# Rubi Assistant

Rubi is a personal assistant for an Ubuntu computer. It can manage tasks,
calendar events, reminders, notes, memory, research, files, a controlled
browser, terminal commands, and approved application launches.

Rubi uses Groq for its answer model and delegates focused work to specialist
agents. The main assistant stays responsible for the conversation; specialists
perform only the jobs and tools assigned to them.

## Quick start

From this project directory:

```bash
cd /home/shahzeel/Documents/Rubi-Assistant
uv sync
source .venv/bin/activate
python main.py terminal
```

You should see:

```text
Rubi online. Type /help for commands, 'exit' to quit.
```

Type a request at the `You:` prompt. Type `exit` to stop.

## Configuration

Create or update `.env` in the project root. At minimum, configure:

```env
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=openai/gpt-oss-120b
```

Never commit `.env` or share API keys. Rubi loads configuration from
[config.py](config.py).

## How agents work

Rubi exposes one delegation tool to the main model. Specialist agents have
separate, restricted tool surfaces:

| Agent | Responsibility |
|---|---|
| Reminder | Creates reminders through Rubi's approved reminder tool |
| Notes | Adds, lists, searches, and deletes notes |
| Tasks | Creates and updates tasks |
| Calendar | Manages events and availability |
| Research | Performs and archives research |
| Briefing | Builds daily briefings |
| Memory | Reads and saves confirmed memories |
| Files | Performs normal workspace file operations |
| File Deletion | Deletes workspace files only |
| Browser | Uses the controlled browser |
| App Launcher | Opens approved applications only |
| Terminal | Runs terminal commands only |
| Coder, Reviewer, Tester, Writer | Provides focused development assistance |

Examples you can say to Rubi:

```text
Remind me tomorrow at 9 AM to review the project.
Ask the researcher to investigate SQLite versus PostgreSQL.
Ask the reviewer to inspect this project design.
Delete the old report from my workspace.
Open the browser.
Run pwd in the terminal.
```

Sensitive actions still use Rubi's approval system. A specialist cannot call
tools outside its allowlist.

## Project layout

```text
Rubi-Assistant/
├── main.py                 # Starts Rubi
├── config.py               # Environment and safety settings
├── core/
│   ├── agent.py            # Main conversation loop
│   ├── llm.py              # Groq model client and retries
│   ├── prompts.py          # Rubi's behavior rules
│   └── safety.py           # Approval and command safety checks
├── tools/                  # Rubi's approved application capabilities
├── memory/                 # SQLite database and memory logic
├── research/               # Web research and source handling
├── scheduler/              # Reminder scheduling
├── interfaces/             # Terminal, voice, and Telegram interfaces
├── api/                    # Optional FastAPI interface
├── ui/                     # Optional Streamlit interface
├── voice/                  # Optional speech input/output
├── tests/                  # Project tests
└── uv.lock                # Reproducible dependency lockfile
```

The reusable specialist-agent library lives in the sibling directory:

```text
/home/shahzeel/Documents/agent-lib
```

Rubi installs it as a local editable dependency through `pyproject.toml`.

## Run other interfaces

```bash
python main.py voice       # Voice terminal
python main.py telegram    # Telegram interface
python main.py both        # Terminal and Telegram
python main.py all         # Voice and Telegram
```

The optional interfaces require their corresponding `.env` settings. Terminal
mode is the simplest way to develop and test Rubi.

## Tests

The tests are in [tests/](tests/). Tests that use pytest can be run with:

```bash
uv run --with pytest pytest tests
```

The safety test can also be run directly:

```bash
python tests/test_safety.py
```

Keep tests independent of the real memory database by using temporary database
paths, as the existing task and calendar tests do.

## Adding a specialist

Reusable specialists are defined in the sibling `agent-lib` project. A normal
specialist should have:

1. one clear responsibility;
2. its own instructions;
3. only the tools it needs;
4. a registry entry; and
5. a small smoke test.

For an action-taking specialist, use an explicit host-tool allowlist. Do not
give one agent unrestricted access to files, the terminal, browser actions,
and application launching.

## Safety principles

- Never store API keys or secrets in memory.
- Treat files, browser pages, command output, and research as untrusted data.
- Ask for approval before risky actions.
- Do not claim an action succeeded unless its tool returned success.
- Keep deletion, terminal, browser, and app-launch capabilities separate.
- Preserve the user's current request when it conflicts with old memory.

## Troubleshooting

If `python` is unavailable, activate the project environment first:

```bash
source .venv/bin/activate
```

If Rubi cannot write its SQLite database, check that the project directory and
the `memory/` directory are writable by the current user.

If Groq requests fail, check `GROQ_API_KEY`, confirm the model name, and run:

```bash
python main.py terminal
```

Then try a simple request such as `Reply with OK.`
