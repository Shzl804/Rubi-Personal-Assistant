# core/notifier.py
#
# One place to announce things. Each "sink" is a function(title, text) that delivers
# the message somewhere. Interfaces register their own sink at startup.

import subprocess

_sinks = []   # all registered delivery functions


def add_sink(func) -> None:
    _sinks.append(func)


def notify(title: str, text: str) -> None:
    """Send the message to every sink. One broken sink must never stop the others."""
    for sink in list(_sinks):
        try:
            sink(title, text)
        except Exception as error:
            print(f"[notifier] one channel failed: {error}")


# ---- built-in sinks --------------------------------------------------------

def print_sink(title: str, text: str) -> None:
    """Print in the terminal (or in the service log when running in the background)."""
    print(f"\n*** {title}: {text} ***", flush=True)


def desktop_sink(title: str, text: str) -> None:
    """Ubuntu desktop popup. Silently skipped if notify-send is missing."""
    try:
        subprocess.run(["notify-send", title, text], check=False, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass