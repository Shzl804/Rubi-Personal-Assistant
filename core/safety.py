# core/safety.py
#
# The safety layer. It is plain Python, so the LLM cannot argue with it.
# Nothing in this file talks to the LLM.

import os
import shlex
from datetime import datetime
from config import LOG_PATH


# ===========================================================================
# PART 1: Approval plumbing
# ===========================================================================
# safety.py does not know HOW to ask the user. Each interface registers its own
# "approver" function: the terminal uses input(), Telegram sends buttons.
#
# A ContextVar is a variable whose value is separate for each thread (and each
# asyncio task). So when Rubi runs the terminal and Telegram together, a request
# that came from the terminal asks in the terminal, and a request that came from
# Telegram asks in Telegram. With a plain global variable they would overwrite
# each other.

from contextvars import ContextVar

_approver_var: ContextVar = ContextVar("approver", default=None)


def set_approver(func):
    """Interfaces call this before running the agent: how to ask THIS user."""
    _approver_var.set(func)


def ask_approval(description: str) -> bool:
    """Ask the user. Returns True only if they clearly said yes."""
    approver = _approver_var.get()
    # FAIL SAFE: no approver registered means we cannot ask, and "cannot ask" means "no".
    if approver is None:
        return False
    try:
        return bool(approver(description))
    except Exception:
        # Any error while asking (closed input, offline, bug...) also means "no".
        return False

# ===========================================================================
# PART 2: Audit log
# ===========================================================================
# One line per action: time | decision | kind | detail
# Decisions used: AUTO (ran without asking), APPROVED, DENIED, BLOCKED.
# If something strange ever happens, this file tells you exactly what Rubi did.

def log_action(kind: str, detail: str, decision: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # Keep each entry on one line and not absurdly long.
    one_line = detail.replace("\n", " ")[:500]
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"{stamp} | {decision:<8} | {kind} | {one_line}\n")


def approve(kind: str, description: str) -> bool:
    """Ask the user, log the answer, return True/False."""
    ok = ask_approval(description)
    log_action(kind, description, "APPROVED" if ok else "DENIED")
    return ok


def gate(kind: str, description: str, needs_approval: bool) -> bool:
    """
    One-line helper used by every tool:
      - needs_approval False -> log as AUTO and allow
      - needs_approval True  -> ask the user (logged inside approve)
    Returns True if the action may proceed.
    """
    if not needs_approval:
        log_action(kind, description, "AUTO")
        return True
    return approve(kind, description)


# ===========================================================================
# PART 3: Shell command classification
# ===========================================================================

# --- 3a. Commands allowed to run WITHOUT asking (read-only, harmless) -------
# Only the FIRST word is checked, and only if the command contains no shell
# operators (see OPERATOR_CHARS). Keep this list short and boring.
SAFE_COMMANDS = {
    "ls", "pwd", "whoami", "date", "uptime", "df", "du", "free", "uname",
    "hostname", "echo", "cat", "head", "tail", "wc", "grep", "which", "id",
    "nproc", "lscpu", "lsblk", "lsb_release",
}

# --- 3b. Commands that must NEVER run ---------------------------------------
# Substrings checked against the whole (lower-cased) command.
BLOCKED_SUBSTRINGS = [
    ":(){",                               # fork bomb
    "/dev/sd", "/dev/nvme", "/dev/mmcblk",  # writing to raw disks
    "| sh", "|sh", "| bash", "|bash",     # curl ... | bash (run unseen code)
    "chmod -r 777 /",                     # make the whole system world-writable
    "--no-preserve-root",                 # explicit "yes, really delete /"
]

# Program names that are never run (checked against every word of the command,
# so "sudo dd ..." is also caught).
BLOCKED_COMMAND_NAMES = {"dd", "shred", "wipefs", "fdisk", "parted", "cryptsetup"}

# Folders/paths that "rm -r" must never target.
HOME = os.path.expanduser("~").rstrip("/")
PROTECTED_PATHS = {
    "/", "/*", "~", "~/*", "$HOME", "$HOME/*",
    "/bin", "/boot", "/dev", "/etc", "/home", "/lib", "/opt",
    "/proc", "/root", "/sbin", "/sys", "/usr", "/var",
    HOME, HOME + "/*",
}

# --- 3c. Characters that let one command do several things ------------------
# With any of these, "ls; rm file" would look like a safe "ls" at first glance.
# So if ANY of them appear, the command is never auto-run.
#   ; | &   chaining and pipes        < >   redirects (can overwrite files)
#   ` $ ( ) command substitution/variables/subshells
#   \ and newlines   line tricks
OPERATOR_CHARS = set(";|&<>`$()\\\n\r")

# --- 3d. Paths that hold secrets: always ask (and warn) ---------------------
# Reason: anything Rubi reads is sent to Groq's servers inside the chat.
SENSITIVE_PARTS = [
    ".ssh", ".gnupg", ".aws", ".env", "id_rsa", "id_ed25519", "/etc/shadow",
    "/etc/passwd", ".bash_history", ".netrc", ".mozilla", "keyring", "credentials",
]


def _is_protected(path: str) -> bool:
    """True if this path is one rm -r must never touch."""
    p = path.rstrip("/") or "/"     # "/" becomes "" after rstrip, so restore it
    return p in PROTECTED_PATHS


def _rm_hits_protected_path(tokens: list) -> bool:
    """Detect things like: rm -rf /   rm -r ~   sudo rm -rf /home"""
    if "rm" not in tokens:
        return False
    args = tokens[tokens.index("rm") + 1:]

    # Is it a recursive delete? (-r, -R, -rf, -fr, --recursive ...)
    recursive = any(
        a == "--recursive" or (a.startswith("-") and not a.startswith("--") and "r" in a.lower())
        for a in args
    )
    targets = [a for a in args if not a.startswith("-")]
    return recursive and any(_is_protected(t) for t in targets)


def classify_command(command: str):
    """
    Decide what to do with a shell command.
    Returns (level, reason) where level is "safe", "risky" or "blocked".
    The order of the checks matters: the strictest checks come first.
    """
    # Collapse repeated spaces so "rm   -rf   /" is seen as "rm -rf /".
    normalized = " ".join(command.split())
    lowered = normalized.lower()

    # 1) Empty command: nothing to run.
    if not normalized:
        return "blocked", "empty command"

    # 2) Blocked substrings (checked BEFORE parsing so odd syntax can't dodge them).
    for bad in BLOCKED_SUBSTRINGS:
        if bad in lowered:
            return "blocked", f"contains forbidden pattern '{bad}'"

    # 3) Split into words the same way a shell would. Broken quotes -> unclear
    #    command -> ask the user rather than guess.
    try:
        tokens = shlex.split(normalized)
    except ValueError:
        return "risky", "could not parse the command (unbalanced quotes?)"

    # 4) Blocked programs and mass deletion of protected paths.
    for t in tokens:
        if t in BLOCKED_COMMAND_NAMES or t.startswith("mkfs"):
            return "blocked", f"'{t}' is never allowed"
    if _rm_hits_protected_path(tokens):
        return "blocked", "recursive delete of a protected folder"

    # 5) Shell operators: a "safe" first word could hide something else.
    #    NOTE: checked on the ORIGINAL command so newlines are still visible.
    if any(ch in OPERATOR_CHARS for ch in command):
        return "risky", "uses shell operators (chaining, pipes, redirects, variables)"

    # 6) Touches secret-looking paths.
    for part in SENSITIVE_PARTS:
        if part in lowered:
            return "risky", f"touches a sensitive path ('{part}'); its output would be sent to Groq"

    # 7) Allow-list: only now can a command run automatically.
    if tokens[0] in SAFE_COMMANDS:
        return "safe", "read-only command on the allow-list"

    # 8) Default: unknown command -> ask.
    return "risky", "not on the safe list"
