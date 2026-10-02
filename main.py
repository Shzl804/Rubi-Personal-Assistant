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