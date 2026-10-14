import tempfile
from pathlib import Path

import memory.db as database
from memory.db import init_db
from tools import tasks


def test_task_lifecycle(monkeypatch):
    with tempfile.TemporaryDirectory() as folder:
        monkeypatch.setattr(database, "DB_PATH", Path(folder) / "tasks.db")
        init_db()

        created = tasks.add_task(
            "Ship Phase 1", priority="high", due_at="2099-01-02 09:30", project="Rubi"
        )
        assert "Task 1 created" in created
        assert "Ship Phase 1" in tasks.list_tasks()
        assert "high" in tasks.list_tasks()

        assert "updated" in tasks.update_task(1, status="in_progress")
        assert "in_progress" in tasks.list_tasks()
        assert "updated" in tasks.complete_task(1)
        assert "No matching tasks." in tasks.list_tasks()
        assert "done" in tasks.list_tasks("done")


def test_task_validation(monkeypatch):
    with tempfile.TemporaryDirectory() as folder:
        monkeypatch.setattr(database, "DB_PATH", Path(folder) / "tasks.db")
        init_db()
        assert "priority must" in tasks.add_task("Bad priority", priority="critical")
        assert "due_at must" in tasks.add_task("Bad date", due_at="tomorrow")
