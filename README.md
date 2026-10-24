# MiniCode

A small coding agent for your terminal. It reads and edits files in a workspace,
searches code, runs shell commands, and switches between plan and build modes.
One Python loop over an OpenAI-compatible chat API.

**MiniCode starts in plan mode. Type `/build` to enable file writes.**

## Features

- Plan and build modes in one session
- `read`, `write`, `edit`, `glob`, `grep`, and shell tools
- Exact-match edits with a terminal diff
- Model switching with `/model`
- Workspace-bounded file access with `.env` protection
- Permission prompts for shell commands and paths outside the workspace
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
3. Shell commands and paths outside the workspace ask for permission.
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
Sandbox: C:\Users\you\Desktop\PyCharm Projects\MiniCode

Mode: plan | Tools Loaded: read, glob, grep, bash

user >> read pyproject.toml and summarize the dependencies

~~Thinking...

|Tools Used: `read` ({"path": "pyproject.toml"})|

minicode >> The project depends on openai, pydantic, and python-dotenv.

---
Model: gemini-3.5-flash-lite | Mode: plan | Tools Loaded: read, glob, grep, bash
Sandbox: C:\Users\you\Desktop\PyCharm Projects\MiniCode
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

`glob` and `grep` skip dot-directories, `__pycache__`, `.venv`, and `.env`
files. Both tell the model to refine broad searches.

## Plan and build

**Plan** is for reading, searching, and proposing changes. `write` and `edit`
are not offered to the model, and a guessed call is refused. Shell commands are
still available but ask for permission.

**Build** offers every tool. `write` and `edit` run without a prompt inside the
workspace. Shell commands still ask.

Plan mode is not a hard sandbox: an approved shell command can still change
files. Use build mode deliberately.

## Permissions

| Key | Covers | Default |
|---|---|---|
| `read` | `read` | allow |
| `edit` | `write`, `edit` | allow |
| `glob` | `glob` | allow |
| `grep` | `grep` | allow |
| `shell` | `bash`, `powershell` | ask |
| `external_directory` | paths outside the workspace | ask |

When prompted:

- `o` or `once` allows this call.
- `a` or `always` allows that exact value until MiniCode exits.
- `d`, an empty answer, or Ctrl+C denies the call.

`.env` files are always refused. A denial is returned to the model as
`Permission denied: <key> <value>`.

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
Sandbox: C:\Users\you\Desktop\PyCharm Projects\MiniCode
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

Streaming and abort handling, sessions and resume, cost and context percentage,
compaction, a diff viewer, MCP, subagents, and a graphical interface. Ctrl+C
during a running shell command ends MiniCode rather than cancelling only that
command.
