import tempfile
from pathlib import Path

import memory.db as database
from memory.db import init_db
from tools import calendar


def main():
    with tempfile.TemporaryDirectory() as folder:
        database.DB_PATH = Path(folder) / "calendar.db"
        init_db()
        assert "created" in calendar.add_event("Planning", "2099-01-02 09:00", "2099-01-02 10:00")
        assert "Conflict" in calendar.add_event("Overlap", "2099-01-02 09:30", "2099-01-02 10:30")
        assert "Busy" in calendar.check_availability("2099-01-02 09:15", "2099-01-02 09:45")
        assert "Planning" in calendar.agenda("2099-01-02")
        assert "cancelled" in calendar.cancel_event(1)
        assert "Available" in calendar.check_availability("2099-01-02 09:15", "2099-01-02 09:45")
    print("calendar smoke tests passed")


if __name__ == "__main__":
    main()
