# MiniCode

A small coding agent for your terminal. It reads and edits files in a workspace,
searches code, runs shell commands, and switches between plan and build modes.
One Python loop over an OpenAI-compatible chat API.

**MiniCode starts in plan mode. Type `/build` to enable file writes.**

## Architecture

### Project Flow Diagram

```text
  [ User / Terminal ]
         │
         ▼  (types prompt, e.g. "Fix calculator.py" or `/build` or `/model`)
  [ __main__.py ] (REPL loop, session usage tracking, elapsed time measurement)
         │
         ├─► Command handled locally? (/plan, /build, /model, exit)
         │
         ▼  (otherwise appends user message to history, calls agent)
  [ agent.py ] (Agent Core & Multi-Step Turn Loop - max 16 steps)
         │
         ├─► client.chat.completions.create(stream=True)
         │        │
         │        ├─► Model API (Gemini / Ollama)
         │        │        │
         │        │        ▼ (Streaming response chunks)
         │        ├─► _consume(stream, on_event, state)
         │        │        ├─► Emits reasoning/thinking (if present)
         │        │        ├─► Accumulates text content & tool calls (handles missing indices/Gemini extra_content)
         │        │        └─► Captures token usage metadata
         │        │
         │        ├─► KeyboardInterrupt / Exception handling during stream
         │        │        └─► Appends interrupted/error assistant message, returns None / error
         │        │
         │        ▼ (No tool calls)
         ├─► Answer tokens stream as they arrive. No `minicode >>` prefix
         │
         └─► Tool Calls Present?
                  │
                  ▼
         [ Permission & Boundary Check ] (`_permit` in agent.py → permissions.py & resolve_path.py)
                  │
                  ├─► Plan mode active & tool in PLAN_DENIED (write, edit) or shell mutating sandbox?
                  │        └─► Denied / prompts user via terminal callback (`_permission` in `__main__.py`)
                  ├─► Target path in `.env` or external directory?
                  │        └─► Prompts user: `[o]nce / [a]lways / [d]eny`
                  │
                  ▼ (Allowed)
         [ Tool Dispatch ] (`TOOLS[name]` in `tools/`)
                  │
                  ├─► read.py, write.py, edit.py, glob.py, grep.py, shell.py
                  │        └─► Validated against SANDBOX boundary (`resolve_path.py`)
                  │        └─► Executes operation (e.g. diff for edit, subprocess for shell)
                  │
                  ▼
         [ Append Tool Result ] (`role: "tool"`, `tool_call_id`)
                  │
                  └─► Loop continues to next step in `agent()`
```

### Component Interaction Table

| Caller | Callee | What crosses |
|---|---|---|
| `__main__` | `agent` | `agent(messages, on_event)`; reads `SYSTEM`, `mode`, `active`, `MODELS`, usage |
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

`agent.py` is the only model-call site. `permissions.py` only decides. `agent.py`, `tools/edit.py`, and `tools/shell.py` also print to stdout. `schema_generator.py` is not in the turn below. It wraps the tools once, at import.

## Features

- Plan and build modes in one session
- `read`, `write`, `edit`, `glob`, `grep`, and shell tools
- Exact-match edits with a terminal diff
- Live model reasoning inside a `---` block when the provider sends it. Gemini is asked for a low thought summary; that summary is not part of the answer
- Answer tokens stream as they arrive. There is no `minicode >>` prefix
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
| `/model` | List the loaded models as `N id`, with a blank line above and below. |
| `/model N` | Switch to model number `N` from that list. |
| `/model <id>` | Switch to another loaded model by id for this session. |
| `exit` / `quit` / `bye` | Leave MiniCode. |

Switching modes keeps the same conversation and history. Neither command is
sent to the model.

## Example session

```text
Sandbox: C:\path\to\project

Mode: plan | Tools Loaded: read, glob, grep, bash

user >> read pyproject.toml and summarize the dependencies

|Tools Used: `read` ({"path": "pyproject.toml"})|

The project depends on openai, pydantic, and python-dotenv.

---
Model: gemini-3.5-flash-lite | Mode: plan | Tools Loaded: read, glob, grep, bash
Sandbox: C:\path\to\project
1,204 In | 48 Out | 48 Session | Elapsed: 2.1s
---

user >> /build
Mode: build | Tools Loaded: read, write, edit, glob, grep, bash
```

If the model streams reasoning, it appears between `---` lines, under
`Thinking:`, and those lines close before the answer or the first tool line.
Gemini is asked for a low summary; it is shown in that block and is not part
of the answer. Not every model sends reasoning; when it does not, the block
does not appear. The answer streams as the tokens arrive. There is no
`minicode >>` prefix.

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

Sessions and resume, cache control, cost display, compaction, a diff viewer,
`AGENTS.md` injection, MCP, subagents, and a graphical interface. Context
percentage stays off until a verified `context_window` is set. Cost display
waits until more models are added. Ctrl+C during a model call or a tool call
aborts that step and returns to `user >>`. A grandchild shell process can
survive.
