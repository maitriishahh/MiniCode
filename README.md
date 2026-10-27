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
         ├─► Final Answer Buffer ──► on_event("text", piece, final=True) ──► Printed via `minicode >>`
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
- Live model reasoning under `Thinking:` / `Thought:` when the provider sends it
- Final answers printed once with `minicode >>`; tool preambles print without it
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

If the model streams reasoning, it appears under `Thinking:` and ends with
`Thought:` before the answer or first tool line. Not every model sends
reasoning; when it does not, neither label appears. Only the final answer
gets `minicode >>`; tool preambles and error notices do not. Content is
buffered per model step so the harness can tell a final answer from a tool
preamble; the final answer is not streamed token by token.
