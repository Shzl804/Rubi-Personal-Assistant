# tools/reminders.py
from datetime import datetime

from memory.db import db

TIME_FORMAT = "%Y-%m-%d %H:%M"


def set_reminder(text: str, remind_at: str) -> str:
    try:
        when = datetime.strptime(remind_at.strip(), TIME_FORMAT)
    except ValueError:
        return "Error: remind_at must be in the format YYYY-MM-DD HH:MM (24-hour clock)."

    if when <= datetime.now():
        return "Error: that time is in the past. Ask the user for a future time."

    when_str = when.strftime(TIME_FORMAT)
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO reminders (text, remind_at) VALUES (?, ?)",
            (text, when_str),
        )
        return f"Reminder {cur.lastrowid} set for {when_str}: {text}"


def list_reminders() -> str:
    with db() as conn:
        rows = conn.execute(
            "SELECT id, text, remind_at FROM reminders WHERE done = 0 ORDER BY remind_at"
        ).fetchall()
    if not rows:
        return "There are no pending reminders."
    return "\n".join(f"[{r['id']}] {r['remind_at']}  {r['text']}" for r in rows)


def cancel_reminder(reminder_id: int) -> str:
    reminder_id = int(reminder_id)
    with db() as conn:
        cur = conn.execute(
            "UPDATE reminders SET done = 1 WHERE id = ? AND done = 0", (reminder_id,)
        )
        if cur.rowcount == 0:
            return f"No pending reminder with id {reminder_id}."
        return f"Reminder {reminder_id} cancelled."


def pop_due_reminders() -> list:
    """Return reminders that are due now, and mark them as done."""
    now = datetime.now().strftime(TIME_FORMAT)
    with db() as conn:
        rows = conn.execute(
            "SELECT id, text, remind_at FROM reminders WHERE done = 0 AND remind_at <= ?",
            (now,),
        ).fetchall()
        due = [dict(r) for r in rows]
        if due:
            conn.executemany(
                "UPDATE reminders SET done = 1 WHERE id = ?",
                [(r["id"],) for r in due],
            )
    return due
