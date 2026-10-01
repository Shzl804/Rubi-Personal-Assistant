# interfaces/terminal.py
from core.agent import Agent


def run():
    agent = Agent()
    print("Rubi online. Type 'exit' to quit.\n")

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

        reply = agent.chat(user_text)
        print(f"Rubi: {reply}\n")