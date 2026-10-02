# Rubi Assistant: Stage 3 Build Guide

**Goal of Stage 3:** two upgrades.

1. **Telegram interface:** chat with Rubi from your phone. Only **you** can use it, and risky actions ask for approval with **Yes / No buttons** in Telegram.
2. **Automatic brain switching:** if the laptop has internet, Rubi thinks with **Groq**. If it is offline (or Groq is down), Rubi automatically uses a **local Ollama model**.

**What stays the same:** `tools/` and the safety rules from Stage 2 do not change. This proves the layered design works: new interface, same brain.

**How to use this guide:** same method as before. Each step says what the file must do, then the full working code follows, with many comments.

---

## Table of Contents

1. The big picture
2. Two ideas you need first
3. New project structure
4. Steps 1 to 16
5. Testing
6. Troubleshooting
7. Security notes
8. Stage 3 checklist and what comes next

---

## 1. The big picture

```
 Phone (Telegram app)  <-->  Telegram servers  <-->  telegram_bot.py  --+
                                                                        |
 Laptop terminal       <-------------------------->  terminal.py    ----+
                                                                        v
                                                                  core/agent.py
                                                                        |
                                                                  core/llm.py  (the router)
                                                                   |           |
                                              internet OK -->  Groq API     Ollama (local)  <-- offline / Groq down
                                                                        |
                                                              tools/  (every risky action goes
                                                                       through core/safety.py)
```

**Honest limit:** Telegram itself needs internet. When the laptop is offline, the **terminal** keeps working with the local model, but Telegram cannot reach you. If your network **blocks** Telegram (common on some ISPs), the bot can use a proxy: see "Optional: use a proxy only for Telegram" in Step 4.

---

## 2. Two ideas you need first

### Idea A: Two layers of "am I online?"

| Layer | How it works | Why |
|---|---|---|
| **1. Cheap check** | Try opening a connection to a few well-known IP addresses (no DNS needed). The result is cached for 15 seconds. | Fast, no wasted waiting when you are clearly offline |
| **2. Real failure fallback** | If a real Groq request fails (connection error, timeout, rate limit, server error), switch to Ollama right away and avoid Groq for 45 seconds | Catches "connected to Wi-Fi but no real internet" and Groq outages |

You can also force a brain by hand with `/brain auto`, `/brain groq`, or `/brain ollama`. This is handy for testing and for privacy (in `ollama` mode nothing is sent to Groq).

### Idea B: Telegram is async, your agent is not

- Telegram's library (`python-telegram-bot`) is **asynchronous** (`async`/`await`, one event loop).
- Your `Agent.chat()` is **synchronous** and *blocks* while it waits (for the LLM, for commands, and for your approval).
- If we ran `agent.chat()` directly inside the async handler, the whole bot would freeze, including the button tap you need to approve something. That is a **deadlock**.

Solution: run the agent in a **worker thread** (`asyncio.to_thread`), and let the approver *bridge* between the worker thread and the event loop:

```
Worker thread (agent.chat)                    Event loop thread (Telegram)
-------------------------                     ----------------------------
tool needs approval
telegram_approver() ---- send message with ----> bot sends message with
                         Yes/No buttons          [Yes] [No] buttons
waits on a Future ...                            you tap [Yes]
                    <--- future.set_result ----- on_button() runs
continues: runs the command
```

Two more details this stage uses:
- `concurrent_updates(True)`: lets the bot process your button tap *while* the message handler is still waiting. Without it you get the deadlock above.
- **`ContextVar` for the approver:** in Stage 2 the approver was one global variable. Now the terminal and Telegram can run at the same time, and each needs its own approver (a terminal request must ask in the terminal, a Telegram request must ask in Telegram). A `ContextVar` keeps a separate value per thread/task.

---

## 3. New project structure

`NEW` = new file, `CHANGED` = you replace its code.

```
rubi/
├── .env                       # CHANGED (new keys)
├── requirements.txt           # CHANGED (2 new packages + SOCKS support)
├── config.py                  # CHANGED (new settings)
├── main.py                    # CHANGED (modes: terminal / telegram / both)
├── ollama/
│   └── Modelfile              # NEW: settings for the local model
│
├── core/
│   ├── agent.py               # CHANGED (uses the router)
│   ├── llm.py                 # NEW: Groq <-> Ollama router
│   ├── connectivity.py        # NEW: "is the internet up?"
│   ├── commands.py            # NEW: /status /brain /clear /help (shared by both interfaces)
│   ├── notifier.py            # NEW: send reminders to terminal, desktop, Telegram
│   ├── safety.py              # small CHANGE (approver becomes a ContextVar)
│   └── prompts.py
│
├── interfaces/
│   ├── terminal.py            # CHANGED (supports /commands)
│   └── telegram_bot.py        # NEW
│
├── scheduler/
│   └── jobs.py                # CHANGED (sends reminders through notifier)
│
├── tools/                     # unchanged
└── memory/                    # unchanged
```

---

## 4. Steps

### Step 1: Install Ollama and prepare the local model (do this while online)

**What to do:** install Ollama, download a model that supports **tool calling**, and create a custom version with a bigger **context window**.

Why the custom model? Ollama's default context window (how much text the model can read at once) can be small. Rubi sends a system prompt plus 18 tool descriptions on every request. If that does not fit, the model silently loses part of it and starts failing. We set a bigger window in a `Modelfile`.

Install (official installer; it needs `sudo`, so run it yourself in a normal terminal, not through Rubi):

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama --version
```

> If you prefer to read the script first, run `curl -fsSL https://ollama.com/install.sh -o ollama_install.sh`, read it, then `sh ollama_install.sh`.

Download a model:

```bash
ollama pull qwen2.5:7b
```

**Which model?** It must support tools (look for the "tools" tag on the model's page at ollama.com/library).

| Model | Size | Notes |
|---|---|---|
| `qwen2.5:7b` | about 4.7 GB | Good at tool calling for its size. Wants about 8 GB free RAM |
| `llama3.1:8b` | about 4.9 GB | Alternative if Qwen behaves badly for you |
| `qwen2.5:3b` or `llama3.2:3b` | about 2 GB | For low-RAM laptops. Weaker at tools, expect more mistakes |

Create the custom model:

```bash
mkdir -p ~/rubi/ollama
cat > ~/rubi/ollama/Modelfile << 'EOF'
FROM qwen2.5:7b
PARAMETER num_ctx 8192
PARAMETER temperature 0.3
EOF

ollama create rubi-local -f ~/rubi/ollama/Modelfile
```

(If you chose another model, change the `FROM` line.)

Test it works:

```bash
ollama list
ollama run rubi-local "Say hello in five words"
```

Type `/bye` to leave. Also check the service answers:

```bash
curl http://localhost:11434
```

It should print `Ollama is running`.

> The first reply after a pause is slow (10 to 30 seconds), because Ollama loads the model into RAM. It unloads again after about 5 idle minutes. Local models on a CPU are also much slower and less capable than Groq. That is the price of working offline.

---

### Step 2: Install the new Python packages

Update `requirements.txt`:

```
groq
python-dotenv
apscheduler
openai
python-telegram-bot
httpx[socks]
```

- `openai`: used **only as a client** for Ollama, because Ollama speaks the same API format as OpenAI. This lets the local model reply in the same shape as Groq, so most of your agent code stays unchanged.
- `python-telegram-bot`: the Telegram library.
- `httpx[socks]`: adds SOCKS support to the HTTP library that `python-telegram-bot` uses. Only needed if your proxy URL starts with `socks5://`. It is harmless to install if you do not use a proxy.

```bash
cd ~/rubi
source venv/bin/activate
pip install -r requirements.txt
```

---

### Step 3: Create the new files

```bash
cd ~/rubi
touch core/connectivity.py core/llm.py core/commands.py core/notifier.py
touch interfaces/telegram_bot.py
```

---

### Step 4: Add the new settings

**Add these lines to the end of `config.py`** (above the final `if not GROQ_API_KEY:` check, or anywhere below the imports):

```python
# ---------------------------------------------------------------------------
# Stage 3 settings
# ---------------------------------------------------------------------------

# --- Telegram ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# Your NUMERIC Telegram user ID. We use the number, not your @username, because
# usernames can be changed or reassigned, but the numeric ID never changes.
# 0 means "not set yet" (the bot then starts in setup mode, see Step 14).
_raw_id = os.getenv("TELEGRAM_USER_ID", "").strip()
TELEGRAM_USER_ID = int(_raw_id) if _raw_id.isdigit() else 0

# OPTIONAL proxy used ONLY for Telegram traffic (see "Optional: use a proxy only for
# Telegram" below). Empty means "no proxy". Examples:
#   socks5://127.0.0.1:1080      http://127.0.0.1:8080
TELEGRAM_PROXY = os.getenv("TELEGRAM_PROXY", "").strip() or None

# If you do not tap Yes/No within this time, the request is treated as DENIED.
APPROVAL_TIMEOUT_SECONDS = 120

# --- Local model (Ollama) ---
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "rubi-local")
OLLAMA_TIMEOUT = 180          # local CPU models can be slow, so be patient

# --- Brain switching ---
GROQ_TIMEOUT = 20             # give up on Groq after this many seconds
GROQ_COOLDOWN_SECONDS = 45    # after a Groq failure, skip Groq for this long
INTERNET_CACHE_SECONDS = 15   # remember the "am I online?" result for this long
```

**Add these lines to `.env`** (keep your existing ones):

```
TELEGRAM_TOKEN=paste_token_here_in_step_11
TELEGRAM_USER_ID=
TELEGRAM_PROXY=
OLLAMA_MODEL=rubi-local
```

Leave `TELEGRAM_PROXY=` **empty** if Telegram works on your network.

> `TELEGRAM_TOKEN` contains the word "TOKEN", so the `_clean_env()` function from Stage 2 automatically hides it from every shell command Rubi runs.

#### Optional: use a proxy only for Telegram

**When you need it:** some ISPs block or throttle Telegram. Then the bot fails at startup with `httpx.ConnectTimeout` and `telegram.error.TimedOut`. Test your network first:

```bash
curl -m 10 -I https://api.telegram.org
```

If this hangs or times out, Telegram is blocked and you need a proxy or VPN.

**What to do:**

1. Start your VPN or proxy app on the laptop. Find the local address it listens on. Common examples: `socks5://127.0.0.1:1080` (SOCKS5) or `http://127.0.0.1:8080` (HTTP).
2. Put that address in `.env`:

```
TELEGRAM_PROXY=socks5://127.0.0.1:1080
```

3. Make sure `httpx[socks]` is installed (Step 2) if the address starts with `socks5://`.
4. The code that uses this value is in Step 12 (`_new_builder()` in `telegram_bot.py`).

**Why "only for Telegram":** the proxy is given directly to the Telegram library. Groq, Ollama and the connectivity check use their own connections and **do not** go through it. This matters because Ollama runs on `localhost`, which must never be sent through a proxy.

> Do **not** set the system-wide variables `HTTP_PROXY`, `HTTPS_PROXY` or `ALL_PROXY` for this. They would push every program (including Groq and Ollama) through the proxy.

---

### Step 5: Write `core/connectivity.py`

**What this file must do:**
- Answer one question: "Should I try Groq right now?"
- Use a cheap probe (cached), plus a way for the router to say "a real request just failed, skip Groq for a while"

```python
# core/connectivity.py
#
# "Can I use Groq right now?"  Two inputs decide it:
#   1) a cheap network probe (cached)
#   2) a manual "cooldown" set when a real Groq request just failed

import socket
import time

from config import INTERNET_CACHE_SECONDS

# We probe raw IP addresses, not domain names, for two reasons:
#   - no DNS lookup needed, so when you are offline it fails FAST
#     (DNS lookups can hang for many seconds on a broken network)
#   - several different targets, so one blocked address doesn't fool us
PROBES = [("1.1.1.1", 443), ("8.8.8.8", 53), ("9.9.9.9", 443)]

# online      : last known answer
# valid_until : timestamp until which that answer is trusted without probing again
_state = {"online": True, "valid_until": 0.0}


def _probe() -> bool:
    """Try to open a TCP connection to each probe. One success = we have internet."""
    for host, port in PROBES:
        try:
            # 'with' closes the socket right away; we only care that it connected.
            with socket.create_connection((host, port), timeout=2):
                return True
        except OSError:        # covers timeouts, "network unreachable", refused...
            continue
    return False


def can_use_groq() -> bool:
    """True if Rubi should try Groq. Uses the cached answer when it is still fresh."""
    now = time.time()
    if now < _state["valid_until"]:
        return _state["online"]

    online = _probe()
    _state["online"] = online
    _state["valid_until"] = now + INTERNET_CACHE_SECONDS
    return online


def mark_unavailable(seconds: float) -> None:
    """
    Called by the router when a REAL Groq request failed (timeout, rate limit...).
    Even if the probe says 'online', we skip Groq for a while so we don't wait
    for a failing request on every single message.
    """
    _state["online"] = False
    _state["valid_until"] = time.time() + seconds
```

Quick test (try it with Wi-Fi on, then off):

```bash
python -c "from core import connectivity as c; print('can use groq:', c.can_use_groq())"
```

---

### Step 6: Write `core/llm.py` (the router)

**What this file must do:**
- Hold two clients: Groq and Ollama
- Pick one per request depending on the mode (`auto`, `groq`, `ollama`) and connectivity
- If Groq fails because it is *unavailable* (connection, timeout, rate limit, server error), fall back to Ollama
- **Not** fall back on errors that are *our* fault (wrong API key, bad request), since the local model would not fix those
- Turn Ollama problems into clear messages (not running, model missing, too slow)

```python
# core/llm.py
#
# The "router": the only file that knows there are two brains.
# The agent just calls  router.complete(messages, tools)  and gets a response.

import groq
from groq import Groq
from openai import OpenAI
from openai import APIConnectionError as OllamaConnectionError
from openai import APITimeoutError as OllamaTimeout
from openai import NotFoundError as OllamaModelMissing

from config import (
    GROQ_API_KEY, MODEL_NAME, GROQ_TIMEOUT, GROQ_COOLDOWN_SECONDS,
    OLLAMA_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT,
)
from core import connectivity


def _groq_errors(*names):
    """
    Collect error classes from the groq library by name.
    getattr/hasattr makes this safe even if a library version names one differently.
    """
    return tuple(getattr(groq, n) for n in names if hasattr(groq, n))


# Errors that mean "Groq cannot serve me right now", so the local model should take over.
# (RateLimitError is included on purpose: if you hit the free-tier limit, Rubi keeps
#  working locally. Remove it from this list if you do not want that.)
GROQ_UNAVAILABLE_ERRORS = _groq_errors(
    "APIConnectionError",   # no route to Groq (also the parent of timeouts)
    "APITimeoutError",      # Groq did not answer in time
    "RateLimitError",       # too many requests / tokens
    "InternalServerError",  # Groq-side failure (5xx)
)
# NOT in the list: AuthenticationError (bad key) and BadRequestError (our mistake).
# Falling back would only hide a bug that you need to see.


class LLMRouter:
    MODES = ("auto", "groq", "ollama")

    def __init__(self):
        # max_retries=1: the SDK retries automatically on connection errors; the
        # default (2 retries with waiting) would delay the fallback too much.
        self.groq = Groq(api_key=GROQ_API_KEY, timeout=GROQ_TIMEOUT, max_retries=1)

        # Ollama exposes an OpenAI-compatible API under /v1, so the 'openai' client
        # works. The api_key is required by the client but ignored by Ollama.
        self.ollama = OpenAI(
            base_url=f"{OLLAMA_URL}/v1",
            api_key="ollama",
            timeout=OLLAMA_TIMEOUT,
            max_retries=0,
        )

        self.mode = "auto"          # "auto": decide by connectivity
        self.last_backend = None    # "groq" or "ollama": which one answered last

    # ---------------------------------------------------------------- helpers
    def set_mode(self, mode: str) -> None:
        if mode not in self.MODES:
            raise ValueError(f"mode must be one of: {', '.join(self.MODES)}")
        self.mode = mode

    def _announce(self, backend: str) -> None:
        """Print a line only when the brain CHANGES, so the terminal stays clean."""
        if backend != self.last_backend:
            print(f"   [brain] now using {backend}")
            self.last_backend = backend

    # ----------------------------------------------------------------- Groq
    def _call_groq(self, messages, tools):
        last_error = None
        for _ in range(2):   # one retry: open models sometimes emit a malformed tool call
            try:
                return self.groq.chat.completions.create(
                    model=MODEL_NAME,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    temperature=0.3,
                )
            except GROQ_UNAVAILABLE_ERRORS:
                raise                    # no point retrying: let complete() decide the fallback
            except Exception as error:   # e.g. a flaky malformed tool call: try once more
                last_error = error
        raise last_error

    # --------------------------------------------------------------- Ollama
    def _call_ollama(self, messages, tools):
        try:
            # tool_choice is left out on purpose: not every Ollama version supports it,
            # and "auto" is already the default behavior.
            return self.ollama.chat.completions.create(
                model=OLLAMA_MODEL,
                messages=messages,
                tools=tools,
                temperature=0.3,
            )
        # Order matters: APITimeoutError is a subclass of APIConnectionError, so it must come first.
        except OllamaTimeout as error:
            raise RuntimeError(
                "The local model took too long to answer. Try a smaller model."
            ) from error
        except OllamaConnectionError as error:
            raise RuntimeError(
                f"The local model is not reachable at {OLLAMA_URL}. "
                f"Is Ollama running? Check: systemctl status ollama"
            ) from error
        except OllamaModelMissing as error:
            raise RuntimeError(
                f"The local model '{OLLAMA_MODEL}' was not found. "
                f"Run 'ollama list' and fix OLLAMA_MODEL in .env."
            ) from error

    # ---------------------------------------------------------- public method
    def complete(self, messages, tools):
        """Return a chat completion from whichever brain is appropriate right now."""
        use_groq = self.mode == "groq" or (self.mode == "auto" and connectivity.can_use_groq())

        if use_groq:
            try:
                response = self._call_groq(messages, tools)
                self._announce("groq")
                return response
            except GROQ_UNAVAILABLE_ERRORS as error:
                if self.mode == "groq":
                    # You explicitly asked for Groq only, so do not silently switch.
                    raise RuntimeError(
                        f"Groq is unavailable ({type(error).__name__}) and the brain mode is 'groq' only. "
                        f"Use /brain auto to allow the local model."
                    ) from error
                # Remember the failure so the next messages skip Groq for a while.
                connectivity.mark_unavailable(GROQ_COOLDOWN_SECONDS)
                print(f"   [brain] Groq unavailable ({type(error).__name__}); switching to the local model")

        # Reached when: offline, mode == "ollama", or Groq just failed.
        response = self._call_ollama(messages, tools)
        self._announce("ollama")
        return response
```

---

### Step 7: Replace `core/agent.py`

**What changes:**
- It uses `LLMRouter` instead of talking to Groq directly (so the retry logic moved into `llm.py`)
- Tool call ids are made safe: some local models omit them, so we create `call_0`, `call_1`... when missing
- A `reset()` method clears the history (used by `/clear`)

```python
# core/agent.py  (Stage 3 version)
import json

from config import MAX_HISTORY, MAX_TOOL_ROUNDS
from core.llm import LLMRouter
from core.prompts import build_system_prompt
from tools.registry import TOOL_SCHEMAS, run_tool


def trim_history(history: list, max_len: int) -> list:
    """Keep only the latest messages, and make sure the first one is from the user.
    (A 'tool' message without the assistant message that requested it would be rejected.)"""
    if len(history) <= max_len:
        return history
    history = history[-max_len:]
    while history and history[0]["role"] != "user":
        history = history[1:]
    return history


class Agent:
    def __init__(self):
        self.llm = LLMRouter()     # the brain switcher (Groq or Ollama)
        self.history = []          # conversation so far, WITHOUT the system prompt

    def reset(self):
        """Forget the current conversation (notes and reminders in the database stay)."""
        self.history = []

    def chat(self, user_text: str) -> str:
        start = len(self.history)    # where this turn began, for cleanup if something fails
        self.history.append({"role": "user", "content": user_text})

        try:
            for _ in range(MAX_TOOL_ROUNDS):
                # The system prompt is rebuilt every time so the clock stays current.
                messages = [{"role": "system", "content": build_system_prompt()}] + self.history

                response = self.llm.complete(messages, TOOL_SCHEMAS)
                msg = response.choices[0].message

                # Normalise the tool calls into plain tuples: (id, name, arguments_text).
                # Doing this once means the SAME id is used in the assistant message and in
                # the tool result, even when a model forgot to send an id.
                calls = []
                for index, call in enumerate(msg.tool_calls or []):
                    arguments = call.function.arguments
                    if not isinstance(arguments, str):      # some servers return a dict
                        arguments = json.dumps(arguments)
                    calls.append((call.id or f"call_{index}", call.function.name, arguments))

                # Save the assistant's message in plain-dict form.
                entry = {"role": "assistant", "content": msg.content or ""}
                if calls:
                    entry["tool_calls"] = [
                        {"id": cid, "type": "function", "function": {"name": name, "arguments": args}}
                        for cid, name, args in calls
                    ]
                self.history.append(entry)

                # No tools requested: this is the final answer.
                if not calls:
                    reply = msg.content or ""
                    self.history = trim_history(self.history, MAX_HISTORY)
                    return reply

                # Run each requested tool and send the results back.
                for cid, name, raw_args in calls:
                    try:
                        args = json.loads(raw_args or "{}")
                    except json.JSONDecodeError:
                        result = "Error: the tool arguments were not valid JSON."
                    else:
                        shown = str(args)
                        if len(shown) > 150:
                            shown = shown[:150] + "..."
                        print(f"   [tool] {name}({shown})")
                        result = run_tool(name, args)

                    self.history.append({
                        "role": "tool",
                        "tool_call_id": cid,
                        "content": str(result),
                    })

            return "I could not finish that request. Please try rephrasing it."

        except Exception as error:
            del self.history[start:]     # undo this turn so the history stays valid
            return f"(Error: {error})"
```

---

### Step 8: Test the offline fallback in the terminal (before Telegram)

Your Stage 2 `main.py` and `terminal.py` still work as they are. Run:

```bash
cd ~/rubi
source venv/bin/activate
python main.py
```

Test in this order:

| You do | What should happen |
|---|---|
| Type `hello` (internet on) | `[brain] now using groq` |
| Turn Wi-Fi off (system menu, or `nmcli radio wifi off`), then type `hello` | `[brain] now using ollama` after a short delay, and a reply (slow the first time) |
| Offline: `save a note: offline test` | `[tool] add_note(...)` and the note is saved, so tool calling works locally |
| Offline: `what files do I have?` | `[tool] list_files(...)` |
| Turn Wi-Fi on (`nmcli radio wifi on`), wait about 15 seconds, type `hello` | `[brain] now using groq` again |

> Don't want to touch your Wi-Fi? Skip it. After Step 15 you can type `/brain ollama` to force the local model instead.

If local replies are bad (ignores tools, or prints JSON as text), see Troubleshooting before continuing.

---

### Step 9: Small change in `core/safety.py` (approver becomes a `ContextVar`)

**Why:** the terminal and Telegram can now run in the same program at the same time. Each must ask *its own* user. A `ContextVar` holds a different value in each thread/task.

Find **PART 1** of `safety.py` (from `# PART 1: Approval plumbing` to the end of `ask_approval`) and **replace it** with:

```python
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
```

Also make sure the `from contextvars import ContextVar` line is fine where it is, and that the old lines `_approver = None` and `global _approver` are gone. Everything else in `safety.py` stays the same. Re-run `python test_safety.py` to confirm nothing broke.

---

### Step 10: Notifications for reminders (`core/notifier.py` and `scheduler/jobs.py`)

**What this does:** in Stage 1 and 2 a due reminder was printed directly by the scheduler. Now it goes through a **notifier** with several **sinks** (outputs): terminal, desktop popup, and (when the Telegram bot runs) your phone.

`core/notifier.py`:

```python
# core/notifier.py
#
# One place to announce things. Each "sink" is a function(title, text) that delivers
# the message somewhere. Interfaces register their own sink at startup.

import subprocess

_sinks = []   # all registered delivery functions


def add_sink(func) -> None:
    _sinks.append(func)


def notify(title: str, text: str) -> None:
    """Send the message to every sink. One broken sink must never stop the others."""
    for sink in list(_sinks):
        try:
            sink(title, text)
        except Exception as error:
            print(f"[notifier] one channel failed: {error}")


# ---- built-in sinks --------------------------------------------------------

def print_sink(title: str, text: str) -> None:
    """Print in the terminal (or in the service log when running in the background)."""
    print(f"\n*** {title}: {text} ***", flush=True)


def desktop_sink(title: str, text: str) -> None:
    """Ubuntu desktop popup. Silently skipped if notify-send is missing."""
    try:
        subprocess.run(["notify-send", title, text], check=False, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
```

Replace `scheduler/jobs.py`:

```python
# scheduler/jobs.py
from apscheduler.schedulers.background import BackgroundScheduler

from config import REMINDER_CHECK_SECONDS
from core import notifier
from tools.reminders import pop_due_reminders


def check_reminders():
    """Runs in a background thread every few seconds."""
    # pop_due_reminders() marks them done, so each reminder fires only once.
    for reminder in pop_due_reminders():
        notifier.notify(
            "Rubi Reminder",
            f"{reminder['text']} (set for {reminder['remind_at']})",
        )


def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_reminders, "interval", seconds=REMINDER_CHECK_SECONDS)
    scheduler.start()
    return scheduler
```

---

### Step 11: Create your Telegram bot (manual steps in the Telegram app)

1. Open Telegram and search for **@BotFather** (the official bot with the blue check mark).
2. Send `/newbot`. Choose a display name (e.g. `Rubi`), then a username that ends in `bot` (e.g. `shazi_rubi_bot`).
3. BotFather replies with a **token** (looks like `123456789:ABCdef...`). Paste it into `.env` as `TELEGRAM_TOKEN=...`.
4. Hardening (recommended): send `/setjoingroups` to BotFather, choose your bot, and select **Disable**, so nobody can add your bot to a group.
5. Also recommended: in Telegram go to **Settings, Privacy and Security, Two-Step Verification** and set a password. If someone takes over your Telegram account, they could control Rubi.

> The token is a **secret**. If it ever leaks, send `/revoke` to BotFather to get a new one.

---

### Step 12: Write `core/commands.py` and `interfaces/telegram_bot.py`

#### `core/commands.py` (slash commands shared by both interfaces)

```python
# core/commands.py
#
# Slash commands handled by code (no LLM involved). Both the terminal and Telegram
# call handle_command(), so the behavior is identical everywhere.

from config import MODEL_NAME, OLLAMA_MODEL
from core import connectivity

HELP = (
    "Commands:\n"
    "/status  show which brain is in use\n"
    "/brain auto|groq|ollama  choose the brain (auto = Groq online, local model offline)\n"
    "/clear  forget this conversation (notes and reminders are kept)\n"
    "/help  show this list"
)


def handle_command(agent, text: str) -> str:
    parts = text.strip().split()
    # Telegram sometimes sends "/status@MyBotName": drop the "@..." part.
    command = parts[0].lower().split("@")[0]
    args = parts[1:]

    if command in ("/start", "/help"):
        return "Hi, I'm Rubi.\n" + HELP

    if command == "/clear":
        agent.reset()
        return "Conversation cleared. Your notes and reminders are untouched."

    if command == "/status":
        groq_ok = connectivity.can_use_groq()
        return (
            f"Brain mode: {agent.llm.mode}\n"
            f"Groq reachable right now: {'yes' if groq_ok else 'no'}\n"
            f"Last brain used: {agent.llm.last_backend or 'none yet'}\n"
            f"Groq model: {MODEL_NAME}\n"
            f"Local model: {OLLAMA_MODEL}"
        )

    if command == "/brain":
        if not args:
            return f"Current brain mode: {agent.llm.mode}. Use /brain auto, /brain groq or /brain ollama."
        try:
            agent.llm.set_mode(args[0].lower())
        except ValueError as error:
            return str(error)
        return f"Brain mode set to: {agent.llm.mode}"

    return f"Unknown command {command}.\n{HELP}"
```

#### `interfaces/telegram_bot.py` (the main new file)

**What this file must do:**
1. Accept messages **only** from your numeric user ID, in private chat. Ignore everyone else silently, but log the attempt.
2. Run `agent.chat()` in a worker thread (no freezing), show a "typing..." indicator, and split long replies.
3. Provide `telegram_approver`: send the approval text with **Yes/No buttons** and wait for your tap (timeout means deny)
4. Register a reminder sink so reminders also arrive on your phone
5. Provide a **setup mode** that tells you your user ID, used once

```python
# interfaces/telegram_bot.py
#
# Telegram interface. Runs in the MAIN thread (run_polling needs that).
# The agent runs in worker threads, and the approver bridges back to the event loop.

import asyncio
import concurrent.futures
import logging
import uuid

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application, CallbackQueryHandler, ContextTypes, MessageHandler, filters,
)
from telegram.request import HTTPXRequest

from config import (
    TELEGRAM_TOKEN, TELEGRAM_USER_ID, TELEGRAM_PROXY, APPROVAL_TIMEOUT_SECONDS,
)
from core import notifier, safety
from core.agent import Agent
from core.commands import handle_command

CHUNK_SIZE = 4000   # Telegram rejects messages longer than 4096 characters

# One agent (one conversation history) for your Telegram chat.
# The terminal has its own, so the two conversations do not mix.
agent = Agent()

# The agent is not thread-safe, so only ONE request may use it at a time.
agent_lock = asyncio.Lock()

# Shared with the worker threads: the event loop and the app are filled in post_init().
_state = {"loop": None, "app": None}

# approval_id -> Future. A Future is a box that the worker thread waits on, and the
# button handler fills with True/False when you tap.
_pending = {}


# ===========================================================================
# Helpers
# ===========================================================================

def chunk_text(text: str, size: int = CHUNK_SIZE) -> list:
    """Split a long reply into Telegram-sized pieces."""
    text = text or "(no reply)"
    return [text[i:i + size] for i in range(0, len(text), size)]


async def keep_typing(bot, chat_id: int, stop: asyncio.Event) -> None:
    """Show 'typing...' while the agent works. Telegram hides it after ~5 seconds,
    so we resend it every 4 seconds until 'stop' is set."""
    while not stop.is_set():
        try:
            await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception:
            pass                                    # a failed indicator is not important
        try:
            await asyncio.wait_for(stop.wait(), timeout=4)
        except asyncio.TimeoutError:
            pass                                    # 4 seconds passed: loop and resend


# ===========================================================================
# The approver (runs in a WORKER thread, called by tools via safety.py)
# ===========================================================================

def telegram_approver(description: str) -> bool:
    loop = _state["loop"]
    app = _state["app"]
    if loop is None or app is None:
        return False                                # not ready: fail safe

    approval_id = uuid.uuid4().hex[:8]              # short random id for this request
    answer = concurrent.futures.Future()            # the worker will wait on this
    _pending[approval_id] = answer

    text = "RUBI NEEDS YOUR APPROVAL\n\n" + description
    if len(text) > 3800:
        text = text[:3800] + "\n...[cut]"           # stay under Telegram's limit

    # callback_data is sent back to us when a button is tapped (max 64 bytes).
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("Yes, allow", callback_data=f"ok:{approval_id}"),
        InlineKeyboardButton("No, deny", callback_data=f"no:{approval_id}"),
    ]])

    # We are in a worker thread, but the bot lives on the event loop thread.
    # run_coroutine_threadsafe schedules the coroutine there and gives us a Future.
    try:
        sent = asyncio.run_coroutine_threadsafe(
            app.bot.send_message(chat_id=TELEGRAM_USER_ID, text=text, reply_markup=keyboard),
            loop,
        ).result(timeout=20)
    except Exception:
        _pending.pop(approval_id, None)
        return False                                # could not even ask (offline?) -> deny

    try:
        # Block this worker thread until you tap a button (or the timeout passes).
        return bool(answer.result(timeout=APPROVAL_TIMEOUT_SECONDS))
    except concurrent.futures.TimeoutError:
        # No answer in time: treat as DENIED and remove the buttons.
        try:
            asyncio.run_coroutine_threadsafe(
                app.bot.edit_message_text(
                    chat_id=TELEGRAM_USER_ID,
                    message_id=sent.message_id,
                    text=text + "\n\nNo answer in time: DENIED",
                ),
                loop,
            ).result(timeout=10)
        except Exception:
            pass
        return False
    finally:
        _pending.pop(approval_id, None)             # always clean up


def telegram_sink(title: str, text: str) -> None:
    """Notifier sink: also deliver reminders to your phone."""
    loop = _state["loop"]
    app = _state["app"]
    if loop is None or app is None:
        return
    asyncio.run_coroutine_threadsafe(
        app.bot.send_message(chat_id=TELEGRAM_USER_ID, text=f"{title}: {text}"),
        loop,
    ).result(timeout=15)    # if this raises, notifier prints the error and carries on


# ===========================================================================
# Handlers (async, run on the event loop)
# ===========================================================================

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message

    # Only one request at a time (the agent keeps ONE conversation).
    if agent_lock.locked():
        await message.reply_text("Still working on your previous request. Please wait a moment.")
        return

    async with agent_lock:
        # Tell safety.py to ask via Telegram for everything this request triggers.
        # asyncio.to_thread copies the current context, so the worker thread sees this.
        safety.set_approver(telegram_approver)

        stop = asyncio.Event()
        typing_task = asyncio.create_task(keep_typing(context.bot, update.effective_chat.id, stop))
        try:
            # Run the blocking agent in a worker thread so the event loop stays free
            # (it must stay free to receive your button taps!).
            reply = await asyncio.to_thread(agent.chat, message.text)
        except Exception as error:
            reply = f"Something went wrong: {error}"
        finally:
            stop.set()
            await typing_task

    for part in chunk_text(reply):
        await message.reply_text(part)              # plain text on purpose: no formatting errors


async def on_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # /status may probe the network for a moment, so run it off the event loop.
    reply = await asyncio.to_thread(handle_command, agent, update.effective_message.text)
    await update.effective_message.reply_text(reply)


async def on_other(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text("I only understand text messages for now.")


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query

    # Ignore button taps from anyone except you (buttons only go to your chat,
    # but we check anyway: never trust, always verify).
    if query.from_user.id != TELEGRAM_USER_ID:
        await query.answer()
        return

    action, _, approval_id = (query.data or "").partition(":")
    answer = _pending.get(approval_id)

    # Old buttons (after a timeout or a restart) must not do anything.
    if answer is None or answer.done():
        await query.answer("This request has expired.", show_alert=True)
        try:
            await query.edit_message_reply_markup(reply_markup=None)   # remove stale buttons
        except Exception:
            pass
        return

    approved = (action == "ok")
    try:
        answer.set_result(approved)                 # wakes up the waiting worker thread
    except concurrent.futures.InvalidStateError:
        pass                                        # it was answered/expired a split second ago

    await query.answer("Approved" if approved else "Denied")
    await query.edit_message_text(
        query.message.text + ("\n\nYOU APPROVED" if approved else "\n\nYOU DENIED")
    )


async def on_stranger(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Someone else messaged the bot. Do NOT reply (that would confirm the bot is alive).
    Only write it to the audit log."""
    user = update.effective_user
    who = f"user_id={user.id} username={user.username}" if user else "unknown"
    safety.log_action("telegram_access", who, "BLOCKED")


async def on_error(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    print(f"[telegram] error: {context.error}")


async def post_init(application: Application) -> None:
    """Runs once when the bot has started (we are now inside the event loop)."""
    _state["loop"] = asyncio.get_running_loop()
    _state["app"] = application
    notifier.add_sink(telegram_sink)                # reminders also go to Telegram

    # The command menu that appears when you type "/" in the chat.
    await application.bot.set_my_commands([
        BotCommand("status", "Show which brain is in use"),
        BotCommand("brain", "auto, groq or ollama"),
        BotCommand("clear", "Forget this conversation"),
        BotCommand("help", "Show commands"),
    ])


# ===========================================================================
# Starting the bot
# ===========================================================================

def _new_builder():
    """
    Application builder shared by setup mode and normal mode.

    If TELEGRAM_PROXY is set, ONLY Telegram traffic goes through it. Groq and Ollama
    use their own HTTP clients, so they are not affected.

    python-telegram-bot uses TWO separate HTTP clients: one for normal calls
    (send_message, ...) and one for the long-polling getUpdates call.
    Both need the same proxy. The longer timeouts help on slow proxies/VPNs.
    (TELEGRAM_PROXY = None simply means "no proxy".)
    """
    request = HTTPXRequest(
        proxy=TELEGRAM_PROXY, connect_timeout=30, read_timeout=30, write_timeout=30,
    )
    updates_request = HTTPXRequest(
        proxy=TELEGRAM_PROXY, connect_timeout=30, read_timeout=30,
    )
    return (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .request(request)
        .get_updates_request(updates_request)
    )


def can_start() -> bool:
    """True if both the token and your user ID are configured."""
    return bool(TELEGRAM_TOKEN and TELEGRAM_USER_ID)


def _run_setup_mode() -> None:
    """
    Used once, when TELEGRAM_USER_ID is not set yet. The bot does NOTHING except tell
    whoever messages it their own numeric user ID. No agent, no tools.
    """
    async def reply_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        await update.effective_message.reply_text(
            f"Your Telegram user ID is: {user.id}\n\n"
            f"Put this line in your .env file:\nTELEGRAM_USER_ID={user.id}\n"
            f"Then stop Rubi (Ctrl+C) and start it again."
        )

    print("SETUP MODE: TELEGRAM_USER_ID is not set.")
    print("Open Telegram, send any message to your bot, and copy the ID it replies with.")
    print("Then add it to .env and restart. Press Ctrl+C to stop.\n")

    app = _new_builder().build()
    app.add_handler(MessageHandler(
        filters.UpdateType.MESSAGE & filters.ChatType.PRIVATE, reply_id
    ))
    app.run_polling(drop_pending_updates=True)


def run() -> None:
    logging.basicConfig(level=logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)   # hide the noisy per-poll lines

    if not TELEGRAM_TOKEN:
        print("Telegram: TELEGRAM_TOKEN is missing in .env (create a bot with @BotFather).")
        return
    if not TELEGRAM_USER_ID:
        _run_setup_mode()
        return

    # The ONLY people allowed: you, in a private chat.
    allowed = filters.User(user_id=TELEGRAM_USER_ID) & filters.ChatType.PRIVATE

    app = (
        _new_builder()          # token + optional proxy (see above)
        # IMPORTANT: lets button taps be processed while on_text is still waiting.
        # Without this, approvals would deadlock (see "Idea B" at the top of the guide).
        .concurrent_updates(True)
        .post_init(post_init)
        .build()
    )

    # Handlers are checked in the order they are added. The first match wins.
    app.add_handler(MessageHandler(allowed & filters.COMMAND, on_command))
    app.add_handler(MessageHandler(allowed & filters.TEXT & ~filters.COMMAND, on_text))
    app.add_handler(MessageHandler(allowed & ~filters.TEXT & ~filters.COMMAND, on_other))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(~allowed, on_stranger))   # everyone else: log, never reply
    app.add_error_handler(on_error)

    print(f"Telegram proxy: {'enabled' if TELEGRAM_PROXY else 'none'}")
    print("Telegram bot is running. Press Ctrl+C to stop.")
    app.run_polling(
        # SAFETY: ignore any messages that arrived while Rubi was off. Otherwise old
        # requests could suddenly run when Rubi starts.
        drop_pending_updates=True,
        # If there is no internet at startup, keep retrying instead of crashing.
        bootstrap_retries=-1,
    )
```

---

### Step 13: Replace `interfaces/terminal.py` and `main.py`

`interfaces/terminal.py` (adds `/commands`; everything else is as in Stage 2):

```python
# interfaces/terminal.py
from core import safety
from core.agent import Agent
from core.commands import handle_command


def terminal_approver(description: str) -> bool:
    """Show an action to the user and return True only for a clear 'yes'.
    The text is built by our code (not by the LLM), so what you read is true."""
    print("\n" + "=" * 62)
    print("RUBI NEEDS YOUR APPROVAL")
    print("-" * 62)
    print(description)
    print("=" * 62)
    try:
        answer = input("Allow this? (yes/no): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nNot allowed.")
        return False
    return answer in {"y", "yes"}          # anything else, even just Enter, means no


def run():
    # Registered inside THIS thread's context (see the ContextVar explanation), so it
    # only applies to requests that come from the terminal.
    safety.set_approver(terminal_approver)

    agent = Agent()
    print("Rubi online. Type /help for commands, 'exit' to quit.\n")

    while True:
        try:
            user_text = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not user_text:
            continue
        if user_text.lower() in {"exit", "quit"}:
            print("Goodbye.")
            break

        # Slash commands are handled by code, not sent to the LLM.
        if user_text.startswith("/"):
            print(handle_command(agent, user_text) + "\n")
            continue

        reply = agent.chat(user_text)
        print(f"Rubi: {reply}\n")
```

`main.py` (three modes):

```python
# main.py
#
# Usage:
#   python main.py            terminal only (default)
#   python main.py telegram   Telegram only (use this for the background service)
#   python main.py both       Telegram + terminal in the same program

import sys
import threading

from config import WORKSPACE_DIR
from core import notifier
from memory.db import init_db
from scheduler.jobs import start_scheduler


def main():
    mode = sys.argv[1].lower() if len(sys.argv) > 1 else "terminal"
    if mode not in ("terminal", "telegram", "both"):
        print("Usage: python main.py [terminal|telegram|both]")
        return

    init_db()
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

    # Where reminders are delivered (the Telegram sink is added later by the bot itself).
    notifier.add_sink(notifier.print_sink)
    notifier.add_sink(notifier.desktop_sink)

    scheduler = start_scheduler()
    try:
        if mode == "terminal":
            from interfaces import terminal
            terminal.run()

        elif mode == "telegram":
            # Imported here (not at the top) so terminal mode works even if the
            # Telegram library is not installed.
            from interfaces import telegram_bot
            telegram_bot.run()

        else:  # both
            from interfaces import terminal, telegram_bot
            if not telegram_bot.can_start():
                print("Telegram is not configured yet, starting the terminal only.")
                print("(Run 'python main.py telegram' once to find your user ID.)\n")
                terminal.run()
            else:
                # The terminal runs in a background thread, and Telegram takes the main
                # thread (python-telegram-bot's run_polling needs the main thread).
                # daemon=True: the thread ends automatically when the program ends.
                threading.Thread(target=terminal.run, daemon=True).start()
                telegram_bot.run()
    finally:
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    main()
```

---

### Step 14: Find your Telegram user ID, then start the bot

> If Telegram is blocked on your network (you get `ConnectTimeout` or `TimedOut`), start your VPN/proxy and set `TELEGRAM_PROXY` in `.env` first (see Step 4). Setup mode uses the proxy too.

1. Make sure `.env` has your real `TELEGRAM_TOKEN` and an **empty** `TELEGRAM_USER_ID=`.
2. Start setup mode:

```bash
cd ~/rubi
source venv/bin/activate
python main.py telegram
```

3. In Telegram, open your bot and send any message. It replies with a line like `TELEGRAM_USER_ID=123456789`.
4. Stop Rubi with `Ctrl+C`, paste that line into `.env`, and start again:

```bash
python main.py telegram
```

You should see `Telegram bot is running.` Now send it `/help`.

---

### Step 15: Run it in the background (a systemd user service)

So Rubi starts when you log in and restarts if it crashes.

Create the folder and the service file:

```bash
mkdir -p ~/.config/systemd/user
nano ~/.config/systemd/user/rubi.service
```

Paste:

```ini
[Unit]
Description=Rubi personal assistant (Telegram mode)

[Service]
Type=simple
WorkingDirectory=%h/rubi
ExecStart=%h/rubi/venv/bin/python main.py telegram
# Show log lines immediately instead of buffering them
Environment=PYTHONUNBUFFERED=1
# Restart if it crashes, wait 10 seconds between attempts
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
```

(`%h` means your home folder. We call the venv's Python directly, so you do not need to activate anything.)

> If you use `TELEGRAM_PROXY`, the proxy/VPN app must be running for the bot to connect. `bootstrap_retries=-1` makes the bot keep retrying at startup, so it recovers once the proxy is up. The service reads `TELEGRAM_PROXY` from `.env` like every other setting.

Enable and start it:

```bash
systemctl --user daemon-reload
systemctl --user enable --now rubi
systemctl --user status rubi
```

Watch its log live:

```bash
journalctl --user -u rubi -f
```

Useful commands:

| Command | What it does |
|---|---|
| `systemctl --user restart rubi` | Restart after changing code or `.env` |
| `systemctl --user stop rubi` | Stop it |
| `systemctl --user disable rubi` | Do not start at login |
| `loginctl enable-linger $USER` | Optional: keep it running even when you are logged out |

> Never run `python main.py telegram` by hand **while the service is running**. Two instances polling the same bot conflict with each other. Stop the service first (`systemctl --user stop rubi`).

---

### Step 16: Final check of the whole chain

Ask Rubi from Telegram: `remind me to stretch in 2 minutes`, then wait. The reminder should arrive on your phone **and** as a desktop popup.

---

## 5. Testing

First the safety tests (they must still pass after the `safety.py` change):

```bash
python test_safety.py
```

Then Telegram (service or `python main.py telegram`):

| You send (in Telegram) | What should happen |
|---|---|
| `/help` | The command list |
| `/status` | Brain mode `auto`, Groq reachable `yes`, last brain `none yet` |
| `hello` | A short reply. Typing indicator shows while waiting |
| `save a note: telegram test` | Note saved (check with `show my notes`) |
| `how much disk space is left?` | `df -h` runs automatically, Rubi summarizes |
| `create a python script hi.py that prints hi` | **Message with Yes/No buttons** showing the script. Tap **No** first, then ask again and tap **Yes** |
| `run hi.py` | Buttons for `python3 hi.py`, then the output after you tap Yes |
| `delete hi.py` | Buttons. Leave it unanswered for 2 minutes: the message updates to "DENIED" |
| Tap an old button after it expired | Pop-up: "This request has expired." |
| Send a message while Rubi is busy | "Still working on your previous request..." |
| Send a voice message or photo | "I only understand text messages for now." |
| `/brain ollama` then `hello` | `[brain] now using ollama` in the log, and a (slower) reply |
| `/brain auto` | Back to automatic |
| `/clear` | History cleared |
| Message the bot from a **second Telegram account** | **No reply at all.** Check `~/rubi/logs/actions.log` for a `BLOCKED | telegram_access` line |

Testing offline behavior with Telegram: turn the laptop's Wi-Fi off. Telegram cannot reach Rubi (expected). Use the terminal (`python main.py`): it should answer through Ollama. Turn Wi-Fi back on and the bot reconnects on its own.

---

## 6. Troubleshooting

| Problem | Likely cause and fix |
|---|---|
| `ModuleNotFoundError: No module named 'telegram'` or `'openai'` | Run `pip install -r requirements.txt` inside the venv |
| Bot never answers you | Wrong `TELEGRAM_USER_ID`, or `.env` not reloaded. Restart Rubi. Check `logs/actions.log` for `telegram_access` BLOCKED lines with your real ID |
| `Conflict: terminated by other getUpdates request` | Two copies of the bot are running (for example the service plus a manual run). Stop one |
| `httpx.ConnectTimeout` / `telegram.error.TimedOut` at startup | The laptop cannot reach `api.telegram.org` (often blocked by the ISP). Test with `curl -m 10 -I https://api.telegram.org`. Fix: start a VPN/proxy and set `TELEGRAM_PROXY` in `.env` (Step 4), then restart |
| Still `ConnectTimeout` with `TELEGRAM_PROXY` set | The proxy app is not running, or the port is wrong. Check with `ss -ltn \| grep 1080` (use your port). Also confirm the scheme: `socks5://` for SOCKS, `http://` for HTTP proxies |
| `socksio package is not installed` or `Unknown scheme for proxy URL` | You use `socks5://` without SOCKS support. Run `pip install "httpx[socks]"` inside the venv |
| `TypeError: ... unexpected keyword argument 'proxy'` | Your `python-telegram-bot` is old (v20.x used `proxy_url=`). Best fix: `pip install -U python-telegram-bot` |
| Approval buttons never appear | Check the log. Without `.concurrent_updates(True)` this deadlocks. Confirm that line exists |
| Buttons say "expired" immediately | Rubi was restarted, or more than 2 minutes passed. Ask again |
| `TypeError: ... unexpected keyword argument` from the telegram library | Library versions differ. Check `pip show python-telegram-bot` and the docs for your version (`run_polling`, `Application.builder`) |
| `RuntimeError: There is no current event loop` | Telegram must run in the main thread. Do not start `telegram_bot.run()` inside a thread |
| `The local model is not reachable at http://localhost:11434` | Ollama is not running. `systemctl status ollama`, then `sudo systemctl start ollama` |
| `The local model 'rubi-local' was not found` | Redo the `ollama create` step. `ollama list` must show `rubi-local` |
| First offline answer takes 30+ seconds | The model is loading into RAM. Normal. A smaller model loads faster |
| Computer freezes or the model gets killed | Not enough RAM. Use `qwen2.5:3b` or `llama3.2:3b` and change the `FROM` line, then `ollama create` again |
| Offline model ignores tools, or writes tool JSON as plain text | Small models do this. Try `llama3.1:8b`, make sure `num_ctx` is 8192, or ask more directly ("save a note: ..."). The safety layer still protects you either way |
| Rubi stays on Ollama although you are online | Groq is in a 45-second cooldown after a failure (or you set `/brain ollama`). Use `/status`, then `/brain auto` |
| Rubi says Groq is unavailable in `groq` mode | You forced Groq only. Use `/brain auto` |
| Rate limit errors keep switching you to Ollama | Expected with the free tier. Lower `MAX_HISTORY`, or remove `RateLimitError` from `GROQ_UNAVAILABLE_ERRORS` in `llm.py` |
| Reminder did not reach Telegram | You were offline when it fired. The desktop popup still shows, but the Telegram message is not retried (see "What to learn next") |
| Apps will not open when run as a service | The service may lack your desktop session variables. Try `systemctl --user import-environment DISPLAY WAYLAND_DISPLAY XDG_RUNTIME_DIR`, then restart the service |
| Service fails to start | `journalctl --user -u rubi -n 50` shows the error. Check the paths in `rubi.service` |

---

## 7. Security notes

Stage 3 adds a **remote control channel** to your laptop, so be strict:

- **Who can use it:** only your numeric user ID, only in private chat. Strangers get no reply (so they cannot even tell the bot is alive), and every attempt is logged.
- **Approvals still protect you.** A Telegram message alone cannot delete files or run unknown commands. You must tap Yes. Read the text before tapping. It shows the exact command or file content.
- **Your Telegram account is now a key to your laptop.** If someone takes it over, they can tap Yes. Turn on Two-Step Verification.
- **Protect the bot token.** Anyone with the token can read your chat with the bot. If it leaks, `/revoke` it in BotFather.
- **Telegram chats are not end-to-end encrypted** (bot chats are stored on Telegram's servers). Rubi's replies, including command output and file contents, pass through Telegram. Do not ask it to show secrets.
- **A proxy or VPN sees where you connect.** Telegram traffic is encrypted (HTTPS) between Rubi and Telegram, so a normal proxy cannot read your messages or token, but it can see that you use Telegram. Use a VPN/proxy you trust. Never use random free public proxies for a bot that controls your laptop.
- **Old messages are ignored at startup** (`drop_pending_updates=True`), so nothing queued while Rubi was off can run later.
- **Online, your conversation goes to Groq. Offline or in `/brain ollama` mode it stays on your laptop** (except what Telegram itself carries). Use `/brain ollama` when handling anything private.
- **The local model is weaker.** Small models misunderstand more and follow tool formats less reliably. The safety layer applies equally, but read approval prompts even more carefully when Rubi is on the local brain.
- **WhatsApp** was left out on purpose. It needs a Meta business account, an approved API setup and a public web address. Telegram gives you the same result with far less risk.

---

## 8. Stage 3 checklist and what comes next

**Done when:**
- [ ] `ollama run rubi-local "hello"` answers
- [ ] Online, the terminal shows `[brain] now using groq`
- [ ] Offline (or `/brain ollama`), it shows `[brain] now using ollama`, and notes/reminders still work
- [ ] After reconnecting, it returns to Groq on its own
- [ ] Your Telegram messages get answers, and a second account gets **no** reply
- [ ] (Only if Telegram is blocked for you) the startup line shows `Telegram proxy: enabled` and the bot connects
- [ ] Risky actions show Yes/No buttons and "No" really stops them
- [ ] Reminders arrive on your phone and as desktop popups
- [ ] `python test_safety.py` still passes
- [ ] The systemd service starts at login and restarts on failure

**Concepts this stage taught you** (and where they connect):
- **Adapter/router pattern:** one interface (`complete()`), two backends. The same idea lets you add a third brain later
- **Graceful degradation:** a worse but working answer is better than an error
- **Async vs sync, threads, and futures:** the bridge between `asyncio` and blocking code is used in nearly every real-world Python bot
- **ContextVar:** per-request state without passing arguments everywhere
- **Allow-listing identity:** numeric IDs, never usernames
- **Services:** `systemd` keeps programs alive

**What to learn next:**
1. `asyncio` basics: tasks, locks, `to_thread`, `run_coroutine_threadsafe`
2. Threads vs processes in Python, and why SQLite connections are opened per operation
3. A **retry queue** for reminders that could not be delivered (offline), as a good exercise: store "undelivered" in SQLite and resend at reconnect
4. Ollama's other features (embeddings, model management), useful for local search over your notes later

**Stage 4 preview (voice):**
- Hearing: `faster-whisper` (offline, runs locally) or Groq's Whisper when online, using the same online/offline switch you just built
- Speaking: `piper` (offline text to speech)
- Optional wake word ("Rubi") with `openWakeWord`
- Telegram voice messages: download the audio, transcribe it, answer

When Stage 3 works, say "start Stage 4".