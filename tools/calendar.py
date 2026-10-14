from datetime import datetime, timedelta

from memory.db import db

TIME_FORMAT = "%Y-%m-%d %H:%M"


def _parse(value, field):
    try:
        return datetime.strptime(str(value).strip(), TIME_FORMAT), None
    except (TypeError, ValueError):
        return None, f"Error: {field} must be YYYY-MM-DD HH:MM (24-hour clock)."


def _format(row):
    extra = []
    if row["location"]:
        extra.append(row["location"])
    if row["project"]:
        extra.append("project " + row["project"])
    suffix = " — " + ", ".join(extra) if extra else ""
    return f"[{row['id']}] {row['starts_at']}–{row['ends_at']}  {row['title']}{suffix}"


def _conflicts(conn, starts_at, ends_at, exclude_id=None):
    query = (
        "SELECT id, title, starts_at, ends_at FROM calendar_events "
        "WHERE status = 'scheduled' AND starts_at < ? AND ends_at > ?"
    )
    params = [ends_at, starts_at]
    if exclude_id is not None:
        query += " AND id != ?"
        params.append(exclude_id)
    return conn.execute(query, params).fetchall()


def add_event(title, starts_at, ends_at=None, description="", location="", project=None):
    title = str(title).strip()
    if not title:
        return "Error: event title cannot be empty."
    starts, error = _parse(starts_at, "starts_at")
    if error:
        return error
    if ends_at:
        ends, error = _parse(ends_at, "ends_at")
        if error:
            return error
    else:
        ends = starts + timedelta(hours=1)
    if ends <= starts:
        return "Error: ends_at must be after starts_at."
    starts_value, ends_value = starts.strftime(TIME_FORMAT), ends.strftime(TIME_FORMAT)
    with db() as conn:
        conflicts = _conflicts(conn, starts_value, ends_value)
        if conflicts:
            conflict_text = ", ".join(f"#{row['id']} {row['title']}" for row in conflicts)
            return f"Conflict: this overlaps {conflict_text}. Event was not created."
        cur = conn.execute(
            "INSERT INTO calendar_events (title, description, starts_at, ends_at, location, project) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (title, str(description or "").strip(), starts_value, ends_value, str(location or "").strip(), project),
        )
    return f"Calendar event {cur.lastrowid} created: {title} ({starts_value}–{ends_value})"


def list_events(start_at=None, end_at=None, limit=50):
    start = start_at or "0001-01-01 00:00"
    end = end_at or "9999-12-31 23:59"
    start_value, error = _parse(start, "start_at")
    if error:
        return error
    end_value, error = _parse(end, "end_at")
    if error:
        return error
    if end_value <= start_value:
        return "Error: end_at must be after start_at."
    limit = max(1, min(int(limit), 200))
    with db() as conn:
        rows = conn.execute(
            "SELECT id, title, starts_at, ends_at, location, project FROM calendar_events "
            "WHERE status = 'scheduled' AND starts_at < ? AND ends_at > ? "
            "ORDER BY starts_at LIMIT ?",
            (end_value.strftime(TIME_FORMAT), start_value.strftime(TIME_FORMAT), limit),
        ).fetchall()
    return "No calendar events." if not rows else "\n".join(_format(row) for row in rows)


def agenda(date=None):
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    try:
        day = datetime.strptime(str(date).strip(), "%Y-%m-%d")
    except ValueError:
        return "Error: date must be YYYY-MM-DD."
    return list_events(day.strftime(TIME_FORMAT), (day + timedelta(days=1)).strftime(TIME_FORMAT))


def check_availability(starts_at, ends_at):
    starts, error = _parse(starts_at, "starts_at")
    if error:
        return error
    ends, error = _parse(ends_at, "ends_at")
    if error:
        return error
    if ends <= starts:
        return "Error: ends_at must be after starts_at."
    with db() as conn:
        conflicts = _conflicts(conn, starts.strftime(TIME_FORMAT), ends.strftime(TIME_FORMAT))
    if conflicts:
        return "Busy: " + ", ".join(f"#{row['id']} {row['title']}" for row in conflicts)
    return "Available: no calendar conflicts."


def cancel_event(event_id):
    with db() as conn:
        cur = conn.execute(
            "UPDATE calendar_events SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ? AND status = 'scheduled'", (int(event_id),)
        )
    return f"Calendar event {event_id} cancelled." if cur.rowcount else f"No scheduled event with id {event_id}."
