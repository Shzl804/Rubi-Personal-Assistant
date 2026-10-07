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