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