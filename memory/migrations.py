from memory.db import db


def run_migrations():
    """Record the schema generation without changing existing user data."""
    with db() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)")
        row = conn.execute(
            "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
        ).fetchone()
        if row is None:
            conn.execute("INSERT INTO schema_version(version) VALUES (1)")
