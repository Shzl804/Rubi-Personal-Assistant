# config.py
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "openai/gpt-oss-120b")

USER_NAME = "Shazi"          # change to what you want Jarvis to call you
DB_PATH = BASE_DIR / "memory" / "Rubi.db"

MAX_HISTORY = 20             # how many past messages to remember in a session
MAX_TOOL_ROUNDS = 5          # safety limit: max tool calls in one request
REMINDER_CHECK_SECONDS = 20  # how often to check for due reminders

if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY is missing. Put it in the .env file.")