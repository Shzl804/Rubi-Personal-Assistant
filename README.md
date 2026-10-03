# Rubi Assistant: Stage 4 Build Guide (Voice)

**Goal of Stage 4:** you can **talk** to Rubi and Rubi **talks back**, using the same online/offline switching idea as Stage 3.

## What you chose (and what it means)

| Decision | Your choice | What gets built |
|---|---|---|
| Language | English only | Smaller, faster, more accurate English-only speech models |
| Hearing (speech-to-text) | Groq Whisper online + local faster-whisper offline | Online: Groq `whisper-large-v3-turbo`. Offline or Groq down: local `small.en` on your CPU |
| Speaking (text-to-speech) | edge-tts online + Piper offline | Online: natural Microsoft voice. Offline: Piper |
| Voice style | Female, American | edge-tts `en-US-JennyNeural`, Piper `en_US-amy-medium` |
| Ways to start talking | All four | Wake word, push-to-talk, a terminal command, Telegram voice messages |
| When Rubi speaks | Only when you spoke by voice | Typed message gives a text reply. Voice gives a spoken reply (a voice note on Telegram) |
| Wake word | Custom "Rubi" | You train a custom model (Step 12). Until then a built-in "hey jarvis" model lets you test everything |
| Voice approvals | Also allow saying yes/no out loud | Voice and typing both work, with safeguards (see Security) |
| RAM | 16 GB, about 12 GB usable | `small.en` Whisper (about 1 GB) fits next to your Ollama model |

**What stays the same:** `tools/` and the safety rules do not change. Voice is "just another interface," exactly like Telegram was.

**How to use this guide:** same method as before. Each step says what the file must do, then the full code follows, with many comments. Test each piece on its own before connecting the next one.

---

## Table of Contents

1. The big picture
2. Concepts you need first
3. New project structure
4. Steps 1 to 16
5. Testing
6. Troubleshooting
7. Security and privacy notes
8. Stage 4 checklist and what comes next

---

## 1. The big picture

```
                      ONLINE                               OFFLINE
 Microphone --> [speech to text] Groq Whisper   or   local faster-whisper (small.en)
                         |
                         v
                  core/agent.py  (the brain you already built: Groq or Ollama)
                         |
                         v
 Speaker   <-- [text to speech]  edge-tts        or   Piper (local)

 How a voice turn starts:
   1. Wake word     "Rubi"  (openWakeWord, always listening locally, nothing leaves your laptop)
   2. Push-to-talk  hold F9 (X11) or press Enter on an empty line
   3. Terminal      type /listen
   4. Telegram      send a voice message
```

**Rule for speaking:** typed input gets a text reply. Voice input gets a text reply on screen **and** a spoken reply.

---

## 2. Concepts you need first

| Term | Simple meaning |
|---|---|
| **Sample rate** | How many audio measurements per second. Speech models want **16,000 per second (16 kHz)** |
| **Mono, 16-bit PCM** | One audio channel, each measurement is a whole number from -32768 to 32767. That is the raw format all our code uses |
| **Block** | A small chunk of audio. We read **1280 samples = 80 ms** at a time (the exact size the wake-word model wants) |
| **RMS** | A number for how loud a block is (root mean square). Quiet room is small, speech is large |
| **VAD (voice activity detection)** | Deciding "is someone speaking right now?". We use a simple version: louder than a threshold means speech, and a stretch of quiet after speech means the sentence ended |
| **Wake word** | A tiny model that listens to every block and only reacts to one phrase. **openWakeWord** does this fully on your laptop |
| **STT (speech-to-text)** | Audio in, text out. **Whisper** is the model family. Groq runs a big one for you online. **faster-whisper** runs a small one locally |
| **TTS (text-to-speech)** | Text in, audio out. **edge-tts** uses Microsoft's online voices. **Piper** runs locally |
| **Pre-roll** | We keep the last ~0.3 s of audio from *before* speech was detected, so the first syllable is not cut off |

### Why the voice terminal is single-threaded (important design decision)

In Stage 3 the terminal used `input()`, which blocks. Now we also need to listen to the microphone. If one thread blocks on `input()` and another thread also reads the keyboard (for example to ask "yes/no" by voice or typing), two threads fight over the same keyboard stream and lines get swallowed.

**Solution:** one loop that never blocks on the keyboard. It repeatedly:
1. checks with `select()` whether you typed a line,
2. reads one 80 ms audio block and checks for the wake word or push-to-talk,
3. when something triggers, handles that whole turn (listen, transcribe, think, speak), then continues.

This is a classic **polling loop**, and it also makes approvals easy: the approver uses the same trick to wait for *either* your voice *or* a typed answer.

---

## 3. New project structure

`NEW` = new file, `CHANGED` = you edit or replace it.

```
rubi/
├── .env                        # CHANGED (optional new keys)
├── .gitignore                  # CHANGED (voice/models/)
├── requirements.txt            # CHANGED (7 new packages)
├── config.py                   # CHANGED (voice settings)
├── main.py                     # CHANGED (new modes: voice, all)
│
├── core/
│   └── connectivity.py         # CHANGED (adds has_internet())
│
├── voice/                      # NEW package: all audio code
│   ├── __init__.py
│   ├── audio.py                # microphone, loudness, recording, beep, playback
│   ├── stt.py                  # speech to text: Groq online, faster-whisper offline
│   ├── tts.py                  # text to speech: edge-tts online, Piper offline
│   ├── wakeword.py             # openWakeWord wrapper
│   ├── ptt.py                  # push-to-talk key (X11 only)
│   ├── selftest.py             # test each piece alone: mic, tts, stt, wake
│   └── models/                 # big files live here (not committed)
│       ├── en_US-amy-medium.onnx        # Piper voice (Step 9)
│       ├── en_US-amy-medium.onnx.json
│       └── rubi.onnx                    # your trained wake word (Step 12)
│
├── interfaces/
│   ├── voice_terminal.py       # NEW: the voice-enabled terminal loop
│   ├── terminal.py             # unchanged
│   └── telegram_bot.py         # CHANGED (voice messages: edits, not a full replacement)
│
└── tools/, memory/, scheduler/ # unchanged
```

---

## 4. Steps

### Step 1: Install system packages

**What to do:** Python audio libraries need a few Ubuntu packages.

- `ffmpeg`: plays sounds (`ffplay`) and converts audio (Telegram voice notes)
- `libportaudio2`: the library `sounddevice` uses to talk to your microphone and speakers
- `libsndfile1`: helps with audio files

```bash
sudo apt update
sudo apt install ffmpeg libportaudio2 libsndfile1 -y
ffplay -version | head -n 1
```

Check which display system you use (matters for push-to-talk in Step 11):

```bash
echo $XDG_SESSION_TYPE
```

It prints `x11` or `wayland`.

---

### Step 2: Install the Python packages

Add these lines to `requirements.txt` (keep the existing ones):

```
numpy
sounddevice
faster-whisper
edge-tts
piper-tts
openwakeword
pynput
```

| Package | Used for |
|---|---|
| `numpy` | audio as arrays of numbers |
| `sounddevice` | microphone input and beep output |
| `faster-whisper` | local speech-to-text (offline) |
| `edge-tts` | online text-to-speech |
| `piper-tts` | local text-to-speech (offline) |
| `openwakeword` | wake word detection |
| `pynput` | global push-to-talk key (X11 only) |

```bash
cd ~/rubi
source venv/bin/activate
pip install -r requirements.txt
```

> If `openwakeword` fails to install (often a complaint about `tflite-runtime` on newer Python versions), see Troubleshooting for a workaround.

---

### Step 3: Create the new files and folders

```bash
cd ~/rubi
mkdir -p voice/models
touch voice/__init__.py voice/audio.py voice/stt.py voice/tts.py
touch voice/wakeword.py voice/ptt.py voice/selftest.py
touch interfaces/voice_terminal.py
```

---

### Step 4: Settings, `.env`, `.gitignore`

**Add this block to the end of `config.py`** (anywhere below the existing settings):

```python
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
# List all edge-tts voices with:  edge-tts --list-voices
EDGE_VOICE = os.getenv("EDGE_VOICE", "en-US-JennyNeural")
PIPER_VOICE_PATH = BASE_DIR / "voice" / "models" / "en_US-amy-medium.onnx"
SPEAK_MAX_CHARS = 500           # longer replies are shortened when SPOKEN (the text stays complete)

# --- Listening behaviour ----------------------------------------------------
MIN_SPEECH_RMS = 250            # never treat anything quieter than this as speech
SILENCE_SECONDS = 1.2           # this much quiet after speech = you finished your sentence
MAX_RECORD_SECONDS = 20         # hard limit for one utterance
WAIT_FOR_SPEECH_SECONDS = 6     # give up if nobody speaks within this time

# --- Ways to start a voice turn ---------------------------------------------
WAKE_WORD_ENABLED = True
WAKE_MODEL_PATH = BASE_DIR / "voice" / "models" / "rubi.onnx"   # your trained model (Step 12)
WAKE_THRESHOLD = 0.5            # 0 to 1. Lower = easier to trigger, but more false alarms
WAKE_BEEP = True                # short beep when the wake word is heard

PTT_ENABLED = True              # hold-to-talk key (works on X11 only, see Step 11)
PTT_KEY = "f9"

# --- Voice approvals --------------------------------------------------------
VOICE_APPROVALS = True          # allow saying "yes"/"no" to approve actions (typing always works)
VOICE_APPROVAL_TIMEOUT = 25     # seconds to answer before it counts as DENIED
```

**`.gitignore`** (add one line):

```
.env
venv/
__pycache__/
*.db
logs/
voice/models/
```

`.env`: no changes needed. Optional overrides if you want them:

```
GROQ_STT_MODEL=whisper-large-v3-turbo
LOCAL_STT_MODEL=small.en
EDGE_VOICE=en-US-JennyNeural
```

---

### Step 5: Update `core/connectivity.py`

**What changes:** Stage 3 had one question, "can I use Groq?". Now we also need "do I have internet at all?" (for edge-tts, which has nothing to do with Groq or its cooldown). We split the two. The old function names still work, so `llm.py` does not change.

Replace the whole file:

```python
# core/connectivity.py
#
# Two separate questions:
#   has_internet()  -> is the network up at all?             (used by edge-tts)
#   can_use_groq()  -> internet up AND Groq not in cooldown   (used by the LLM and Whisper)

import socket
import time

from config import INTERNET_CACHE_SECONDS

# Probe raw IP addresses, not domain names: no DNS lookup means a fast failure when offline,
# and several targets mean one blocked address cannot fool us.
PROBES = [("1.1.1.1", 443), ("8.8.8.8", 53), ("9.9.9.9", 443)]

_net = {"online": True, "valid_until": 0.0}   # cached result of the probe
_groq = {"blocked_until": 0.0}                # "do not try Groq until this time"


def _probe() -> bool:
    """Try to open a TCP connection to each probe. One success means we have internet."""
    for host, port in PROBES:
        try:
            with socket.create_connection((host, port), timeout=2):
                return True
        except OSError:       # timeouts, "network unreachable", refused...
            continue
    return False


def has_internet() -> bool:
    """True if the network is up. Cached for a few seconds so we do not probe constantly."""
    now = time.time()
    if now < _net["valid_until"]:
        return _net["online"]

    online = _probe()
    _net["online"] = online
    _net["valid_until"] = now + INTERNET_CACHE_SECONDS
    return online


def can_use_groq() -> bool:
    """True if Rubi should try Groq right now."""
    if time.time() < _groq["blocked_until"]:
        return False                     # a real Groq request failed recently: skip for a while
    return has_internet()


def mark_unavailable(seconds: float) -> None:
    """Called when a REAL Groq request failed: skip Groq for 'seconds' seconds."""
    _groq["blocked_until"] = time.time() + seconds
```

---

### Step 6: Write `voice/audio.py`

**What this file must do:**
- `Microphone`: open/close the mic stream, read one 80 ms block
- `rms()`: how loud is a block
- `calibrate()`: measure room noise and set the "speech" threshold
- `record_utterance()`: record from the moment you start speaking until you stop (with pre-roll)
- `record_while()`: record while a key is held (push-to-talk)
- `to_wav_bytes()`: turn recorded numbers into a WAV file in memory
- `beep()` and `play_file()`

> `sounddevice` is imported **inside** functions on purpose. A Telegram-only background service may run on a machine with no audio device, and it must still be able to import this file.

```python
# voice/audio.py
#
# Everything that touches the microphone or speakers.

import io
import subprocess
import wave
from collections import deque

import numpy as np

from config import (
    AUDIO_BLOCK, AUDIO_INPUT_DEVICE, BLOCKS_PER_SECOND, MAX_RECORD_SECONDS,
    MIN_SPEECH_RMS, SILENCE_SECONDS, VOICE_SAMPLE_RATE, WAIT_FOR_SPEECH_SECONDS,
)

# How loud counts as "speech". calibrate() updates it; this is the safe default.
_vad = {"threshold": float(MIN_SPEECH_RMS)}

# Keep about 0.3 s of audio from BEFORE speech was detected (4 blocks x 80 ms),
# so the first syllable of your sentence is not cut off.
PREROLL_BLOCKS = 4


def rms(block: np.ndarray) -> float:
    """Loudness of a block: root mean square of the samples. Bigger = louder."""
    # Convert to float first: squaring int16 numbers would overflow.
    return float(np.sqrt(np.mean(block.astype(np.float32) ** 2)))


def to_wav_bytes(samples: np.ndarray) -> bytes:
    """Wrap raw samples in a WAV container (in memory). STT services expect a real audio file."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)                 # mono
        wav.setsampwidth(2)                 # 2 bytes = 16 bit
        wav.setframerate(VOICE_SAMPLE_RATE)
        wav.writeframes(samples.astype(np.int16).tobytes())
    return buffer.getvalue()


class Microphone:
    """A thin wrapper around sounddevice's InputStream."""

    def __init__(self):
        self.stream = None

    def start(self) -> None:
        """Open the microphone. Safe to call twice."""
        if self.stream is None:
            import sounddevice as sd      # imported here: see the note above the code
            self.stream = sd.InputStream(
                samplerate=VOICE_SAMPLE_RATE,
                channels=1,
                dtype="int16",
                blocksize=AUDIO_BLOCK,
                device=AUDIO_INPUT_DEVICE,
            )
            self.stream.start()

    def stop(self) -> None:
        """Close the microphone. Safe to call twice."""
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            finally:
                self.stream = None

    def read_block(self) -> np.ndarray:
        """Wait for and return the next 80 ms of audio (blocks for up to 80 ms)."""
        if self.stream is None:
            raise RuntimeError("The microphone is not started.")
        data, _overflowed = self.stream.read(AUDIO_BLOCK)    # shape (1280, 1)
        return data[:, 0].copy()                             # -> shape (1280,)

    def drain(self) -> None:
        """Throw away audio that piled up while we were busy doing something else."""
        if self.stream is not None:
            waiting = self.stream.read_available
            if waiting > 0:
                self.stream.read(waiting)


def calibrate(mic: Microphone, seconds: float = 1.0):
    """
    Measure the background noise for a moment (stay quiet!) and set the speech threshold
    to 3x the noise level. Returns (noise_level, threshold).
    """
    count = max(1, int(seconds * BLOCKS_PER_SECOND))
    levels = [rms(mic.read_block()) for _ in range(count)]
    noise = float(np.median(levels))       # median ignores a single loud click
    _vad["threshold"] = max(noise * 3.0, float(MIN_SPEECH_RMS))
    return noise, _vad["threshold"]


def record_utterance(mic: Microphone, abort_check=None,
                     wait_seconds: float = WAIT_FOR_SPEECH_SECONDS,
                     ignore_seconds: float = 0.0):
    """
    Record ONE sentence: wait until you start speaking, then record until you stop.

    abort_check   : optional function. If it returns True we stop at once and return None
                    (used so a typed answer can interrupt a spoken one).
    wait_seconds  : give up (return None) if nobody speaks within this time.
    ignore_seconds: discard this much audio first (used to skip the wake-word beep).

    Returns a numpy array of int16 samples, or None if nothing useful was heard.
    """
    threshold = _vad["threshold"]
    silence_limit = int(SILENCE_SECONDS * BLOCKS_PER_SECOND)   # quiet blocks that end a sentence
    wait_limit = int(wait_seconds * BLOCKS_PER_SECOND)
    max_blocks = int(MAX_RECORD_SECONDS * BLOCKS_PER_SECOND)

    # Throw away the first moments (for example our own beep).
    for _ in range(int(ignore_seconds * BLOCKS_PER_SECOND)):
        mic.read_block()

    preroll = deque(maxlen=PREROLL_BLOCKS)   # rolling window of the most recent quiet blocks
    blocks = []                              # the recording itself
    heard_speech = False
    silent = 0                               # consecutive quiet blocks AFTER speech started
    waited = 0                               # blocks waited BEFORE speech started

    while True:
        if abort_check is not None and abort_check():
            return None

        block = mic.read_block()
        loud = rms(block) > threshold

        if not heard_speech:
            if loud:
                heard_speech = True
                blocks = list(preroll) + [block]      # include the pre-roll
            else:
                preroll.append(block)
                waited += 1
                if waited >= wait_limit:
                    return None                       # nobody spoke
        else:
            blocks.append(block)
            silent = 0 if loud else silent + 1
            if silent >= silence_limit or len(blocks) >= max_blocks:
                break

    return np.concatenate(blocks)


def record_while(mic: Microphone, is_down):
    """
    Push-to-talk: record for as long as is_down() returns True (key held).
    Returns int16 samples, or None if the press was too short (under 0.4 s).
    """
    blocks = []
    max_blocks = int(MAX_RECORD_SECONDS * BLOCKS_PER_SECOND)
    while is_down() and len(blocks) < max_blocks:
        blocks.append(mic.read_block())

    if not blocks:
        return None
    samples = np.concatenate(blocks)
    if len(samples) < VOICE_SAMPLE_RATE * 0.4:
        return None
    return samples


def beep(wait: bool = True, freq: int = 880, seconds: float = 0.12) -> None:
    """A short 'ding' to say 'I am listening'."""
    import sounddevice as sd
    t = np.linspace(0, seconds, int(VOICE_SAMPLE_RATE * seconds), endpoint=False)
    # np.hanning fades the tone in and out so it does not click.
    tone = (0.3 * np.sin(2 * np.pi * freq * t) * np.hanning(len(t))).astype(np.float32)
    sd.play(tone, VOICE_SAMPLE_RATE)
    if wait:
        sd.wait()


def play_file(path) -> None:
    """Play an MP3 or WAV file and wait until it finishes. Uses ffplay (part of ffmpeg)."""
    subprocess.run(
        ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(path)],
        stdin=subprocess.DEVNULL,
        check=False,
    )
```

---

### Step 7: Write `voice/stt.py` (hearing, online and offline)

**What this file must do:**
- `transcribe(audio_bytes, filename, force_local)`: audio file bytes in, text out
- Use **Groq Whisper** when Groq is usable. If Groq is unavailable (offline, timeout, rate limit, server error), switch to the **local model** and avoid Groq for 45 seconds, exactly like the LLM router
- `force_local=True` (when you used `/brain ollama`) always uses the local model, so your voice never leaves the laptop
- Clean up Whisper's famous "ghost" phrases

The same function handles microphone recordings (WAV) **and** Telegram voice notes (OGG), because both Groq and faster-whisper accept audio file bytes.

```python
# voice/stt.py
#
# Speech to text with automatic online/offline switching.

import io

from groq import Groq

from config import (
    GROQ_API_KEY, GROQ_COOLDOWN_SECONDS, GROQ_STT_MODEL, GROQ_TIMEOUT, LOCAL_STT_MODEL,
)
from core import connectivity
from core.llm import GROQ_UNAVAILABLE_ERRORS   # the same "Groq is down" error list as the LLM router

# Same safety settings as the LLM client: fail fast so the fallback starts quickly.
_groq_client = Groq(api_key=GROQ_API_KEY, timeout=GROQ_TIMEOUT, max_retries=1)

# The local model is loaded on first use (it takes a few seconds and about 1 GB of RAM)
# and then kept in memory.
_local_model = None

# Whisper sometimes "hears" these phrases in silence or noise. They are not real speech.
JUNK_TRANSCRIPTS = {
    "", ".", "you", "thank you", "thank you.", "thanks for watching", "thanks for watching.",
    "thanks for watching!", "bye", "bye.",
}


def _get_local_model():
    global _local_model
    if _local_model is None:
        from faster_whisper import WhisperModel   # imported here so Groq-only use stays light
        print(f"   [voice] loading the local speech model '{LOCAL_STT_MODEL}' (first time only)...")
        # device="cpu", compute_type="int8": the smallest and fastest setup for a CPU.
        _local_model = WhisperModel(LOCAL_STT_MODEL, device="cpu", compute_type="int8")
    return _local_model


def _transcribe_groq(audio_bytes: bytes, filename: str) -> str:
    # file=(name, bytes): the filename's extension tells Groq the format (wav, ogg, mp3...).
    result = _groq_client.audio.transcriptions.create(
        file=(filename, audio_bytes),
        model=GROQ_STT_MODEL,
        language="en",         # English only: faster and avoids wrong language guesses
        temperature=0.0,       # most deterministic transcription
    )
    return result.text


def _transcribe_local(audio_bytes: bytes) -> str:
    model = _get_local_model()
    # faster-whisper decodes the audio itself, so file-like bytes are fine for wav and ogg.
    segments, _info = model.transcribe(
        io.BytesIO(audio_bytes),
        language="en",
        beam_size=5,
        vad_filter=True,       # skip silent parts: fewer ghost phrases
    )
    # 'segments' is a generator: it does the real work while we loop over it.
    return " ".join(segment.text.strip() for segment in segments)


def _clean(text: str) -> str:
    text = (text or "").strip()
    return "" if text.lower() in JUNK_TRANSCRIPTS else text


def transcribe(audio_bytes: bytes, filename: str = "speech.wav", force_local: bool = False) -> str:
    """Return the spoken text (empty string if nothing real was heard)."""
    use_groq = (not force_local) and connectivity.can_use_groq()

    if use_groq:
        try:
            return _clean(_transcribe_groq(audio_bytes, filename))
        except GROQ_UNAVAILABLE_ERRORS as error:
            connectivity.mark_unavailable(GROQ_COOLDOWN_SECONDS)
            print(f"   [voice] Groq speech-to-text unavailable ({type(error).__name__}); using the local model")

    return _clean(_transcribe_local(audio_bytes))


def warm_up() -> None:
    """Load (and, the first time, DOWNLOAD) the local model. Run once while online (Step 9)."""
    import numpy as np
    from voice import audio
    one_second_of_silence = np.zeros(16000, dtype=np.int16)
    _transcribe_local(audio.to_wav_bytes(one_second_of_silence))
    print("The local speech model is ready.")
```

---

### Step 8: Write `voice/tts.py` (speaking, online and offline)

**What this file must do:**
- `synthesize(text, force_local)`: text in, audio **file** out. Tries **edge-tts** when you have internet, and falls back to **Piper** on any failure
- `speak(text, force_local)`: synthesize, play, delete the file
- Clean text for speech (no markdown symbols, no URLs read out, no long code) and shorten long replies
- `to_ogg_opus()`: convert for Telegram voice notes

Piper is called through its **command line** (`python -m piper`) rather than its Python API, because the Python API has changed between Piper versions, while `-m model -f output.wav` with the text on stdin has stayed stable.

```python
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
```

---

### Step 9: Download the voice and models (do this while online)

**What to do:** three one-time downloads.

**A) The Piper voice** (female American, about 60 MB):

```bash
cd ~/rubi/voice/models
python -m piper.download_voices en_US-amy-medium
ls
```

You need both `en_US-amy-medium.onnx` and `en_US-amy-medium.onnx.json` in `~/rubi/voice/models/`. If that command does not exist in your Piper version, download the two files directly (the path layout follows Piper's voices repository; if you get a "not found", check the repository for the current path):

```bash
cd ~/rubi/voice/models
curl -L -O https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx
curl -L -O https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx.json
```

**B) The local Whisper model** (`small.en`, a few hundred MB, downloaded automatically from Hugging Face):

```bash
cd ~/rubi
source venv/bin/activate
python -c "from voice import stt; stt.warm_up()"
```

**C) openWakeWord's helper models** (small files the wake-word detector needs):

```bash
python -c "import openwakeword; openwakeword.utils.download_models()"
```

> If a download fails because a site is blocked or slow on your network, see Troubleshooting. After these three steps everything also works offline.

---

### Step 10: Write `voice/selftest.py` and test mic, speakers, hearing

**Why:** voice has many parts that can fail in different ways (microphone, speakers, models, network). Testing each one alone tells you *which* part is broken. That is the same "test one layer at a time" method as before.

**What this file must do:** four small tests you run one by one: `mic`, `tts`, `stt`, `wake`.

```python
# voice/selftest.py
#
# Run ONE test at a time, from the project folder:
#   python -m voice.selftest mic
#   python -m voice.selftest tts
#   python -m voice.selftest stt
#   python -m voice.selftest wake

import sys
import time

from voice import audio, stt, tts


def test_mic():
    """A live loudness bar for 8 seconds. Speak and watch it move."""
    mic = audio.Microphone()
    mic.start()
    print("Speak, clap, stay quiet... (8 seconds)\n")
    start = time.time()
    while time.time() - start < 8:
        level = audio.rms(mic.read_block())
        bar = "#" * int(min(level, 3000) / 60)
        print(f"\r{level:7.0f}  {bar:<50}", end="", flush=True)
    mic.stop()
    print("\n\nDid the bar move when you spoke? If not, pick another device (see Troubleshooting).")


def test_tts():
    """Speak once with the online voice, then once with the offline voice."""
    print("Online voice (edge-tts)... you should hear a voice.")
    tts.speak("Hello, I am Rubi. This is my online voice.")
    print("Offline voice (Piper)...")
    tts.speak("Hello, I am Rubi. This is my offline voice.", force_local=True)
    print("Done.")


def test_stt():
    """Record one sentence and transcribe it with Groq and with the local model."""
    mic = audio.Microphone()
    mic.start()
    print("Stay quiet for one second (measuring room noise)...")
    noise, threshold = audio.calibrate(mic)
    print(f"Noise level {noise:.0f}, speech threshold {threshold:.0f}")
    print("Now say a sentence...")
    samples = audio.record_utterance(mic, wait_seconds=8)
    mic.stop()
    if samples is None:
        print("No speech heard. Check the microphone with: python -m voice.selftest mic")
        return
    wav = audio.to_wav_bytes(samples)
    print("Groq (online) :", stt.transcribe(wav))
    print("Local (offline):", stt.transcribe(wav, force_local=True))


def test_wake():
    """Print the wake-word score live for 30 seconds."""
    from voice.wakeword import WakeWord
    mic = audio.Microphone()
    mic.start()
    wake = WakeWord()
    print("Say the wake word. Scores above 0.1 are printed. (30 seconds)\n")
    start = time.time()
    while time.time() - start < 30:
        score = wake.score(mic.read_block())
        if score > 0.1:
            print(f"score {score:.2f}" + ("   <-- TRIGGERED" if score >= 0.5 else ""))
    mic.stop()


TESTS = {"mic": test_mic, "tts": test_tts, "stt": test_stt, "wake": test_wake}

if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else ""
    if name not in TESTS:
        print("Usage: python -m voice.selftest [mic|tts|stt|wake]")
    else:
        TESTS[name]()
```

Run these now (the wake test comes after Step 11):

```bash
cd ~/rubi
source venv/bin/activate
python -m voice.selftest mic
python -m voice.selftest tts
python -m voice.selftest stt
```

**Check:** the bar moves when you speak, you hear both voices, and both transcripts match what you said. To test the fully offline path, turn Wi-Fi off and run `tts` and `stt` again; the online lines will fall back automatically.

To see all audio devices (if the wrong microphone is used):

```bash
python -c "import sounddevice as sd; print(sd.query_devices())"
```

Put the number of the right input device in `AUDIO_INPUT_DEVICE` in `config.py`.

---

### Step 11: Write `voice/wakeword.py` and `voice/ptt.py`

#### `voice/wakeword.py`

**What it must do:**
- Load your trained model (`rubi.onnx`) if it exists. Otherwise load the **built-in "hey jarvis"** model so you can test the whole pipeline today
- `detect(block)`: True when the wake word score passes the threshold
- `reset()`: clear its internal memory (needed after the mic was stopped)

```python
# voice/wakeword.py
#
# Wake word detection with openWakeWord. Runs fully on your laptop: audio is analysed
# in memory block by block and is never saved or sent anywhere.

from config import WAKE_MODEL_PATH, WAKE_THRESHOLD


class WakeWord:
    def __init__(self):
        from openwakeword.model import Model    # imported here: only needed in voice mode

        if WAKE_MODEL_PATH.exists():
            # Your own trained model (Step 12).
            self.model = Model(wakeword_models=[str(WAKE_MODEL_PATH)], inference_framework="onnx")
            self.custom = True
            print(f"   [voice] wake word model loaded: {WAKE_MODEL_PATH.name}")
        else:
            # No custom model yet: load the built-in ones and use only "hey jarvis".
            self.model = Model(inference_framework="onnx")
            self.custom = False
            print("   [voice] no custom wake word yet, so say 'hey jarvis' for now (train 'rubi' in Step 12)")

    def score(self, block) -> float:
        """How sure is the model (0 to 1) that the wake word was just said?"""
        # predict() wants 16 kHz int16 audio, 1280 samples at a time (our block size).
        scores = self.model.predict(block)       # dict: {model name: score}
        if self.custom:
            return float(max(scores.values()))   # only one model is loaded
        return float(max((v for k, v in scores.items() if "jarvis" in k.lower()), default=0.0))

    def detect(self, block) -> bool:
        return self.score(block) >= WAKE_THRESHOLD

    def reset(self) -> None:
        """Forget recent audio (otherwise old audio could trigger it again)."""
        try:
            self.model.reset()
        except AttributeError:       # older versions have no reset(): safe to skip
            pass
```

Test it now with the built-in word:

```bash
python -m voice.selftest wake
```

Say **"hey jarvis"**. You should see scores rise and `TRIGGERED` appear.

#### `voice/ptt.py`

**What it must do:** a **hold-to-talk** key (default `F9`) that works as a *global* hotkey (even when the terminal is not focused).

**Honest limitation:** global key capture works on **X11** only. On **Wayland** (Ubuntu's default on many systems) desktop apps are not allowed to read keys from other windows, and the workaround (reading `/dev/input`) needs extra permissions that would let any program read all your keystrokes. So on Wayland we deliberately use a safe alternative: **press Enter on an empty line in the terminal** to start listening (same as `/listen`).

```python
# voice/ptt.py
#
# Hold-to-talk key. X11 only (see the explanation above).

import os
import threading

from config import PTT_KEY


class HoldKey:
    def __init__(self, key_name: str = PTT_KEY):
        self._down = threading.Event()     # set while the key is held
        self.supported = False

        if os.environ.get("XDG_SESSION_TYPE", "").lower() != "x11":
            print(f"   [voice] push-to-talk key is off (not an X11 session). "
                  f"Press Enter on an empty line or type /listen instead.")
            return

        try:
            from pynput import keyboard
            key = getattr(keyboard.Key, key_name)      # e.g. keyboard.Key.f9

            def on_press(pressed):
                if pressed == key:
                    self._down.set()                    # holding the key repeats this: harmless

            def on_release(released):
                if released == key:
                    self._down.clear()

            # The listener runs in its own background thread.
            self._listener = keyboard.Listener(on_press=on_press, on_release=on_release)
            self._listener.daemon = True
            self._listener.start()
            self.supported = True
            print(f"   [voice] push-to-talk: hold {key_name.upper()} while you speak")
        except Exception as error:
            print(f"   [voice] push-to-talk unavailable: {error}")

    def is_down(self) -> bool:
        return self._down.is_set()
```

---

### Step 12: Train your custom "Rubi" wake word

**What this step is:** wake-word models are trained per phrase. There is no ready-made "Rubi", so you create one. openWakeWord provides an automated **training notebook** (Google Colab) that:

1. generates thousands of synthetic spoken examples of your phrase using text-to-speech,
2. mixes in background noise,
3. trains a small model and exports it as an `.onnx` file.

I have not verified the notebook's current details, so follow the instructions in its own text. The steps are:

1. Open the **openWakeWord GitHub page** and find the link to the **automatic model training** Colab notebook in its README or docs.
2. **Choose your phrase carefully. I recommend "hey rubi" (four syllables), not just "rubi".** Very short, common-sounding words trigger by accident (TV, music, "ruby", "movie"). A longer phrase is much more reliable.
3. In the notebook, set the target phrase and a model name (for example `hey_rubi`) and run all cells. A free Colab session typically needs about an hour or more.
4. If the trained model works poorly, retry with a **phonetic spelling** of the phrase (for example "hey roo bee"), because the synthetic voices read the written text.
5. Download the exported `.onnx` file and save it as:

```
~/rubi/voice/models/rubi.onnx
```

6. Test it:

```bash
cd ~/rubi
source venv/bin/activate
python -m voice.selftest wake
```

Say your phrase several times, then play music or a video with speech for a minute and see if it triggers by mistake. Tune `WAKE_THRESHOLD` in `config.py`:

| Symptom | Fix |
|---|---|
| It often does not react when you speak the phrase | Lower the threshold (try 0.4, then 0.3) |
| It triggers on TV, music or other words | Raise it (try 0.6, then 0.7), or retrain with a longer phrase |

> Until `rubi.onnx` exists, Rubi automatically uses the built-in "hey jarvis" word. You can finish and test everything else first.

---

### Step 13: Write `interfaces/voice_terminal.py`

**What this file must do:**
- Run the single-threaded loop from the concepts section: typed lines, wake word, push-to-talk, `/listen`
- A **voice turn**: record → transcribe → agent → print → **speak**
- A **typed turn**: text reply only (you said Rubi speaks only when you spoke by voice)
- A **voice approver**: speak a short summary, print the full text, accept a spoken **or** typed yes/no
- Respect `/brain ollama` (then speech-to-text and text-to-speech stay on the laptop)

```python
# interfaces/voice_terminal.py
#
# The voice-enabled terminal. ONE thread, never blocks on the keyboard.
# Each loop pass: (1) did you type a line? (2) did the mic hear a trigger?

import re
import select
import sys
import time

from config import (
    PTT_ENABLED, PTT_KEY, VOICE_APPROVALS, VOICE_APPROVAL_TIMEOUT,
    WAKE_BEEP, WAKE_WORD_ENABLED,
)
from core import safety
from core.agent import Agent
from core.commands import handle_command
from interfaces.terminal import terminal_approver
from voice import audio, stt, tts

# --- Words accepted as an answer to "Allow this?" -------------------------------
# EXACT match only (after cleaning). "yes but only if..." or a sentence that merely
# contains "yes" is NOT accepted: it counts as "unclear" and Rubi asks again.
YES_WORDS = {"yes", "yes please", "yeah", "yep", "allow", "allow it", "approve", "approved", "go ahead", "do it"}
NO_WORDS = {"no", "no thanks", "nope", "deny", "denied", "cancel", "stop", "dont", "do not", "dont do it"}


def stdin_ready() -> bool:
    """True if you pressed Enter and there is a typed line waiting. Never blocks."""
    # select() asks the OS "is there data to read?". The 0 means "do not wait".
    return bool(select.select([sys.stdin], [], [], 0)[0])


def prompt() -> None:
    print("You: ", end="", flush=True)


def normalize(text: str) -> str:
    """lowercase and keep only letters, spaces and apostrophes ('Yes!' -> 'yes')."""
    cleaned = re.sub(r"[^a-z' ]", "", text.lower()).replace("'", "")
    return cleaned.strip()


# =============================================================================
# The approver: voice OR typing
# =============================================================================

def make_voice_approver(mic: audio.Microphone, agent: Agent):
    def approver(description: str) -> bool:
        # The FULL text is always shown on screen. It was built by our code, not by the LLM.
        print("\n" + "=" * 62)
        print("RUBI NEEDS YOUR APPROVAL")
        print("-" * 62)
        print(description)
        print("=" * 62)
        print("Say or type yes / no: ", end="", flush=True)

        force_local = agent.llm.mode == "ollama"

        # Speak only a SHORT summary: the first two lines of the description.
        lines = [line.strip() for line in description.splitlines() if line.strip()]
        short = " ".join(lines[:2])[:140]
        try:
            tts.speak(f"I need your approval. {short}. Say yes or no, or type it.", force_local)
        except Exception as error:
            print(f"\n[voice] could not speak: {error}")

        deadline = time.time() + VOICE_APPROVAL_TIMEOUT
        unclear = 0
        try:
            # The mic was stopped while Rubi was talking (so it cannot hear itself).
            mic.start()
            mic.drain()
            while time.time() < deadline and unclear < 2:
                # abort_check=stdin_ready: if you start TYPING, stop listening immediately.
                samples = audio.record_utterance(mic, abort_check=stdin_ready, wait_seconds=5)

                if stdin_ready():                          # a typed answer wins
                    typed = sys.stdin.readline().strip().lower()
                    return typed in {"y", "yes"}

                if samples is None:                        # nothing heard in 5 s: keep waiting
                    continue

                text = normalize(stt.transcribe(audio.to_wav_bytes(samples), "speech.wav", force_local))
                print(f"\n(heard: {text!r})")

                if text in YES_WORDS:
                    safety.log_action("approval_via_voice", text, "INFO")
                    return True
                if text in NO_WORDS:
                    safety.log_action("approval_via_voice", text, "INFO")
                    return False

                unclear += 1                                # heard something, but not a clear yes/no
                mic.stop()
                try:
                    tts.speak("Sorry, please say just yes, or no.", force_local)
                except Exception:
                    pass
                mic.start()
                mic.drain()

            return False       # timeout or too many unclear answers: DENIED (fail safe)
        finally:
            mic.stop()         # any error inside also ends up as DENIED via safety.ask_approval()
    return approver


# =============================================================================
# One voice turn
# =============================================================================

def listen_once(mic: audio.Microphone):
    """For /listen and Enter: beep, then record one sentence."""
    mic.stop()
    audio.beep(wait=True)       # the mic is closed during the beep, so it cannot record it
    mic.start()
    mic.drain()
    print("   [listening...]", flush=True)
    return audio.record_utterance(mic)


def listen_after_wake(mic: audio.Microphone):
    """After the wake word. The mic stays OPEN so a fast 'Rubi, what time is it' is not cut off."""
    print("\n   [wake word heard, listening...]", flush=True)
    if WAKE_BEEP:
        audio.beep(wait=False)
        # Skip the first 0.35 s so the beep itself is not mistaken for speech.
        return audio.record_utterance(mic, ignore_seconds=0.35)
    return audio.record_utterance(mic)


def voice_turn(agent: Agent, mic: audio.Microphone, samples) -> None:
    """Recorded audio in, spoken answer out."""
    mic.stop()                  # Rubi must not hear itself, and the buffer must not overflow
    try:
        if samples is None:
            print("   [no speech heard]")
            return

        force_local = agent.llm.mode == "ollama"
        text = stt.transcribe(audio.to_wav_bytes(samples), "speech.wav", force_local)
        if not text:
            print("   [could not understand that]")
            return

        print(f"You (voice): {text}")
        reply = agent.chat(text)
        print(f"Rubi: {reply}\n")

        # You spoke, so Rubi speaks. A failure here must never crash the loop.
        try:
            tts.speak(reply, force_local)
        except Exception as error:
            print(f"   [voice] could not speak: {error}")
    except Exception as error:
        print(f"   [voice] problem: {error}")
    finally:
        mic.start()
        mic.drain()


def typed_turn(agent: Agent, mic: audio.Microphone, text: str) -> None:
    """Typed in, TEXT only out (no speech)."""
    mic.stop()
    try:
        reply = agent.chat(text)
        print(f"Rubi: {reply}\n")
    finally:
        mic.start()
        mic.drain()


# =============================================================================
# The main loop
# =============================================================================

def run() -> None:
    agent = Agent()
    mic = audio.Microphone()

    # How risky actions get approved in THIS terminal (voice + typing, or typing only).
    safety.set_approver(make_voice_approver(mic, agent) if VOICE_APPROVALS else terminal_approver)

    try:
        mic.start()
    except Exception as error:
        print(f"Could not open the microphone: {error}")
        print("Test it with: python -m voice.selftest mic")
        return

    wake = None
    if WAKE_WORD_ENABLED:
        try:
            from voice.wakeword import WakeWord
            wake = WakeWord()
        except Exception as error:
            print(f"   [voice] wake word is off: {error}")

    ptt = None
    if PTT_ENABLED:
        from voice.ptt import HoldKey
        ptt = HoldKey(PTT_KEY)

    print("\nStay quiet for a second (measuring room noise)...")
    noise, threshold = audio.calibrate(mic)
    print(f"Noise level {noise:.0f}, speech threshold {threshold:.0f}  (use /calibrate to redo)")

    print("\nRubi voice terminal is ready.")
    print("  type a message          -> text reply")
    print("  Enter on empty line     -> listen once (also /listen)")
    if wake is not None:
        print("  say the wake word       -> listen")
    if ptt is not None and ptt.supported:
        print(f"  hold {PTT_KEY.upper()}               -> push-to-talk")
    print("  /help for commands, 'exit' to quit\n")

    prompt()
    try:
        while True:
            # ---- 1) Did you type something? ------------------------------------
            if stdin_ready():
                line = sys.stdin.readline()
                if line == "":                       # stdin was closed
                    break
                text = line.strip()
                lowered = text.lower()

                if lowered in ("exit", "quit"):
                    break
                elif lowered in ("", "/listen"):     # empty Enter or /listen = listen once
                    voice_turn(agent, mic, listen_once(mic))
                elif lowered == "/calibrate":
                    print("Stay quiet for a second...")
                    noise, threshold = audio.calibrate(mic)
                    print(f"Noise level {noise:.0f}, speech threshold {threshold:.0f}\n")
                elif text.startswith("/"):
                    print(handle_command(agent, text) + "\n")
                else:
                    typed_turn(agent, mic, text)

                if wake is not None:
                    wake.reset()
                prompt()
                continue

            # ---- 2) Read ONE audio block (about 80 ms). This also paces the loop. --
            block = mic.read_block()

            # ---- 3) Push-to-talk key held? -------------------------------------
            if ptt is not None and ptt.supported and ptt.is_down():
                print("\n   [push-to-talk: recording...]", flush=True)
                voice_turn(agent, mic, audio.record_while(mic, ptt.is_down))
                if wake is not None:
                    wake.reset()
                prompt()
                continue

            # ---- 4) Wake word heard? -------------------------------------------
            if wake is not None and wake.detect(block):
                voice_turn(agent, mic, listen_after_wake(mic))
                wake.reset()
                prompt()
                continue

    except KeyboardInterrupt:
        pass
    except Exception as error:
        print(f"\n[voice] stopped because of an error: {error}")
    finally:
        mic.stop()
        print("\nGoodbye.")
```

---

### Step 14: Replace `main.py` (two new modes)

**What changes:** `voice` = voice terminal only. `all` = voice terminal + Telegram. The old modes are unchanged. If you edited `main.py` yourself, merge instead of replacing.

```python
# main.py
#
# Usage:
#   python main.py            text terminal only (default)
#   python main.py voice      voice terminal (typing, wake word, push-to-talk, /listen)
#   python main.py telegram   Telegram only (use this for the background service)
#   python main.py both       text terminal + Telegram
#   python main.py all        voice terminal + Telegram

import sys
import threading

from config import WORKSPACE_DIR
from core import notifier
from memory.db import init_db
from scheduler.jobs import start_scheduler

MODES = ("terminal", "voice", "telegram", "both", "all")


def main():
    mode = sys.argv[1].lower() if len(sys.argv) > 1 else "terminal"
    if mode not in MODES:
        print(f"Usage: python main.py [{'|'.join(MODES)}]")
        return

    init_db()
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

    # Where reminders are delivered (the Telegram sink is added later by the bot itself).
    notifier.add_sink(notifier.print_sink)
    notifier.add_sink(notifier.desktop_sink)

    scheduler = start_scheduler()
    try:
        if mode == "terminal":
            from interfaces import terminal
            terminal.run()

        elif mode == "voice":
            # Imported here, not at the top, so the other modes work even if the
            # audio libraries are not installed.
            from interfaces import voice_terminal
            voice_terminal.run()

        elif mode == "telegram":
            from interfaces import telegram_bot
            telegram_bot.run()

        else:  # "both" (text terminal + Telegram) or "all" (voice terminal + Telegram)
            from interfaces import telegram_bot
            if mode == "all":
                from interfaces import voice_terminal as local_interface
            else:
                from interfaces import terminal as local_interface

            if not telegram_bot.can_start():
                print("Telegram is not configured yet, starting the local interface only.\n")
                local_interface.run()
            else:
                # The local interface runs in a background thread, Telegram takes the main
                # thread (run_polling needs it). daemon=True: it ends when the program ends.
                threading.Thread(target=local_interface.run, daemon=True).start()
                telegram_bot.run()
    finally:
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    main()
```

---

### Step 15: Telegram voice messages (edits to `interfaces/telegram_bot.py`)

**Apply these as edits, not as a full replacement.** You changed this file for your network setup (the proxy settings), and a replacement would erase those changes. All edits below are in handler functions and in the handler list, so your connection settings are untouched.

**15a. Add two imports** near the other imports at the top:

```python
import os

from voice import stt, tts
```

**15b. Replace the whole `on_text` function** with a shared helper plus a thin `on_text`. (The helper contains the old `on_text` logic, so text and voice messages behave the same way.)

```python
async def _run_agent_and_reply(update: Update, context: ContextTypes.DEFAULT_TYPE,
                               text: str, speak: bool) -> None:
    """The old on_text logic, shared by text messages (speak=False) and voice messages (speak=True)."""
    message = update.effective_message

    if agent_lock.locked():
        await message.reply_text("Still working on your previous request. Please wait a moment.")
        return

    async with agent_lock:
        safety.set_approver(telegram_approver)

        stop = asyncio.Event()
        typing_task = asyncio.create_task(keep_typing(context.bot, update.effective_chat.id, stop))
        try:
            reply = await asyncio.to_thread(agent.chat, text)
        except Exception as error:
            reply = f"Something went wrong: {error}"
        finally:
            stop.set()
            await typing_task

    for part in chunk_text(reply):
        await message.reply_text(part)

    if speak:
        # You sent a voice message, so you also get a voice note back (plus the text above).
        await _send_voice_reply(message, reply)


async def _send_voice_reply(message, reply: str) -> None:
    """Make a voice note from the reply and send it. Failure here never loses the text reply."""
    force_local = agent.llm.mode == "ollama"        # /brain ollama keeps speech on the laptop too
    audio_path = ogg_path = None
    try:
        audio_path = await asyncio.to_thread(tts.synthesize, reply, force_local)
        ogg_path = await asyncio.to_thread(tts.to_ogg_opus, audio_path)
        with open(ogg_path, "rb") as voice_file:
            await message.reply_voice(voice=voice_file)
    except Exception as error:
        await message.reply_text(f"(I could not make a voice reply: {error})")
    finally:
        for path in (audio_path, ogg_path):         # always delete the temporary files
            if path is not None and os.path.exists(path):
                os.remove(path)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _run_agent_and_reply(update, context, update.effective_message.text, speak=False)


async def on_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message

    # Very long voice messages are slow and expensive to transcribe.
    if message.voice.duration and message.voice.duration > 60:
        await message.reply_text("That voice message is longer than 60 seconds. Please send a shorter one.")
        return

    force_local = agent.llm.mode == "ollama"
    try:
        # Download through the bot's own connection (so it uses the same network settings
        # as the rest of the bot), then transcribe in a worker thread.
        telegram_file = await message.voice.get_file()
        data = bytes(await telegram_file.download_as_bytearray())
        text = await asyncio.to_thread(stt.transcribe, data, "voice.ogg", force_local)
    except Exception as error:
        await message.reply_text(f"I could not process that voice message: {error}")
        return

    if not text:
        await message.reply_text("I could not hear any speech in that message.")
        return

    # Show what was understood, so you can see if something was misheard BEFORE it matters.
    await message.reply_text(f'I heard: "{text}"')
    await _run_agent_and_reply(update, context, text, speak=True)
```

**15c. In `run()`, change the handler list.** Find the lines that register `on_other` and add the voice handler **before** it, and make `on_other` ignore voice messages:

```python
    app.add_handler(MessageHandler(allowed & filters.VOICE, on_voice))        # NEW: voice messages
    app.add_handler(MessageHandler(allowed & ~filters.TEXT & ~filters.COMMAND & ~filters.VOICE, on_other))
```

(The `on_other` line replaces the old one, which did not have `& ~filters.VOICE`. The `~allowed` stranger handler stays as it is, so strangers' voice messages are still ignored and logged.)

Restart Rubi after the edit.

---

### Step 16: Run it

```bash
cd ~/rubi
source venv/bin/activate
python main.py voice
```

You will be asked to stay quiet for a second (noise calibration). Then try the ways to talk:

- Type a message (text reply)
- Press Enter on an empty line, speak (spoken reply)
- Say the wake word, then your sentence
- Hold `F9` while speaking (X11 only)

To run it together with Telegram: `python main.py all`. For the background service from Stage 3, keep `python main.py telegram` (Telegram voice messages work there, since they need no microphone).

---

## 5. Testing

Do these in order. Each one tests one more layer.

| Test | Command or action | What should happen |
|---|---|---|
| Microphone | `python -m voice.selftest mic` | The bar moves when you speak |
| Speakers and voices | `python -m voice.selftest tts` | You hear the online voice, then the offline voice |
| Hearing | `python -m voice.selftest stt` | Both transcripts match what you said |
| Wake word | `python -m voice.selftest wake` | Scores rise and `TRIGGERED` appears when you say the wake word |
| Typed turn | `python main.py voice`, type `hello` | Text reply, **no speech** |
| `/listen` | Type `/listen` or press Enter, then say "save a note: voice test" | Beep, `You (voice): ...`, `[tool] add_note`, a spoken reply |
| Wake word turn | Say the wake word, then "what time is it" | Beep, transcript, spoken reply |
| Push-to-talk (X11 only) | Hold `F9`, speak, release | Transcript and a spoken reply |
| Voice approval: yes | Say "create a python script hi.py that prints hi", then say **yes** when asked | The full text is shown, Rubi reads a short summary, and "yes" lets it proceed |
| Voice approval: no | Same request, say **no** | Denied, nothing is written |
| Typed approval | Same request, **type** `yes` while Rubi is still speaking or listening | Typing wins and works |
| Unclear answer | Say "maybe" at an approval | "Please say just yes, or no", and after two unclear answers it counts as **DENIED** |
| No answer | Stay silent at an approval for 25 seconds | **DENIED** |
| Offline voice | Turn Wi-Fi off, speak to Rubi | Local transcription, Piper voice, local LLM (slower but fully working) |
| Private mode | `/brain ollama`, speak to Rubi | Everything local, even with Wi-Fi on |
| Telegram voice message | Send a voice message to the bot | `I heard: "..."`, the text reply, then a voice note |
| Telegram text | Send a text message | Text reply only |
| Long voice message | Send one over 60 seconds | "Longer than 60 seconds" |
| Safety | `python test_safety.py` | Still `All tests passed.` |

---

## 6. Troubleshooting

| Problem | Likely cause and fix |
|---|---|
| `PortAudioError` or "no default input device" | Microphone not found. `sudo apt install libportaudio2`, then list devices with `python -c "import sounddevice as sd; print(sd.query_devices())"` and set `AUDIO_INPUT_DEVICE` |
| The mic test bar never moves | Wrong device, or the mic is muted. Check Ubuntu Settings, Sound, Input, and try another device number |
| Bluetooth headset sounds terrible or the mic is silent | Bluetooth switches to a low-quality call mode when the mic is used. Use the laptop mic, or a wired or USB headset |
| `ffplay: command not found` | `sudo apt install ffmpeg` |
| You hear nothing but there is no error | Wrong output device or volume. Test with `speaker-test` or the Ubuntu sound settings |
| Online voice fails and it always uses Piper | The online service may be blocked or changed (edge-tts is an unofficial route into Microsoft's service). Piper takes over automatically, which is what the fallback is for |
| `Piper voice file not found` | Redo Step 9A. Both the `.onnx` and `.onnx.json` files must be in `voice/models/` |
| `Piper failed: ...` or unknown arguments | Piper's command line changed in your version. Run `python -m piper --help` and adjust the flags in `_synth_piper` in `tts.py` |
| Local Whisper download fails or hangs | The model comes from Hugging Face. If it is blocked or slow on your network, download it through a connection that can reach it, then run the warm-up again. Once downloaded it is cached and works offline |
| Groq transcription error 400 or 404 | Model name changed. Check the Groq console and set `GROQ_STT_MODEL` in `.env` |
| It transcribes "Thank you." or other phrases when you said nothing | Whisper does that on silence. The junk filter removes the common ones. Raise `MIN_SPEECH_RMS` or run `/calibrate` |
| Sentences get cut off at the end | You pause long while speaking. Raise `SILENCE_SECONDS` (try 1.6) |
| It waits too long after you finish | Lower `SILENCE_SECONDS` (try 0.9) |
| It records constantly or never stops | The room is noisy. Run `/calibrate` while quiet, or raise `MIN_SPEECH_RMS` |
| The first words are missing after the wake word | The wake-word beep skips the first 0.35 s. Pause a moment after the wake word, or set `WAKE_BEEP = False` |
| Wake word never triggers | Say it clearly at normal volume. Lower `WAKE_THRESHOLD`. Check `python -m voice.selftest wake`. If it is your own model, retrain with more variants |
| Wake word triggers all the time | Raise `WAKE_THRESHOLD`, or retrain using a longer phrase like "hey rubi" |
| `pip install openwakeword` fails (often about `tflite-runtime`) | Try `pip install openwakeword --no-deps`, then `pip install onnxruntime numpy scipy scikit-learn tqdm requests`. We use the ONNX engine, so the TFLite runtime is not needed |
| `download_models()` fails | It downloads from the internet. Retry on another connection. It only needs to succeed once |
| Push-to-talk key does nothing | Only works on X11 (`echo $XDG_SESSION_TYPE`). On Wayland press Enter on an empty line or type `/listen`. On the Ubuntu login screen you can pick an "Ubuntu on Xorg" session if you really want a global key |
| The terminal prompt looks odd after a voice turn | Cosmetic, caused by output arriving while the `You:` prompt is shown. Press Enter to get a clean prompt |
| Telegram voice message: "could not process" | Check that `ffmpeg` is installed and look at the exact error text. If it is a download problem, it is the same connection as the rest of your bot |
| Telegram voice note reply is missing, text arrives | Voice synthesis or `ffmpeg` failed. The reply text explains why. Test with `python -m voice.selftest tts` |
| `ModuleNotFoundError: voice` | Run commands from the `~/rubi` folder, and check that `voice/__init__.py` exists |
| Local speech is slow | Use `LOCAL_STT_MODEL=base.en` in `.env`, or close memory-hungry apps. The Ollama model and Whisper are both using your CPU |
| High RAM use | The local model stays loaded once used (about 1 GB for `small.en`). That is expected with your 12 GB |

---

## 7. Security and privacy notes

Voice adds a **microphone that is always on** and **a way to approve actions by speaking**. Read these carefully:

- **Voice approvals are less safe than typing.** Anyone in the room, or any video or audio your laptop plays, could say "yes" during the short approval window. Safeguards in the code: Rubi's microphone is **off while Rubi speaks** (it cannot approve itself), listening happens **only during the approval window** (25 seconds), only an **exact** short answer counts ("yes", "allow it", ... never a sentence that merely contains "yes"), unclear answers are asked **twice at most** and then count as **DENIED**, any error means **DENIED**, voice approvals are written to the audit log, and the **full text always appears on screen** so you can check what was approved. If you want maximum safety, set `VOICE_APPROVALS = False` in `config.py` and approvals become typing only.
- **Read what you approve.** Rubi only reads a short summary aloud. The exact command or file content is on the screen.
- **The wake-word detector listens continuously, but locally.** Audio is analysed in memory, block by block, and is neither saved nor sent anywhere until the wake word triggers. After that, the recorded sentence is sent to Groq (online) or processed locally (offline).
- **What goes online:** your recorded sentence goes to **Groq** for transcription, and Rubi's reply **text** goes to **Microsoft** for the online voice. Use `/brain ollama` when you want everything to stay on your laptop (local Whisper, Piper, Ollama).
- **edge-tts is an unofficial route into Microsoft's service.** It needs no key, but it can change or stop working without notice. That is exactly why Piper is built in as the fallback.
- **Telegram voice notes** pass through Telegram's servers (not end-to-end encrypted) in both directions. Do not ask Rubi to read out secrets.
- **Push-to-talk on X11** uses a global keyboard listener. It only reacts to one key, but a global listener technically sees all key presses in your session, which is why it is limited to X11 and why I did not add a Wayland workaround that reads raw keyboard devices.
- **Misheard speech is possible.** Speech recognition can get words wrong. The approval system still protects risky actions, and on Telegram Rubi shows `I heard: "..."` first. In the terminal the transcript is printed before Rubi acts.
- **Temporary audio files** are stored in `/tmp/rubi_voice` only until playback or sending finishes, then deleted.

---

## 8. Stage 4 checklist and what comes next

**Done when:**
- [ ] `python -m voice.selftest mic`, `tts`, `stt` and `wake` all work
- [ ] The offline path works with Wi-Fi off (local Whisper and Piper)
- [ ] Typed messages get a text reply, voice gets a spoken reply
- [ ] Wake word, `/listen` and (on X11) push-to-talk each start a turn
- [ ] Your trained `rubi.onnx` works, with an acceptable false-trigger rate
- [ ] Approvals work by voice and by typing, and unclear or silent answers are denied
- [ ] Telegram voice messages get `I heard: ...`, a text reply and a voice note
- [ ] `/brain ollama` keeps hearing and speaking local
- [ ] `python test_safety.py` still passes

**Concepts this stage taught you** (and where they connect):
- **Audio basics:** sample rate, PCM, blocks, loudness (RMS), pre-roll
- **Voice activity detection:** the simplest useful form (a threshold plus silence timing)
- **Polling loops with `select`:** one thread, no keyboard conflicts
- **Graceful degradation again:** the same online/offline pattern from Stage 3, now for hearing and speaking
- **Wake-word models:** small classifiers trained on synthetic data
- **Human factors in security:** why approvals by voice need extra safeguards

**What to learn next:**
1. Digital signal basics (what a spectrogram is, and why models use mel features)
2. Better voice activity detection with a small neural model (for example Silero VAD) instead of a plain loudness threshold
3. **Barge-in**: letting you interrupt Rubi while it is speaking (needs echo cancellation)
4. Streaming speech (start speaking the first sentence while the rest is still being generated)
5. ONNX Runtime basics (how both the wake word and Piper run)

**Ideas for later stages (tell me if you want any):** web search tools, a morning briefing on request, a retry queue for reminders that could not reach Telegram while offline, searching your notes by meaning with local embeddings, and packaging everything into one install script.

When Stage 4 works, tell me what you want next, or ask me to change anything in the design.