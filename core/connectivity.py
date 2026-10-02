# core/connectivity.py
#
# "Can I use Groq right now?"  Two inputs decide it:
#   1) a cheap network probe (cached)
#   2) a manual "cooldown" set when a real Groq request just failed

import socket
import time

from config import INTERNET_CACHE_SECONDS

# We probe raw IP addresses, not domain names, for two reasons:
#   - no DNS lookup needed, so when you are offline it fails FAST
#     (DNS lookups can hang for many seconds on a broken network)
#   - several different targets, so one blocked address doesn't fool us
PROBES = [("1.1.1.1", 443), ("8.8.8.8", 53), ("9.9.9.9", 443)]

# online      : last known answer
# valid_until : timestamp until which that answer is trusted without probing again
_state = {"online": True, "valid_until": 0.0}


def _probe() -> bool:
    """Try to open a TCP connection to each probe. One success = we have internet."""
    for host, port in PROBES:
        try:
            # 'with' closes the socket right away; we only care that it connected.
            with socket.create_connection((host, port), timeout=2):
                return True
        except OSError:        # covers timeouts, "network unreachable", refused...
            continue
    return False


def can_use_groq() -> bool:
    """True if Rubi should try Groq. Uses the cached answer when it is still fresh."""
    now = time.time()
    if now < _state["valid_until"]:
        return _state["online"]

    online = _probe()
    _state["online"] = online
    _state["valid_until"] = now + INTERNET_CACHE_SECONDS
    return online


def mark_unavailable(seconds: float) -> None:
    """
    Called by the router when a REAL Groq request failed (timeout, rate limit...).
    Even if the probe says 'online', we skip Groq for a while so we don't wait
    for a failing request on every single message.
    """
    _state["online"] = False
    _state["valid_until"] = time.time() + seconds