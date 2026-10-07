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