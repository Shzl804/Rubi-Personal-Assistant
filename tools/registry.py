# tools/registry.py
from tools import notes, reminders, files, system
from memory import archive, long_term
from research.researcher import format_research_context, research


def _tool(name, description, properties=None, required=None):
    """Build one tool description in the format the Groq API expects."""
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
    # ------------------------- notes (Stage 1) -------------------------
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

    # ----------------------- reminders (Stage 1) -----------------------
    _tool(
        "set_reminder",
        "Set a reminder that will alert the user at a specific date and time.",
        {
            "text": {"type": "string", "description": "What to remind the user about."},
            "remind_at": {
                "type": "string",
                "description": "Exact local date and time as YYYY-MM-DD HH:MM using a 24-hour clock.",
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

    # ------------------------ system (Stage 2) -------------------------
    _tool(
        "run_command",
        "Run a shell command on the user's Ubuntu laptop, inside the workspace folder. "
        "Use for system info (disk space, memory, date), running scripts, git, etc. "
        "Do NOT use it for reading/writing files in the workspace; use the file tools for that. "
        "Harmless read-only commands run automatically; others make the system ask the user. "
        "You do not need to ask for permission yourself.",
        {
            "command": {"type": "string", "description": "The exact shell command to run."},
            "reason": {"type": "string", "description": "One short sentence: why this command is needed."},
        },
        ["command"],
    ),
    _tool(
        "open_app",
        "Open a desktop application by its friendly name (e.g. browser, calculator, files, terminal, text editor, code).",
        {"name": {"type": "string", "description": "Friendly app name."}},
        ["name"],
    ),
    _tool(
        "open_url",
        "Open a web link (http/https) in the user's default browser. The user is asked to confirm.",
        {"url": {"type": "string", "description": "Full URL starting with http:// or https://"}},
        ["url"],
    ),

    # ------------------------- files (Stage 2) -------------------------
    _tool(
        "list_files",
        "List files and folders inside the workspace. Paths are relative to the workspace root.",
        {"path": {"type": "string", "description": "Folder to list. Default '.' (the workspace root)."}},
    ),
    _tool(
        "read_file",
        "Read a text file from the workspace.",
        {"path": {"type": "string", "description": "File path relative to the workspace."}},
        ["path"],
    ),
    _tool(
        "write_file",
        "Create a new text file in the workspace (or overwrite one if overwrite is true). "
        "Overwriting and writing script files make the system ask the user.",
        {
            "path": {"type": "string", "description": "File path relative to the workspace."},
            "content": {"type": "string", "description": "Full text content of the file."},
            "overwrite": {"type": "boolean", "description": "Set true only if the user wants to replace an existing file."},
        },
        ["path", "content"],
    ),
    _tool(
        "append_file",
        "Add text to the end of a file in the workspace (creates it if missing).",
        {
            "path": {"type": "string", "description": "File path relative to the workspace."},
            "content": {"type": "string", "description": "Text to add at the end."},
        },
        ["path", "content"],
    ),
    _tool(
        "make_folder",
        "Create a folder (and any missing parent folders) in the workspace.",
        {"path": {"type": "string", "description": "Folder path relative to the workspace."}},
        ["path"],
    ),
    _tool(
        "delete_file",
        "Delete a single file in the workspace. The user is asked to confirm. Cannot delete folders.",
        {"path": {"type": "string", "description": "File path relative to the workspace."}},
        ["path"],
    ),
    _tool(
        "move_file",
        "Move or rename a file or folder inside the workspace. The user is asked to confirm.",
        {
            "source": {"type": "string", "description": "Current path relative to the workspace."},
            "destination": {"type": "string", "description": "New path relative to the workspace."},
        },
        ["source", "destination"],
    ),
    _tool(
        "search_files",
        "Search the workspace for files by name, and optionally by text inside them.",
        {
            "keyword": {"type": "string", "description": "Word to look for."},
            "search_content": {"type": "boolean", "description": "Also search inside text files. Default false."},
        },
        ["keyword"],
    ),
    _tool(
        "remember_user",
        "Save durable information only when the user explicitly asked Rubi to remember it.",
        {
            "content": {"type": "string", "description": "The exact memory to save."},
            "category": {"type": "string", "description": "preference, personal_fact, project_decision, workflow, goal, or constraint."},
            "topic": {"type": "string"},
            "project": {"type": "string"},
        },
        ["content"],
    ),
    _tool(
        "find_memory",
        "Search confirmed memories relevant to the current request.",
        {
            "query": {"type": "string"},
            "topic": {"type": "string"},
            "project": {"type": "string"},
        },
        ["query"],
    ),
    _tool(
        "run_research",
        "Search the web and return source material for a current or research question.",
        {"query": {"type": "string"}},
        ["query"],
    ),
    _tool(
        "archive_research",
        "Save a completed research result to the local archive.",
        {
            "title": {"type": "string"},
            "content": {"type": "string"},
            "topic": {"type": "string"},
            "project": {"type": "string"},
        },
        ["title", "content"],
    ),
]


# Tool name (what the LLM says) -> real Python function.
TOOL_FUNCTIONS = {
    "add_note": notes.add_note,
    "list_notes": notes.list_notes,
    "search_notes": notes.search_notes,
    "delete_note": notes.delete_note,
    "set_reminder": reminders.set_reminder,
    "list_reminders": reminders.list_reminders,
    "cancel_reminder": reminders.cancel_reminder,
    "run_command": system.run_command,
    "open_app": system.open_app,
    "open_url": system.open_url,
    "list_files": files.list_files,
    "read_file": files.read_file,
    "write_file": files.write_file,
    "append_file": files.append_file,
    "make_folder": files.make_folder,
    "delete_file": files.delete_file,
    "move_file": files.move_file,
    "search_files": files.search_files,
}


def _remember_user(content, category="preference", topic=None, project=None):
    lowered = str(content).lower()
    if any(secret in lowered for secret in ("password", "api key", "token", "secret")):
        return "Refused: secrets cannot be saved as memory."
    memory_id = long_term.add_memory(
        content, category, topic, project,
        confidence=0.95, source="explicit_user_request",
    )
    return "Saved memory {}.".format(memory_id)


def _find_memory(query, topic=None, project=None):
    rows = long_term.search_memories(query, topic, project)
    if not rows:
        return "No matching confirmed memories."
    return "\n".join(
        "[{}] {} ({})".format(row["id"], row["content"], row["category"])
        for row in rows
    )


def _run_research(query):
    report = research(query)
    return format_research_context(report)


def _archive_research(title, content, topic=None, project=None):
    archive_id = archive.save_archive(
        "research", content, title, topic, project, source="web"
    )
    return "Saved research archive {}.".format(archive_id)


TOOL_FUNCTIONS.update({
    "remember_user": _remember_user,
    "find_memory": _find_memory,
    "run_research": _run_research,
    "archive_research": _archive_research,
})


def run_tool(name: str, args: dict) -> str:
    """Run one tool safely. Errors become text the LLM can read; they never crash Rubi."""
    func = TOOL_FUNCTIONS.get(name)
    if func is None:
        return f"Error: there is no tool called '{name}'."
    try:
        return str(func(**args))
    except TypeError as error:
        # Usually: the LLM sent wrong/missing argument names.
        return f"Error: wrong arguments for {name}: {error}"
    except Exception as error:
        # Includes ValueError("that path is outside the workspace") from files.py.
        return f"Error while running {name}: {error}"
