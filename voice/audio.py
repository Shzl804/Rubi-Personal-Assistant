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