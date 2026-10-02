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