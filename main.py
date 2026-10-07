# main.py
#
# Usage:
#   python main.py            text terminal only (default)
#   python main.py voice      voice terminal (typing, wake word, push-to-talk, /listen)
#   python main.py telegram   Telegram only (use this for the background service)
#   python main.py both       text terminal + Telegram
#   python main.py all        voice terminal + Telegram

import sys
import threading

from config import WORKSPACE_DIR
from core import notifier
from memory.db import init_db
from scheduler.jobs import start_scheduler

MODES = ("terminal", "voice", "telegram", "both", "all")


def main():
    mode = sys.argv[1].lower() if len(sys.argv) > 1 else "terminal"
    if mode not in MODES:
        print(f"Usage: python main.py [{'|'.join(MODES)}]")
        return

    init_db()
    from memory.migrations import run_migrations
    run_migrations()
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

    # Where reminders are delivered (the Telegram sink is added later by the bot itself).
    notifier.add_sink(notifier.print_sink)
    notifier.add_sink(notifier.desktop_sink)

    scheduler = start_scheduler()
    try:
        if mode == "terminal":
            from interfaces import terminal
            terminal.run()

        elif mode == "voice":
            # Imported here, not at the top, so the other modes work even if the
            # audio libraries are not installed.
            from interfaces import voice_terminal
            voice_terminal.run()

        elif mode == "telegram":
            from interfaces import telegram_bot
            telegram_bot.run()

        else:  # "both" (text terminal + Telegram) or "all" (voice terminal + Telegram)
            from interfaces import telegram_bot
            if mode == "all":
                from interfaces import voice_terminal as local_interface
            else:
                from interfaces import terminal as local_interface

            if not telegram_bot.can_start():
                print("Telegram is not configured yet, starting the local interface only.\n")
                local_interface.run()
            else:
                # The local interface runs in a background thread, Telegram takes the main
                # thread (run_polling needs it). daemon=True: it ends when the program ends.
                threading.Thread(target=local_interface.run, daemon=True).start()
                telegram_bot.run()
    finally:
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    main()
