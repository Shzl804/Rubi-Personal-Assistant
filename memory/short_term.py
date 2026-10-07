import uuid

from memory.db import db, init_db


class ShortTermMemory:
    def __init__(self, session_id=None):
        init_db()
        self.session_id = session_id or uuid.uuid4().hex
        with db() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO sessions(id) VALUES (?)",
                (self.session_id,),
            )

    def set_context(self, topic=None, project=None):
        with db() as conn:
            conn.execute(
                """UPDATE sessions SET topic = COALESCE(?, topic),
                   project = COALESCE(?, project), updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (topic, project, self.session_id),
            )

    def add_message(self, role, content):
        with db() as conn:
            conn.execute(
                "INSERT INTO messages(session_id, role, content) VALUES (?, ?, ?)",
                (self.session_id, role, str(content)),
            )
            conn.execute(
                "UPDATE sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (self.session_id,),
            )

    def recent_messages(self, limit=20):
        with db() as conn:
            rows = conn.execute(
                """SELECT role, content, created_at FROM messages
                   WHERE session_id = ? ORDER BY id DESC LIMIT ?""",
                (self.session_id, limit),
            ).fetchall()
        return list(reversed([dict(row) for row in rows]))

    def context(self):
        with db() as conn:
            row = conn.execute(
                "SELECT topic, project, summary FROM sessions WHERE id = ?",
                (self.session_id,),
            ).fetchone()
        return {
            "session_id": self.session_id,
            "topic": row["topic"] if row else None,
            "project": row["project"] if row else None,
            "summary": row["summary"] if row else "",
            "messages": self.recent_messages(),
        }

    def set_summary(self, summary):
        with db() as conn:
            conn.execute(
                """UPDATE sessions SET summary = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (summary.strip(), self.session_id),
            )


def summarize_messages(messages, max_chars=1800):
    """Create a deterministic summary until a dedicated summarizer is added."""
    lines = []
    for message in messages[-12:]:
        text = str(message.get("content", "")).strip()
        if text:
            lines.append("{}: {}".format(message.get("role", "unknown").upper(), text))
    summary = "\n".join(lines)
    return summary if len(summary) <= max_chars else summary[-max_chars:]
