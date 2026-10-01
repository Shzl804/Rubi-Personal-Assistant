# tools/registry.py
from tools import notes, reminders


def _tool(name, description, properties=None, required=None):
    """Helper that builds one tool description in the format Groq expects."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties or {},
                "required": required or [],
            },
        },
    }


TOOL_SCHEMAS = [
    _tool(
        "add_note",
        "Save a new note. Use when the user asks to save, remember, or write down some information.",
        {"content": {"type": "string", "description": "The text of the note."}},
        ["content"],
    ),
    _tool(
        "list_notes",
        "Show the user's most recent saved notes.",
        {"limit": {"type": "integer", "description": "How many notes to show. Default 20."}},
    ),
    _tool(
        "search_notes",
        "Search saved notes for a keyword.",
        {"keyword": {"type": "string", "description": "Word or phrase to look for."}},
        ["keyword"],
    ),
    _tool(
        "delete_note",
        "Delete a saved note by its id number.",
        {"note_id": {"type": "integer", "description": "The id of the note to delete."}},
        ["note_id"],
    ),
    _tool(
        "set_reminder",
        "Set a reminder that will alert the user at a specific date and time.",
        {
            "text": {"type": "string", "description": "What to remind the user about."},
            "remind_at": {
                "type": "string",
                "description": "Exact local date and time in the format YYYY-MM-DD HH:MM using a 24-hour clock.",
            },
        },
        ["text", "remind_at"],
    ),
    _tool("list_reminders", "Show all pending (not yet fired) reminders."),
    _tool(
        "cancel_reminder",
        "Cancel a pending reminder by its id number.",
        {"reminder_id": {"type": "integer", "description": "The id of the reminder to cancel."}},
        ["reminder_id"],
    ),
]


# Maps the tool name (what the LLM says) to the real Python function.
TOOL_FUNCTIONS = {
    "add_note": notes.add_note,
    "list_notes": notes.list_notes,
    "search_notes": notes.search_notes,
    "delete_note": notes.delete_note,
    "set_reminder": reminders.set_reminder,
    "list_reminders": reminders.list_reminders,
    "cancel_reminder": reminders.cancel_reminder,
}


def run_tool(name: str, args: dict) -> str:
    func = TOOL_FUNCTIONS.get(name)
    if func is None:
        return f"Error: there is no tool called '{name}'."
    try:
        return str(func(**args))
    except TypeError as error:
        return f"Error: wrong arguments for {name}: {error}"
    except Exception as error:
        return f"Error while running {name}: {error}"