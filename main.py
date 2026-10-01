# main.py
from memory.db import init_db
from scheduler.jobs import start_scheduler
from interfaces.terminal import run


def main():
    init_db()
    scheduler = start_scheduler()
    try:
        run()
    finally:
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    main()