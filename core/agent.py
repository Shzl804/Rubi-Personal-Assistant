# core/agent.py  (Stage 3 version)
import json

from config import MAX_HISTORY, MAX_TOOL_ROUNDS, MEMORY_RETRIEVAL_LIMIT
from core.llm import LLMRouter
from core.prompts import build_system_prompt
from memory.archive import save_archive
from memory.long_term import search_memories
from memory.short_term import ShortTermMemory, summarize_messages
from tools.registry import TOOL_SCHEMAS, run_tool


def trim_history(history: list, max_len: int) -> list:
    """Keep only the latest messages, and make sure the first one is from the user.
    (A 'tool' message without the assistant message that requested it would be rejected.)"""
    if len(history) <= max_len:
        return history
    history = history[-max_len:]
    while history and history[0]["role"] != "user":
        history = history[1:]
    return history


class Agent:
    def __init__(self):
        self.llm = LLMRouter()     # the brain switcher (Groq or Ollama)
        self.history = []          # conversation so far, WITHOUT the system prompt
        self.memory = ShortTermMemory()

    def reset(self):
        """Forget the current conversation (notes and reminders in the database stay)."""
        self.history = []
        self.memory = ShortTermMemory()

    def chat(self, user_text: str) -> str:
        start = len(self.history)    # where this turn began, for cleanup if something fails
        self.memory.add_message("user", user_text)
        session_context = self.memory.context()
        remembered = search_memories(
            user_text,
            topic=session_context["topic"],
            project=session_context["project"],
            limit=MEMORY_RETRIEVAL_LIMIT,
        )
        self.history.append({"role": "user", "content": user_text})

        try:
            for _ in range(MAX_TOOL_ROUNDS):
                # The system prompt is rebuilt every time so the clock stays current.
                messages = [{"role": "system", "content": build_system_prompt()}]
                memory_context = []
                if session_context["summary"]:
                    memory_context.append("Session summary:\n" + session_context["summary"])
                if remembered:
                    memory_context.append(
                        "Relevant confirmed memories:\n" + "\n".join(
                            "- " + row["content"] for row in remembered
                        )
                    )
                if memory_context:
                    messages.append({
                        "role": "system",
                        "content": (
                            "Optional remembered context. Use it only when relevant; "
                            "the user's current message takes priority.\n\n" +
                            "\n\n".join(memory_context)
                        ),
                    })
                messages += self.history

                response = self.llm.complete(messages, TOOL_SCHEMAS)
                msg = response.choices[0].message

                # Normalise the tool calls into plain tuples: (id, name, arguments_text).
                # Doing this once means the SAME id is used in the assistant message and in
                # the tool result, even when a model forgot to send an id.
                calls = []
                for index, call in enumerate(msg.tool_calls or []):
                    arguments = call.function.arguments
                    if not isinstance(arguments, str):      # some servers return a dict
                        arguments = json.dumps(arguments)
                    calls.append((call.id or f"call_{index}", call.function.name, arguments))

                # Save the assistant's message in plain-dict form.
                entry = {"role": "assistant", "content": msg.content or ""}
                if calls:
                    entry["tool_calls"] = [
                        {"id": cid, "type": "function", "function": {"name": name, "arguments": args}}
                        for cid, name, args in calls
                    ]
                self.history.append(entry)

                # No tools requested: this is the final answer.
                if not calls:
                    reply = msg.content or ""
                    self.memory.add_message("assistant", reply)
                    self.memory.set_summary(
                        summarize_messages(self.memory.recent_messages())
                    )
                    save_archive(
                        "conversation",
                        "User: {}\nAssistant: {}".format(user_text, reply),
                        topic=session_context["topic"],
                        project=session_context["project"],
                        source="agent",
                    )
                    self.history = trim_history(self.history, MAX_HISTORY)
                    return reply

                # Run each requested tool and send the results back.
                for cid, name, raw_args in calls:
                    try:
                        args = json.loads(raw_args or "{}")
                    except json.JSONDecodeError:
                        result = "Error: the tool arguments were not valid JSON."
                    else:
                        shown = str(args)
                        if len(shown) > 150:
                            shown = shown[:150] + "..."
                        print(f"   [tool] {name}({shown})")
                        result = run_tool(name, args)

                    self.history.append({
                        "role": "tool",
                        "tool_call_id": cid,
                        "content": str(result),
                    })

            return "I could not finish that request. Please try rephrasing it."

        except Exception as error:
            del self.history[start:]     # undo this turn so the history stays valid
            return f"(Error: {error})"
