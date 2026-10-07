# memory/db.py
import sqlite3
from contextlib import contextmanager

from config import DB_PATH


@contextmanager
def db():
    """Open a connection, commit if all went well, always close it."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row   # lets us read columns by name
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    """Create the existing tables and the Stage 5 memory tables."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                content    TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                text       TEXT NOT NULL,
                remind_at  TEXT NOT NULL,
                done       INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id         TEXT PRIMARY KEY,
                topic      TEXT,
                project    TEXT,
                summary    TEXT NOT NULL DEFAULT '',
                started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role       TEXT NOT NULL,
                content    TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(session_id) REFERENCES sessions(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                content      TEXT NOT NULL,
                category     TEXT NOT NULL,
                topic        TEXT,
                project      TEXT,
                confidence   REAL NOT NULL DEFAULT 0.5,
                status       TEXT NOT NULL DEFAULT 'confirmed',
                source       TEXT,
                created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_used_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS archive_items (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                kind       TEXT NOT NULL,
                title      TEXT,
                content    TEXT NOT NULL,
                topic      TEXT,
                project    TEXT,
                source     TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS research_sources (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                archive_id    INTEGER,
                title         TEXT,
                url           TEXT NOT NULL,
                publisher     TEXT,
                snippet       TEXT,
                retrieved_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(archive_id) REFERENCES archive_items(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_scope ON memories(topic, project, status)")
