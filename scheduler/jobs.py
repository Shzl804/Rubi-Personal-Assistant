# scheduler/jobs.py
import subprocess

from apscheduler.schedulers.background import BackgroundScheduler

from config import REMINDER_CHECK_SECONDS
from tools.reminders import pop_due_reminders


def check_reminders():
    for reminder in pop_due_reminders():
        print(f"\n\n*** REMINDER: {reminder['text']}  (was set for {reminder['remind_at']}) ***")
        print("You: ", end="", flush=True)   # redraw the input prompt (cosmetic)

        # Ubuntu desktop notification. Ignore if notify-send is not installed.
        try:
            subprocess.run(
                ["notify-send", "Rubi Reminder", reminder["text"]],
                check=False,
            )
        except FileNotFoundError:
            pass


def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_reminders, "interval", seconds=REMINDER_CHECK_SECONDS)
    scheduler.start()
    return scheduler