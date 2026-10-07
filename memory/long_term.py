from memory.db import db


ALLOWED_CATEGORIES = {
    "preference", "personal_fact", "project_decision", "workflow",
    "goal", "constraint", "correction",
}


def _check_category(category):
    if category not in ALLOWED_CATEGORIES:
        raise ValueError("category must be one of: {}".format(", ".join(sorted(ALLOWED_CATEGORIES))))


def add_memory(content, category="preference", topic=None, project=None,
               confidence=0.8, source="user"):
    _check_category(category)
    content = str(content).strip()
    if not content:
        raise ValueError("memory content cannot be empty")
    with db() as conn:
        existing = conn.execute(
            "SELECT id FROM memories WHERE content = ? AND status = 'confirmed'",
            (content,),
        ).fetchone()
        if existing:
            return int(existing["id"])
        cur = conn.execute(
            """INSERT INTO memories
               (content, category, topic, project, confidence, status, source)
               VALUES (?, ?, ?, ?, ?, 'confirmed', ?)""",
            (content, category, topic, project, max(0.0, min(1.0, float(confidence))), source),
        )
        return int(cur.lastrowid)


def propose_memory(content, category="preference", topic=None, project=None,
                   confidence=0.5, source="curator"):
    _check_category(category)
    with db() as conn:
        cur = conn.execute(
            """INSERT INTO memories
               (content, category, topic, project, confidence, status, source)
               VALUES (?, ?, ?, ?, ?, 'proposed', ?)""",
            (str(content).strip(), category, topic, project, confidence, source),
        )
        return int(cur.lastrowid)


def list_memories(limit=50, status="confirmed"):
    with db() as conn:
        rows = conn.execute(
            """SELECT * FROM memories WHERE status = ?
               ORDER BY updated_at DESC, id DESC LIMIT ?""",
            (status, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def search_memories(query, topic=None, project=None, limit=8):
    words = [word.lower() for word in str(query).split() if len(word) > 2][:8]
    if not words:
        return []
    clauses = ["LOWER(content) LIKE ?" for _ in words]
    params = ["%{}%".format(word) for word in words]
    scope = ["status = 'confirmed'", "({})".format(" OR ".join(clauses))]
    if topic:
        scope.append("(topic = ? OR topic IS NULL)")
        params.append(topic)
    if project:
        scope.append("(project = ? OR project IS NULL)")
        params.append(project)
    params.append(limit)
    with db() as conn:
        rows = conn.execute(
            """SELECT * FROM memories WHERE {} ORDER BY confidence DESC, id DESC LIMIT ?""".format(
                " AND ".join(scope)
            ),
            params,
        ).fetchall()
        for row in rows:
            conn.execute(
                "UPDATE memories SET last_used_at = CURRENT_TIMESTAMP WHERE id = ?",
                (row["id"],),
            )
    return [dict(row) for row in rows]


def forget_memory(memory_id):
    with db() as conn:
        cur = conn.execute(
            "UPDATE memories SET status = 'deleted', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (memory_id,),
        )
    return cur.rowcount > 0


def confirm_memory(memory_id):
    with db() as conn:
        cur = conn.execute(
            "UPDATE memories SET status = 'confirmed', updated_at = CURRENT_TIMESTAMP WHERE id = ? AND status = 'proposed'",
            (memory_id,),
        )
    return cur.rowcount > 0


def reject_memory(memory_id):
    with db() as conn:
        cur = conn.execute(
            "UPDATE memories SET status = 'rejected', updated_at = CURRENT_TIMESTAMP WHERE id = ? AND status = 'proposed'",
            (memory_id,),
        )
    return cur.rowcount > 0
