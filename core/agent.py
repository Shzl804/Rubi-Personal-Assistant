# core/agent.py
import json

from groq import Groq

from config import GROQ_API_KEY, MODEL_NAME, MAX_HISTORY, MAX_TOOL_ROUNDS
from core.prompts import build_system_prompt
from tools.registry import TOOL_SCHEMAS, run_tool


def trim_history(history: list, max_len: int) -> list:
    """Keep only the latest messages, starting from a user message."""
    if len(history) <= max_len:
        return history
    history = history[-max_len:]
    while history and history[0]["role"] != "user":
        history = history[1:]
    return history


class Agent:
    def __init__(self):
        self.client = Groq(api_key=GROQ_API_KEY)
        self.history = []          # list of messages (without the system prompt)

    def _call_llm(self, messages: list):
        """Call Groq. Retry once, because tool calls occasionally fail randomly."""
        last_error = None
        for _ in range(2):
            try:
                return self.client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=messages,
                    tools=TOOL_SCHEMAS,
                    tool_choice="auto",
                    temperature=0.3,
                )
            except Exception as error:
                last_error = error
        raise last_error

    def chat(self, user_text: str) -> str:
        start = len(self.history)    # remember where this turn began (for error cleanup)
        self.history.append({"role": "user", "content": user_text})

        try:
            for _ in range(MAX_TOOL_ROUNDS):
                # The system prompt is rebuilt every time so the clock stays current.
                messages = [{"role": "system", "content": build_system_prompt()}] + self.history

                response = self._call_llm(messages)
                msg = response.choices[0].message

                # Save the assistant's message in plain-dict form.
                entry = {"role": "assistant", "content": msg.content or ""}
                if msg.tool_calls:
                    entry["tool_calls"] = [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.function.name,
                                "arguments": call.function.arguments,
                            },
                        }
                        for call in msg.tool_calls
                    ]
                self.history.append(entry)

                # No tool requested: this is the final answer.
                if not msg.tool_calls:
                    reply = msg.content or ""
                    self.history = trim_history(self.history, MAX_HISTORY)
                    return reply

                # Run each requested tool and send results back.
                for call in msg.tool_calls:
                    name = call.function.name
                    try:
                        args = json.loads(call.function.arguments or "{}")
                    except json.JSONDecodeError:
                        result = "Error: the tool arguments were not valid JSON."
                    else:
                        print(f"   [tool] {name}({args})")
                        result = run_tool(name, args)

                    self.history.append({
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": str(result),
                    })

            return "I could not finish that request. Please try rephrasing it."

        except Exception as error:
            del self.history[start:]     # undo this turn so history stays valid
            return f"(Error talking to Groq: {error})"