from datetime import datetime

from memory.db import db

TIME_FORMAT = "%Y-%m-%d %H:%M"
STATUSES = {"todo", "in_progress", "done", "cancelled"}
PRIORITIES = {"low", "normal", "high", "urgent"}


def _parse_due(due_at):
    if not due_at:
        return None, None
    try:
        value = datetime.strptime(str(due_at).strip(), TIME_FORMAT)
    except ValueError:
        return None, "Error: due_at must be YYYY-MM-DD HH:MM (24-hour clock)."
    return value.strftime(TIME_FORMAT), None


def add_task(title, description="", priority="normal", due_at=None, project=None):
    title = str(title).strip()
    priority = str(priority or "normal").lower().strip()
    if not title:
        return "Error: task title cannot be empty."
    if priority not in PRIORITIES:
        return "Error: priority must be low, normal, high, or urgent."
    due_value, error = _parse_due(due_at)
    if error:
        return error
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO tasks (title, description, priority, due_at, project) VALUES (?, ?, ?, ?, ?)",
            (title, str(description or "").strip(), priority, due_value, project),
        )
    return f"Task {cur.lastrowid} created: {title}"


def list_tasks(status="open", project=None, limit=50):
    status = str(status or "open").lower()
    limit = max(1, min(int(limit), 200))
    clauses, params = [], []
    if status == "open":
        clauses.append("status IN ('todo', 'in_progress')")
    elif status != "all":
        if status not in STATUSES:
            return "Error: status must be open, all, todo, in_progress, done, or cancelled."
        clauses.append("status = ?")
        params.append(status)
    if project:
        clauses.append("project = ?")
        params.append(project)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with db() as conn:
        rows = conn.execute(
            "SELECT id, title, status, priority, due_at, project FROM tasks" + where +
            " ORDER BY CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 "
            "WHEN 'normal' THEN 2 ELSE 3 END, due_at IS NULL, due_at, id DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
    if not rows:
        return "No matching tasks."
    lines = []
    for row in rows:
        details = [row["status"], row["priority"]]
        if row["due_at"]:
            details.append("due " + row["due_at"])
        if row["project"]:
            details.append("project " + row["project"])
        lines.append(f"[{row['id']}] {row['title']} ({', '.join(details)})")
    return "\n".join(lines)


def update_task(task_id, status=None, priority=None, title=None, due_at=None, project=None):
    task_id = int(task_id)
    updates, params = [], []
    if status is not None:
        status = str(status).lower().strip()
        if status not in STATUSES:
            return "Error: status must be todo, in_progress, done, or cancelled."
        updates += ["status = ?", "completed_at = ?"]
        params += [status, datetime.now().strftime(TIME_FORMAT) if status == "done" else None]
    if priority is not None:
        priority = str(priority).lower().strip()
        if priority not in PRIORITIES:
            return "Error: priority must be low, normal, high, or urgent."
        updates.append("priority = ?")
        params.append(priority)
    if title is not None:
        title = str(title).strip()
        if not title:
            return "Error: task title cannot be empty."
        updates.append("title = ?")
        params.append(title)
    if due_at is not None:
        due_value, error = _parse_due(due_at)
        if error:
            return error
        updates.append("due_at = ?")
        params.append(due_value)
    if project is not None:
        updates.append("project = ?")
        params.append(project)
    if not updates:
        return "Error: provide a task field to update."
    updates.append("updated_at = CURRENT_TIMESTAMP")
    with db() as conn:
        cur = conn.execute("UPDATE tasks SET " + ", ".join(updates) + " WHERE id = ?", (*params, task_id))
    return f"Task {task_id} updated." if cur.rowcount else f"No task with id {task_id}."


def complete_task(task_id):
    return update_task(task_id, status="done")


def delete_task(task_id):
    with db() as conn:
        cur = conn.execute("DELETE FROM tasks WHERE id = ?", (int(task_id),))
    return f"Task {task_id} deleted." if cur.rowcount else f"No task with id {task_id}."
