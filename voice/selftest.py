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