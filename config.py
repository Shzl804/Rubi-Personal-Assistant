# config.py
import os
from pathlib import Path
from dotenv import load_dotenv

# Folder where this file lives = the project root. Using an absolute base path
# means the project works no matter which folder you launch it from.
BASE_DIR = Path(__file__).resolve().parent

# Read key=value lines from .env and put them into the environment (os.environ).
load_dotenv(BASE_DIR / ".env")

# ---------------------------------------------------------------------------
# Stage 1 settings
# ---------------------------------------------------------------------------
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
# Groq model settings. GROQ_MODEL is supported for clarity; MODEL_NAME remains
# accepted for backward compatibility. These settings never affect Ollama.
MODEL_NAME = os.getenv("GROQ_MODEL", os.getenv("MODEL_NAME", "qwen/qwen3.8-27b"))
FAST_MODEL_NAME = os.getenv("GROQ_FAST_MODEL", os.getenv("FAST_MODEL_NAME", MODEL_NAME))
RESEARCH_MODEL_NAME = os.getenv("GROQ_RESEARCH_MODEL", os.getenv("RESEARCH_MODEL_NAME", MODEL_NAME))

USER_NAME = "Shazi"                       # what Rubi calls you
DB_PATH = BASE_DIR / "memory" / "rubi.db"  # SQLite file

MAX_HISTORY = 20                # past messages kept in a session
MAX_TOOL_ROUNDS = 8             # raised from 5: file/command tasks often need several steps
REMINDER_CHECK_SECONDS = 20     # how often the scheduler checks for due reminders

# ---------------------------------------------------------------------------
# Stage 2 settings
# ---------------------------------------------------------------------------

# Rubi's file tools can ONLY read/write inside this folder (the "jail").
# Shell commands also start with this as their working directory.
WORKSPACE_DIR = Path.home() / "rubi_workspace"

# Audit log: one line per action Rubi takes (or is refused).
LOG_PATH = BASE_DIR / "logs" / "actions.log"

COMMAND_TIMEOUT = 30        # seconds before a running command is killed
MAX_OUTPUT_CHARS = 4000     # command output is cut to this length. Saves tokens and
                            # stops a huge output from flooding the conversation.
MAX_READ_CHARS = 20000      # max characters read_file returns
MAX_WRITE_CHARS = 100000    # max characters write_file/append_file will write

# --- Controlled browser -----------------------------------------------------
BROWSER_ENABLED = os.getenv("RUBI_BROWSER_ENABLED", "false").lower() == "true"
BROWSER_HEADLESS = os.getenv("RUBI_BROWSER_HEADLESS", "false").lower() == "true"
BROWSER_PROFILE_DIR = Path(os.getenv("RUBI_BROWSER_PROFILE_DIR", str(Path.home() / "rubi_workspace" / ".browser-profile")))

# --- WhatsApp Business Platform --------------------------------------------
WHATSAPP_ENABLED = os.getenv("WHATSAPP_ENABLED", "false").lower() == "true"
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_API_VERSION = os.getenv("WHATSAPP_API_VERSION", "v23.0")
WHATSAPP_ALLOWED_SENDERS = {item.strip() for item in os.getenv("WHATSAPP_ALLOWED_SENDERS", "").split(",") if item.strip()}

# Friendly name -> actual program name. Rubi can ONLY open apps listed here.
# That is deliberate: "open_app" must not become a way to run any program.
# Check that a program exists with:  which firefox
APP_ALIASES = {
    "browser": "firefox",
    "firefox": "firefox",
    "files": "nautilus",
    "terminal": "gnome-terminal",
    "calculator": "gnome-calculator",
    "text editor": "gnome-text-editor",   # use "gedit" on older Ubuntu versions
    "code": "code",
    "vscode": "code",
    "settings": "gnome-control-center",
}

if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY is missing. Put it in the .env file.")

# ---------------------------------------------------------------------------
# Stage 3 settings
# ---------------------------------------------------------------------------

# --- Telegram ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# Your NUMERIC Telegram user ID. We use the number, not your @username, because
# usernames can be changed or reassigned, but the numeric ID never changes.
# 0 means "not set yet" (the bot then starts in setup mode, see Step 14).
_raw_id = os.getenv("TELEGRAM_USER_ID", "").strip()
TELEGRAM_USER_ID = int(_raw_id) if _raw_id.isdigit() else 0

# OPTIONAL proxy used ONLY for Telegram traffic (see "Optional: use a proxy only for
# Telegram" below). Empty means "no proxy". Examples:
#   socks5://127.0.0.1:1080      http://127.0.0.1:8080
TELEGRAM_PROXY = os.getenv("TELEGRAM_PROXY", "").strip() or None

# If you do not tap Yes/No within this time, the request is treated as DENIED.
APPROVAL_TIMEOUT_SECONDS = 120

# --- Brain switching ---
GROQ_TIMEOUT = 20             # give up on Groq after this many seconds
GROQ_COOLDOWN_SECONDS = 45    # after a Groq failure, skip Groq for this long
INTERNET_CACHE_SECONDS = 15   # remember the "am I online?" result for this long

# ---------------------------------------------------------------------------
# Stage 5 settings (memory and research)
# ---------------------------------------------------------------------------
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
MEMORY_RETRIEVAL_LIMIT = 8
SHORT_TERM_MESSAGE_LIMIT = 20
ARCHIVE_CONVERSATIONS = True
SUGGESTIONS_ENABLED = False


# ---------------------------------------------------------------------------
# Stage 4 settings (voice)
# ---------------------------------------------------------------------------

# --- Audio format -----------------------------------------------------------
# Whisper and openWakeWord both expect 16 kHz, mono, 16-bit audio.
VOICE_SAMPLE_RATE = 16000
# Audio is processed in small blocks. 1280 samples = 80 ms, which is exactly the
# frame size openWakeWord wants, so we use it everywhere.
AUDIO_BLOCK = 1280
BLOCKS_PER_SECOND = VOICE_SAMPLE_RATE / AUDIO_BLOCK     # = 12.5 blocks per second
# None = system default microphone. To pick another one, run
#   python -c "import sounddevice as sd; print(sd.query_devices())"
# and put the device number here.
AUDIO_INPUT_DEVICE = None

# --- Speech to text ---------------------------------------------------------
# Groq model names change sometimes: check the models list in the Groq console.
GROQ_STT_MODEL = os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo")
# Local fallback. "small.en" (about 1 GB RAM) is a good balance on a CPU.
# Faster but less accurate: "base.en". Slower but better: "medium.en".
LOCAL_STT_MODEL = os.getenv("LOCAL_STT_MODEL", "small.en")

# --- Text to speech ---------------------------------------------------------
# ElevenLabs is used when an API key is configured; Piper remains the fallback.
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")
PIPER_VOICE_PATH = BASE_DIR / "voice" / "models" / "en_US-amy-medium.onnx"
SPEAK_MAX_CHARS = 500           # longer replies are shortened when SPOKEN (the text stays complete)

# --- Listening behaviour ----------------------------------------------------
MIN_SPEECH_RMS = 250            # never treat anything quieter than this as speech
SILENCE_SECONDS = 1.2           # this much quiet after speech = you finished your sentence
MAX_RECORD_SECONDS = 20         # hard limit for one utterance
WAIT_FOR_SPEECH_SECONDS = 6     # give up if nobody speaks within this time

# --- Ways to start a voice turn ---------------------------------------------
# Temporarily disabled to keep the voice path simple. Re-enable when the
# wake-word model is ready; Enter, /listen, and push-to-talk still work.
WAKE_WORD_ENABLED = False
WAKE_MODEL_PATH = BASE_DIR / "voice" / "models" / "rubi.onnx"   # your trained model (Step 12)
WAKE_THRESHOLD = 0.5            # 0 to 1. Lower = easier to trigger, but more false alarms
WAKE_BEEP = True                # short beep when the wake word is heard

PTT_ENABLED = True              # hold-to-talk key (works on X11 only, see Step 11)
PTT_KEY = "f9"

# --- Voice approvals --------------------------------------------------------
VOICE_APPROVALS = True          # allow saying "yes"/"no" to approve actions (typing always works)
VOICE_APPROVAL_TIMEOUT = 25     # seconds to answer before it counts as DENIED
