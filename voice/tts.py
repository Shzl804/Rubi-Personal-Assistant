# voice/tts.py
#
# Text to speech with automatic online/offline switching.

import asyncio
import re
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from config import EDGE_VOICE, PIPER_VOICE_PATH, SPEAK_MAX_CHARS
from core import connectivity
from voice import audio

# All generated audio files live here and are deleted right after use.
TMP_DIR = Path(tempfile.gettempdir()) / "rubi_voice"
TMP_DIR.mkdir(parents=True, exist_ok=True)


def clean_for_speech(text: str) -> str:
    """Make a reply pleasant to listen to. The on-screen text is NOT changed."""
    text = re.sub(r"```.*?```", " (code left out) ", text, flags=re.S)  # do not read code blocks
    text = re.sub(r"https?://\S+", "a link", text)                       # do not spell out URLs
    text = re.sub(r"[*_#`>|~]", "", text)                                # markdown symbols
    text = re.sub(r"\s+", " ", text).strip()

    if len(text) > SPEAK_MAX_CHARS:
        # Cut at a word boundary, then say where the rest is.
        text = text[:SPEAK_MAX_CHARS].rsplit(" ", 1)[0] + ". I left out the rest, it is in the text."
    return text


async def _edge_save(text: str, path: Path) -> None:
    import edge_tts   # imported here so a missing package only breaks this path, not everything
    communicate = edge_tts.Communicate(text, EDGE_VOICE)
    # wait_for: never hang forever if the connection is poor.
    await asyncio.wait_for(communicate.save(str(path)), timeout=20)


def _synth_edge(text: str) -> Path:
    path = TMP_DIR / f"{uuid.uuid4().hex}.mp3"
    # asyncio.run() creates a fresh event loop. That is fine here because we are always
    # called from a plain thread (never from inside a running event loop).
    asyncio.run(_edge_save(text, path))
    return path


def _synth_piper(text: str) -> Path:
    if not PIPER_VOICE_PATH.exists():
        raise RuntimeError(f"Piper voice file not found: {PIPER_VOICE_PATH} (see Step 9)")
    path = TMP_DIR / f"{uuid.uuid4().hex}.wav"
    try:
        # The text is sent on stdin. -m = voice model, -f = output file.
        subprocess.run(
            [sys.executable, "-m", "piper", "-m", str(PIPER_VOICE_PATH), "-f", str(path)],
            input=text, text=True, capture_output=True, timeout=60, check=True,
        )
    except subprocess.CalledProcessError as error:
        raise RuntimeError(f"Piper failed: {(error.stderr or '')[-300:]}") from error
    return path


def synthesize(text: str, force_local: bool = False) -> Path:
    """
    Turn text into an audio file and return its path (the caller deletes it).
    edge-tts first (needs internet and sends the text to Microsoft), Piper otherwise.
    """
    text = clean_for_speech(text)
    if not text:
        raise ValueError("there is nothing to say")

    if not force_local and connectivity.has_internet():
        try:
            return _synth_edge(text)
        except Exception as error:
            print(f"   [voice] online voice failed ({type(error).__name__}); using the offline voice")

    return _synth_piper(text)


def speak(text: str, force_local: bool = False) -> None:
    """Say the text out loud and wait until finished."""
    path = synthesize(text, force_local)
    try:
        audio.play_file(path)
    finally:
        path.unlink(missing_ok=True)      # always clean up the temporary file


def to_ogg_opus(path: Path) -> Path:
    """Convert to OGG/Opus, the format Telegram voice notes use."""
    out = path.with_suffix(".ogg")
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(path), "-c:a", "libopus", "-b:a", "32k", str(out)],
        check=True, timeout=30, stdin=subprocess.DEVNULL,
    )
    return out