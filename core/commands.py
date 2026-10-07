# core/commands.py
#
# Slash commands handled by code (no LLM involved). Both the terminal and Telegram
# call handle_command(), so the behavior is identical everywhere.

from config import MODEL_NAME, OLLAMA_MODEL
from core import connectivity
from core.suggestions import find_suggestion
from memory import archive, long_term

HELP = (
    "Commands:\n"
    "/status  show which brain is in use\n"
    "/brain auto|groq|ollama  choose the brain (auto = Groq online, local model offline)\n"
    "/model default|fast|research  choose the model profile\n"
    "/suggest <text>  look for a relevant past workflow or memory\n"
    "/memory list|search <text>|forget <id>  manage curated memories\n"
    "/archive search <text>  search archived conversations and research\n"
    "/topic <name>  set the current conversation topic\n"
    "/project <name>  set the current project context\n"
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

    if command == "/memory":
        if not args or args[0].lower() == "help":
            return "Usage: /memory list, /memory search <text>, /memory forget <id>"
        action = args[0].lower()
        if action == "list":
            rows = long_term.list_memories()
            return "No confirmed memories." if not rows else "\n".join(
                "[{}] {} ({})".format(row["id"], row["content"], row["category"])
                for row in rows
            )
        if action == "search" and len(args) > 1:
            rows = long_term.search_memories(" ".join(args[1:]))
            return "No matching memories." if not rows else "\n".join(
                "[{}] {}".format(row["id"], row["content"]) for row in rows
            )
        if action == "forget" and len(args) == 2 and args[1].isdigit():
            return "Memory deleted." if long_term.forget_memory(int(args[1])) else "Memory not found."
        return "Usage: /memory list, /memory search <text>, /memory forget <id>"

    if command == "/archive":
        if len(args) < 2 or args[0].lower() != "search":
            return "Usage: /archive search <text>"
        rows = archive.search_archive(" ".join(args[1:]))
        return "No archive matches." if not rows else "\n".join(
            "[{}] {}: {}".format(row["id"], row["kind"], row["content"][:300])
            for row in rows
        )

    if command == "/topic":
        if not args:
            return "Usage: /topic <name>"
        topic = " ".join(args)
        agent.memory.set_context(topic=topic)
        return "Conversation topic set to: {}".format(topic)

    if command == "/project":
        if not args:
            return "Usage: /project <name> (use /project none to clear it)"
        project = " ".join(args)
        agent.memory.set_context(project=None if project.lower() == "none" else project)
        return "Project context set to: {}".format(project)

    if command == "/status":
        groq_ok = connectivity.can_use_groq()
        return (
            f"Brain mode: {agent.llm.mode}\n"
            f"Groq reachable right now: {'yes' if groq_ok else 'no'}\n"
            f"Last brain used: {agent.llm.last_backend or 'none yet'}\n"
            f"Model profile: {agent.llm.profile}\n"
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

    if command == "/model":
        if not args:
            return "Current model profile: {}. Use /model default, /model fast, or /model research.".format(agent.llm.profile)
        try:
            agent.llm.set_profile(args[0].lower())
        except ValueError as error:
            return str(error)
        return "Model profile set to: {} ({}).".format(
            agent.llm.profile, agent.llm.selected_model()
        )

    if command == "/suggest":
        if not args:
            return "Usage: /suggest <what you are working on>"
        return find_suggestion(" ".join(args)) or "I do not have a relevant suggestion yet."

    return f"Unknown command {command}.\n{HELP}"
