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