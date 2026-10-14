import tempfile
from pathlib import Path

import memory.db as database
from memory.db import init_db
from tools import briefing, calendar, tasks


def main():
    with tempfile.TemporaryDirectory() as folder:
        database.DB_PATH = Path(folder) / "briefing.db"
        init_db()
        tasks.add_task("Finish report", priority="high", due_at="2026-10-08 17:00")
        tasks.add_task("Old task", due_at="2026-10-07 17:00")
        calendar.add_event("Team meeting", "2026-10-08 10:00", "2026-10-08 11:00")
        result = briefing.daily_briefing("2026-10-08")
        assert "Team meeting" in result
        assert "Finish report" in result
        assert "Old task" in result
        assert "Overdue" in result
    print("briefing smoke tests passed")


if __name__ == "__main__":
    main()
