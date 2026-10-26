# MiniCode

A small coding agent for your terminal. It reads and edits files in a workspace,
searches code, runs shell commands, and switches between plan and build modes.
One Python loop over an OpenAI-compatible chat API.

**MiniCode starts in plan mode. Type `/build` to enable file writes.**

## Architecture

`-->` is a runtime call. `-.->` is import-time or a callback.

```text
__main__.py -- agent(messages) --> agent.py
__main__.py -- registers ask["fn"] -.-> permissions.py
__main__.py -- reads SANDBOX -.-> resolve_path.py
agent.py -- chat.completions.create --> model API
agent.py -- decide / force_ask / plan_touches --> permissions.py
permissions.py -- prompt callback -.-> __main__.py
agent.py -- classify / approve / clear_approved --> resolve_path.py
agent.py -- dispatch TOOLS[name] --> tools/
agent.py -- tool_from_fn -.-> schema_generator.py
schema_generator.py -- wraps each tool -.-> tools/
tools/ -- _resolve / SANDBOX --> resolve_path.py
```

`agent.py` is the only model-call site. `permissions.py` only decides. `agent.py`, `tools/edit.py`, and `tools/shell.py` also print to stdout. `schema_generator.py` is not in the turn below. It wraps the tools once, at import.

```text
user >> input
├── empty → next prompt
├── exit / quit / bye → stop
├── /plan or /build → swap messages[0] → next prompt
├── /model → list or set the id → next prompt
└── otherwise
    ↓
    append the user message
    ↓
    agent(messages)
    ↓
    chat.completions.create → model API
    ↓
    append the assistant message
    ├── no tool call → return the answer
    └── each tool call
        ├── plan denies write/edit, or unknown name → tool result
        ├── deny → tool result
        ├── ask → prompt callback → __main__.py
        └── allow → TOOLS[name] → tools/ → resolve_path.py
    ↓
    repeat until the model stops, or MAX_STEPS
    ↓
    print minicode >> and the status block → next prompt
```

| Caller | Callee | What crosses |
|---|---|---|
| `__main__` | `agent` | `agent(messages)`; reads `SYSTEM`, `mode`, `active`, `MODELS`, usage |
| `__main__` | `permissions` | registers `ask["fn"]` at import |
| `__main__` | `resolve_path` | reads `SANDBOX` at import |
| `agent` | OpenAI API | one `chat.completions.create` site |
| `agent` | `permissions` | `decide` / `force_ask` / `plan_touches` |
| `permissions` | `__main__` | calls the registered prompt (callback) |
| `agent` | `resolve_path` | `classify` / `approve` / `clear_approved` |
| `agent` | `schema_generator` | `tool_from_fn` at import |
| `agent` | `tools` | imports the functions; dispatches `TOOLS[name]` |
| `schema_generator` | `tools` | wraps each function at import into a validating `run` |
| `tools` | `resolve_path` | `_resolve` / `SANDBOX` |

## Features

- Plan and build modes in one session
- `read`, `write`, `edit`, `glob`, `grep`, and shell tools
- Exact-match edits with a terminal diff
- Model switching with `/model`
- Workspace-bounded file access with `.env` protection
- Permission prompts for `.env` access, plan-mode file-changing shell commands,
  and paths outside the workspace
- Per-turn token and elapsed-time status

## Requirements

- Python 3.13 or newer
- `uv`
- A Gemini API key, or a local Ollama server

On Windows, MiniCode uses Git Bash if it is installed, otherwise PowerShell. On
macOS and Linux it uses bash, then sh. The status line shows the loaded shell
name.

## Install

```powershell
git clone https://github.com/maitriishahh/MiniCode.git
cd MiniCode
uv sync
```

Copy the environment template:

```powershell
Copy-Item .env.example .env
```

On macOS or Linux:

```bash
cp .env.example .env
```

## Configure

Edit `.env`:

| Variable | Required | Notes |
|---|---|---|
| `GEMINI_API_KEY` | For Gemini | Get one from https://aistudio.google.com |
| `GEMINI_MODEL` | For Gemini | Model id, for example `gemini-3.5-flash-lite`. No `gemini/` prefix. |
| `OLLAMA_MODEL` | No | Local model id. Leave empty to disable Ollama. |
| `OLLAMA_API_KEY` | No | Leave empty for a local server. |

`.env` is gitignored. Server base URLs are built in. To use only Ollama,
leave `GEMINI_MODEL` empty, set `OLLAMA_MODEL`, and start the local server
first.

## Run

From the MiniCode directory:

```powershell
uv run python -m minicode
```

To point MiniCode at another directory:

```powershell
uv run python -m minicode --sandbox C:\path\to\project
```

`--sandbox` accepts a relative or absolute path and creates it if missing.
Without it, the workspace is the directory you launch from.

Startup prints the workspace, mode, and loaded tools. The default mode is
`plan`.

## First session

1. Ask for something in plain English.
2. MiniCode may read, search, or run a permitted command.
3. Paths outside the workspace ask for permission. Shell asks for `.env`,
   and in plan mode for commands that read, create, or delete files.
4. Type `/build` before asking for file changes.
5. Leave with `exit`, `quit`, `bye`, or Ctrl+C at the prompt.

## Commands

| Command | Effect |
|---|---|
| `/plan` | Switch to plan mode. `write` and `edit` are disabled. |
| `/build` | Switch to build mode. All tools are available. |
| `/model` | List the models loaded from `.env`. |
| `/model <id>` | Switch to another loaded model for this session. |
| `exit` / `quit` / `bye` | Leave MiniCode. |

Switching modes keeps the same conversation and history. Neither command is
sent to the model.

## Example session

```text
Sandbox: C:\path\to\project

Mode: plan | Tools Loaded: read, glob, grep, bash

user >> read pyproject.toml and summarize the dependencies

~~Thinking...

|Tools Used: `read` ({"path": "pyproject.toml"})|

minicode >> The project depends on openai, pydantic, and python-dotenv.

---
Model: gemini-3.5-flash-lite | Mode: plan | Tools Loaded: read, glob, grep, bash
Sandbox: C:\path\to\project
1,204 In | 48 Out | 48 Session | Elapsed: 2.1s
---

user >> /build
Mode: build | Tools Loaded: read, write, edit, glob, grep, bash
```

If your shell tool is named `powershell` instead of `bash`, that is the Windows
fallback.

## Tools

| Tool | What it does | Notes |
|---|---|---|
| `read` | Reads a file with line numbers. | Starts at line 1 and returns up to 2,000 lines by default. |
| `write` | Creates a file or replaces a whole file. | `content` must be the full final file. Creates parent folders. |
| `edit` | Replaces one exact unique span. | Fails on zero or multiple matches. Prints a diff to the terminal. |
| `glob` | Finds files by name pattern. | Capped at 50 paths. |
| `grep` | Searches file contents with a regex. | Capped at 50 matches. `include` filters file names. |
| `bash` / `powershell` | Runs a shell command. | 120-second timeout. Output capped at 8,000 characters. |

`glob` and `grep` skip dot-directories, `__pycache__`, and `.venv`. `grep`
also skips `.env` contents. `glob` may list the name. Both tell the model
to refine broad searches.

## Plan and build

**Plan** is for reading, searching, and proposing changes. `write` and `edit`
are not offered to the model, and a guessed call is refused. Shell commands are
still available. In plan, a command asks when it reads file contents, creates,
or deletes. `ls` and `git` do not.

**Build** offers every tool. `write` and `edit` run without a prompt inside the
workspace. Ordinary shell commands do not ask.

Plan mode is not a hard sandbox: an approved shell command can still change
files. Use build mode deliberately.

## Permissions

| Key | Covers | Default |
|---|---|---|
| `read` | `read` | allow |
| `edit` | `write`, `edit` | allow |
| `glob` | `glob` | allow |
| `grep` | `grep` | allow |
| `shell` | `bash`, `powershell` | allow, except `.env` text and plan verbs |
| `external_directory` | paths outside the workspace | ask |

When prompted:

- `o` or `once` allows this call.
- `a` or `always` allows that exact value until MiniCode exits.
- `d`, an empty answer, or Ctrl+C denies the call.

`.env` and `.env.*` ask on read. `.env.example` does not. Permission denials
return `Permission denied: <key> <value>`. A denied plan-mode shell ask returns
the short `/build` sentence instead.

## Workspace and safety

The workspace is the directory you launch from, or the path passed to
`--sandbox`. File tools may use absolute or workspace-relative paths. A path
outside the workspace triggers the `external_directory` prompt.

The workspace is a path boundary, not a container. An approved shell command
can leave it with `cd` or change files outside it. The shell also inherits your
environment variables. Do not run MiniCode on a repository you do not trust.

## Status line

After each turn:

```text
---
Model: gemini-3.5-flash-lite | Mode: plan | Tools Loaded: read, glob, grep, bash
Sandbox: C:\path\to\project
1,204 In | 48 Out | 96 Session | Elapsed: 2.1s
---
```

- `In` is the prompt size of the last model call.
- `Out` is the output tokens for the turn.
- `Session` is the total output tokens since startup.
- `Elapsed` is wall-clock time for the turn.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `401` or authentication error | Check `GEMINI_API_KEY` in `.env`. |
| `404` model not found | Remove any `gemini/` prefix from `GEMINI_MODEL`. |
| `No module named minicode` | Run `uv sync` from the MiniCode directory. |
| `Model Error: ...` with Ollama | Start Ollama and check that `OLLAMA_MODEL` matches a pulled model. |
| `No shell found` | Install Git Bash or PowerShell on Windows, or bash/sh on Unix. |
| `Max limit reached: 16` | The turn hit the step limit. Ask for a smaller task. |

## Not included yet

Streaming and abort handling, sessions and resume, cache control, cost display,
compaction, a diff viewer, `AGENTS.md` injection, MCP, subagents, and a
graphical interface. Context percentage stays off until a verified
`context_window` is set. Cost display waits until more models are added.
Ctrl+C during a running shell command ends MiniCode rather than cancelling
only that command.
