from memory.db import db


def save_archive(kind, content, title=None, topic=None, project=None, source=None):
    with db() as conn:
        cur = conn.execute(
            """INSERT INTO archive_items(kind, title, content, topic, project, source)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (kind, title, str(content), topic, project, source),
        )
        return int(cur.lastrowid)


def search_archive(query, kind=None, limit=10):
    params = ["%{}%".format(str(query).strip())]
    kind_filter = ""
    if kind:
        kind_filter = " AND kind = ?"
        params.append(kind)
    params.append(limit)
    with db() as conn:
        rows = conn.execute(
            """SELECT * FROM archive_items
               WHERE content LIKE ?{} ORDER BY id DESC LIMIT ?""".format(kind_filter),
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def save_source(archive_id, title, url, publisher=None, snippet=None):
    with db() as conn:
        cur = conn.execute(
            """INSERT INTO research_sources
               (archive_id, title, url, publisher, snippet)
               VALUES (?, ?, ?, ?, ?)""",
            (archive_id, title, url, publisher, snippet),
        )
        return int(cur.lastrowid)
