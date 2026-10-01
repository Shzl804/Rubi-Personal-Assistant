# tools/notes.py
from memory.db import db


def add_note(content: str) -> str:
    with db() as conn:
        cur = conn.execute("INSERT INTO notes (content) VALUES (?)", (content,))
        return f"Note saved with id {cur.lastrowid}."


def list_notes(limit: int = 20) -> str:
    limit = int(limit)
    with db() as conn:
        rows = conn.execute(
            "SELECT id, content, created_at FROM notes ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    if not rows:
        return "There are no notes yet."
    return "\n".join(f"[{r['id']}] {r['content']} (saved {r['created_at']} UTC)" for r in rows)


def search_notes(keyword: str) -> str:
    with db() as conn:
        rows = conn.execute(
            "SELECT id, content, created_at FROM notes WHERE content LIKE ? ORDER BY id DESC",
            (f"%{keyword}%",),
        ).fetchall()
    if not rows:
        return f"No notes found containing '{keyword}'."
    return "\n".join(f"[{r['id']}] {r['content']} (saved {r['created_at']} UTC)" for r in rows)


def delete_note(note_id: int) -> str:
    note_id = int(note_id)
    with db() as conn:
        cur = conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        if cur.rowcount == 0:
            return f"No note with id {note_id}."
        return f"Note {note_id} deleted."