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