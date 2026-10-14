from datetime import datetime, timedelta

from memory.db import db
from tools.calendar import agenda

DATE_FORMAT = "%Y-%m-%d"
TIME_FORMAT = "%Y-%m-%d %H:%M"


def _date_value(date):
    if date:
        try:
            return datetime.strptime(str(date).strip(), DATE_FORMAT)
        except ValueError:
            return None
    return datetime.now()


def daily_briefing(date=None):
    day = _date_value(date)
    if day is None:
        return "Error: date must be YYYY-MM-DD."
    day_start = day.strftime(TIME_FORMAT)
    day_end = (day + timedelta(days=1)).strftime(TIME_FORMAT)
    date_label = day.strftime(DATE_FORMAT)

    with db() as conn:
        overdue = conn.execute(
            "SELECT id, title, priority, due_at FROM tasks "
            "WHERE status IN ('todo', 'in_progress') AND due_at IS NOT NULL AND due_at < ? "
            "ORDER BY due_at, id", (day_start,)
        ).fetchall()
        due_today = conn.execute(
            "SELECT id, title, status, priority, due_at FROM tasks "
            "WHERE status IN ('todo', 'in_progress') AND due_at >= ? AND due_at < ? "
            "ORDER BY due_at, id", (day_start, day_end)
        ).fetchall()
        upcoming = conn.execute(
            "SELECT id, title, status, priority, due_at FROM tasks "
            "WHERE status IN ('todo', 'in_progress') AND due_at >= ? AND due_at < ? "
            "ORDER BY due_at, id LIMIT 10", (day_end, (day + timedelta(days=8)).strftime(TIME_FORMAT))
        ).fetchall()
        reminders = conn.execute(
            "SELECT id, text, remind_at FROM reminders WHERE done = 0 AND remind_at < ? "
            "ORDER BY remind_at", (day_end,)
        ).fetchall()

    lines = [f"Rubi daily briefing — {date_label}", ""]
    lines.append("Calendar")
    calendar_text = agenda(date_label)
    lines.append(calendar_text if calendar_text != "No calendar events." else "No events scheduled.")

    lines.extend(["", "Tasks"])
    if overdue:
        lines.append("Overdue:")
        lines.extend(f"- [{row['id']}] {row['title']} ({row['priority']}, due {row['due_at']})" for row in overdue)
    if due_today:
        lines.append("Due today:")
        lines.extend(f"- [{row['id']}] {row['title']} ({row['status']}, {row['priority']})" for row in due_today)
    if not overdue and not due_today:
        lines.append("No overdue or due-today tasks.")

    lines.extend(["", "Reminders"])
    if reminders:
        lines.extend(f"- [{row['id']}] {row['remind_at']}  {row['text']}" for row in reminders)
    else:
        lines.append("No pending reminders before the end of the day.")

    if upcoming:
        lines.extend(["", "Coming up next 7 days"])
        lines.extend(f"- [{row['id']}] {row['due_at']}  {row['title']}" for row in upcoming)

    return "\n".join(lines)
