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