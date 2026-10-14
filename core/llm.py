# core/llm.py
#
# The "router": the only file that knows how the online answer model is called.
# The agent just calls router.complete(messages, tools) and gets a response.

import groq
import re
from groq import Groq
import openai
from openai import OpenAI

from config import (
    GROQ_API_KEY, MODEL_NAME, FAST_MODEL_NAME, RESEARCH_MODEL_NAME,
    GROQ_TIMEOUT, GROQ_COOLDOWN_SECONDS,
)
from core import connectivity


def hide_reasoning(text):
    """Remove leaked Qwen thinking blocks before text enters history or the UI."""
    if not text:
        return text or ""
    cleaned = re.sub(r"<think>.*?</think>", "", str(text), flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"^\s*Thinking:\s*.*?(?=\n\s*(?:Final|Answer):|\Z)", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    return cleaned.strip()


def _groq_errors(*names):
    """
    Collect error classes from the groq library by name.
    getattr/hasattr makes this safe even if a library version names one differently.
    """
    return tuple(getattr(groq, n) for n in names if hasattr(groq, n))


def _openai_errors(*names):
    return tuple(getattr(openai, n) for n in names if hasattr(openai, n))


# Errors that mean "Groq cannot serve me right now", so the local model should take over.
# (RateLimitError is included on purpose: if you hit the free-tier limit, Rubi keeps
#  working locally. Remove it from this list if you do not want that.)
GROQ_UNAVAILABLE_ERRORS = _groq_errors(
    "APIConnectionError",   # no route to Groq (also the parent of timeouts)
    "APITimeoutError",      # Groq did not answer in time
    "RateLimitError",       # too many requests / tokens
    "InternalServerError",  # Groq-side failure (5xx)
)
GROQ_UNAVAILABLE_ERRORS += _openai_errors(
    "APIConnectionError",
    "APITimeoutError",
    "RateLimitError",
    "InternalServerError",
)
# NOT in the list: AuthenticationError (bad key) and BadRequestError (our mistake).
# Falling back would only hide a bug that you need to see.


class LLMRouter:
    # Ollama is intentionally disabled for now. Rubi should report an internet
    # problem instead of silently switching to a different answer model.
    MODES = ("auto", "groq")

    def __init__(self):
        # max_retries=1: the SDK retries automatically on connection errors; the
        # default (2 retries with waiting) would delay the fallback too much.
        # Groq's OpenAI-compatible endpoint handles Rubi's function-tool
        # requests correctly. The native Groq client remains used by voice STT.
        self.groq = OpenAI(
            api_key=GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
            timeout=GROQ_TIMEOUT,
            max_retries=1,
        )

        self.mode = "auto"          # "auto": use Groq when internet is available
        self.profile = "default"    # default, fast, or research
        self.last_backend = None    # "groq": which one answered last

    # ---------------------------------------------------------------- helpers
    def set_mode(self, mode: str) -> None:
        if mode not in self.MODES:
            raise ValueError(f"mode must be one of: {', '.join(self.MODES)}")
        self.mode = mode

    def set_profile(self, profile: str) -> None:
        if profile not in ("default", "fast", "research"):
            raise ValueError("profile must be one of: default, fast, research")
        self.profile = profile

    def selected_model(self) -> str:
        if self.profile == "fast":
            return FAST_MODEL_NAME
        if self.profile == "research":
            return RESEARCH_MODEL_NAME
        return MODEL_NAME

    def _announce(self, backend: str) -> None:
        """Print a line only when the brain CHANGES, so the terminal stays clean."""
        if backend != self.last_backend:
            print(f"   [brain] now using {backend}")
            self.last_backend = backend

    # ----------------------------------------------------------------- Groq
    def _call_groq(self, messages, tools):
        last_error = None
        options = {
            "model": self.selected_model(),
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "temperature": 0.3,
        }
        if self.selected_model().startswith("qwen/qwen3"):
            # Qwen still reasons internally, but Groq returns only the final answer.
            options["reasoning_format"] = "hidden"
            options["reasoning_effort"] = "none"
        for _ in range(2):   # one retry: open models sometimes emit a malformed tool call
            try:
                return self.groq.chat.completions.create(**options)
            except GROQ_UNAVAILABLE_ERRORS:
                raise                    # no point retrying: let complete() decide the fallback
            except Exception as error:   # e.g. a flaky malformed tool call: try once more
                last_error = error
        raise last_error

    # ---------------------------------------------------------- public method
    def complete(self, messages, tools):
        """Return a Groq completion, or a clear error when internet is unavailable."""
        if not connectivity.can_use_groq():
            raise RuntimeError(
                "Internet is not working, so I cannot contact the answer model right now."
            )

        use_groq = True

        if use_groq:
            try:
                response = self._call_groq(messages, tools)
                self._announce("groq")
                return response
            except GROQ_UNAVAILABLE_ERRORS as error:
                # Remember the failure so the next messages fail quickly too.
                connectivity.mark_unavailable(GROQ_COOLDOWN_SECONDS)
                raise RuntimeError(
                    "Internet is not working, so I cannot contact the answer model right now."
                ) from error
