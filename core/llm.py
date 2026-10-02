# core/llm.py
#
# The "router": the only file that knows there are two brains.
# The agent just calls  router.complete(messages, tools)  and gets a response.

import groq
from groq import Groq
from openai import OpenAI
from openai import APIConnectionError as OllamaConnectionError
from openai import APITimeoutError as OllamaTimeout
from openai import NotFoundError as OllamaModelMissing

from config import (
    GROQ_API_KEY, MODEL_NAME, GROQ_TIMEOUT, GROQ_COOLDOWN_SECONDS,
    OLLAMA_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT,
)
from core import connectivity


def _groq_errors(*names):
    """
    Collect error classes from the groq library by name.
    getattr/hasattr makes this safe even if a library version names one differently.
    """
    return tuple(getattr(groq, n) for n in names if hasattr(groq, n))


# Errors that mean "Groq cannot serve me right now", so the local model should take over.
# (RateLimitError is included on purpose: if you hit the free-tier limit, Rubi keeps
#  working locally. Remove it from this list if you do not want that.)
GROQ_UNAVAILABLE_ERRORS = _groq_errors(
    "APIConnectionError",   # no route to Groq (also the parent of timeouts)
    "APITimeoutError",      # Groq did not answer in time
    "RateLimitError",       # too many requests / tokens
    "InternalServerError",  # Groq-side failure (5xx)
)
# NOT in the list: AuthenticationError (bad key) and BadRequestError (our mistake).
# Falling back would only hide a bug that you need to see.


class LLMRouter:
    MODES = ("auto", "groq", "ollama")

    def __init__(self):
        # max_retries=1: the SDK retries automatically on connection errors; the
        # default (2 retries with waiting) would delay the fallback too much.
        self.groq = Groq(api_key=GROQ_API_KEY, timeout=GROQ_TIMEOUT, max_retries=1)

        # Ollama exposes an OpenAI-compatible API under /v1, so the 'openai' client
        # works. The api_key is required by the client but ignored by Ollama.
        self.ollama = OpenAI(
            base_url=f"{OLLAMA_URL}/v1",
            api_key="ollama",
            timeout=OLLAMA_TIMEOUT,
            max_retries=0,
        )

        self.mode = "auto"          # "auto": decide by connectivity
        self.last_backend = None    # "groq" or "ollama": which one answered last

    # ---------------------------------------------------------------- helpers
    def set_mode(self, mode: str) -> None:
        if mode not in self.MODES:
            raise ValueError(f"mode must be one of: {', '.join(self.MODES)}")
        self.mode = mode

    def _announce(self, backend: str) -> None:
        """Print a line only when the brain CHANGES, so the terminal stays clean."""
        if backend != self.last_backend:
            print(f"   [brain] now using {backend}")
            self.last_backend = backend

    # ----------------------------------------------------------------- Groq
    def _call_groq(self, messages, tools):
        last_error = None
        for _ in range(2):   # one retry: open models sometimes emit a malformed tool call
            try:
                return self.groq.chat.completions.create(
                    model=MODEL_NAME,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    temperature=0.3,
                )
            except GROQ_UNAVAILABLE_ERRORS:
                raise                    # no point retrying: let complete() decide the fallback
            except Exception as error:   # e.g. a flaky malformed tool call: try once more
                last_error = error
        raise last_error

    # --------------------------------------------------------------- Ollama
    def _call_ollama(self, messages, tools):
        try:
            # tool_choice is left out on purpose: not every Ollama version supports it,
            # and "auto" is already the default behavior.
            return self.ollama.chat.completions.create(
                model=OLLAMA_MODEL,
                messages=messages,
                tools=tools,
                temperature=0.3,
            )
        # Order matters: APITimeoutError is a subclass of APIConnectionError, so it must come first.
        except OllamaTimeout as error:
            raise RuntimeError(
                "The local model took too long to answer. Try a smaller model."
            ) from error
        except OllamaConnectionError as error:
            raise RuntimeError(
                f"The local model is not reachable at {OLLAMA_URL}. "
                f"Is Ollama running? Check: systemctl status ollama"
            ) from error
        except OllamaModelMissing as error:
            raise RuntimeError(
                f"The local model '{OLLAMA_MODEL}' was not found. "
                f"Run 'ollama list' and fix OLLAMA_MODEL in .env."
            ) from error

    # ---------------------------------------------------------- public method
    def complete(self, messages, tools):
        """Return a chat completion from whichever brain is appropriate right now."""
        use_groq = self.mode == "groq" or (self.mode == "auto" and connectivity.can_use_groq())

        if use_groq:
            try:
                response = self._call_groq(messages, tools)
                self._announce("groq")
                return response
            except GROQ_UNAVAILABLE_ERRORS as error:
                if self.mode == "groq":
                    # You explicitly asked for Groq only, so do not silently switch.
                    raise RuntimeError(
                        f"Groq is unavailable ({type(error).__name__}) and the brain mode is 'groq' only. "
                        f"Use /brain auto to allow the local model."
                    ) from error
                # Remember the failure so the next messages skip Groq for a while.
                connectivity.mark_unavailable(GROQ_COOLDOWN_SECONDS)
                print(f"   [brain] Groq unavailable ({type(error).__name__}); switching to the local model")

        # Reached when: offline, mode == "ollama", or Groq just failed.
        response = self._call_ollama(messages, tools)
        self._announce("ollama")
        return response