"""Bridge Rubi's existing tool loop to the reusable specialist agents."""

import asyncio

from agents import Runner

from agent_lib.registry import get_agent
from agent_lib.host_tools import configure_host_runner


def _run_rubi_tool(tool_name: str, arguments: dict) -> str:
    from tools.registry import run_tool
    return run_tool(tool_name, arguments)


configure_host_runner(_run_rubi_tool)


SPECIALIST_NAMES = {
    "researcher": "Researcher",
    "coder": "Coder",
    "reviewer": "Reviewer",
    "reminder": "Reminder",
    "notes": "Notes",
    "tasks": "Tasks",
    "calendar": "Calendar",
    "files": "Files",
    "file_deletion": "File Deletion",
    "browser": "Browser",
    "app_launcher": "App Launcher",
    "terminal": "Terminal",
    "memory": "Memory",
    "research": "Research",
    "briefing": "Briefing",
    "tester": "Tester",
    "writer": "Writer",
}


def delegate_to_specialist(agent_name: str, task: str, context: str = "") -> str:
    """Run one focused specialist and return its result to Rubi."""
    key = agent_name.strip().lower()
    if key not in SPECIALIST_NAMES:
        return "Error: choose researcher, coder, reviewer, reminder, notes, tasks, calendar, files, file_deletion, browser, app_launcher, terminal, memory, research, briefing, tester, or writer."
    if not task.strip():
        return "Error: task is required."

    prompt = task.strip()
    if context.strip():
        prompt += f"\n\nProject context:\n{context.strip()}"

    try:
        result = asyncio.run(Runner.run(get_agent(SPECIALIST_NAMES[key]), prompt))
        return str(result.final_output)
    except RuntimeError as error:
        return f"Specialist could not complete the task: {error}"
