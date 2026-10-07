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