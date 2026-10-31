# Architecture

**Status:** shipped · **Layer:** 0-10 · **Files:** `src/minicode/*.py`
**Verified:** 2026-10-30

MiniCode is one synchronous agent loop behind an `input()` REPL. A prompt is
appended once, the loop calls the model, runs whatever tools it asks for, and
repeats until the model answers without a tool call or the step limit is
reached. Everything else in the package exists to serve that loop.

## Flow

The turn as the REPL sees it. Which edges are import-time is in the tables
below. The permission rules are `docs/permissions.md`.

```text
  [ User / Terminal ]
         │
         ▼  (types prompt, e.g. "Fix calculator.py" or `/build` or `/models`)
  [ __main__.py ] (REPL loop, sessions, title thread, usage tracking)
         │
         ├─► Command handled locally? (any slash command, or exit/quit/bye)
         │
         ▼  (otherwise appends user message to history, calls agent)
  [ agent.py ] (Agent Core & Multi-Step Turn Loop - max 16 steps)
         │
         ├─► _create(...) (one chat.completions.create site)
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

## Contract

The loop itself — the message flow, the 16-step ceiling, and what `agent`
returns — is owned by `docs/loop.md`. This doc covers only where the code
lives and what crosses between modules.

| Rule | Where |
|---|---|
| One `chat.completions.create` site in the package | `agent._create` |
| The agent and the title worker both call it | `agent.agent`, `agent.session_title` |
| The history holds plain dicts, never SDK objects | `agent._assistant` |
| Tool code never raises out of the loop | `schema_generator.tool_from_fn` → `run` |
| No tool imports the model client | `tools/` |
| No module imports the REPL | all |

`MAX_STEPS` is 16.

## Modules

| File | Holds |
|---|---|
| `__main__.py` | REPL, slash commands, session lifecycle, title thread, transcript and export, status print |
| `agent.py` | the loop, `SYSTEM`, `PLAN_SYSTEM`, `TITLE_SYSTEM`, `_SERVERS`, `TOOLS`, `SCHEMAS`, the mode and display state, `_create`, `_consume`, `_permit` |
| `schema_generator.py` | `tool_from_fn`: docstring and type hints to schema and validator |
| `resolve_path.py` | `SANDBOX`, `classify`, `_resolve`, `approve` |
| `permissions.py` | `RULES`, `check`, `decide`, `force_ask`, `plan_touches`, `ALWAYS` |
| `sessions.py` | session JSON, ids, list, load, save, rename, delete |
| `tools/` | `read`, `write`, `edit`, `glob`, `grep`, `shell` |

The loop owns dispatch. No tool imports the model client. No module imports the
REPL.

## Edges

Every cross-module edge in the package, labelled by when it happens.

| From | To | Kind | What crosses |
|---|---|---|---|
| `__main__` | `agent` | runtime | `agent(messages, on_event)`; reads `SYSTEM`, `mode`, `active`, `MODELS`, `last_usage`, `session_usage` |
| `__main__` | `sessions` | runtime | `new_session`, `save`, `load`, `list_sessions`, `rename`, `delete` |
| `__main__` | `permissions` | import-time | registers `permission_ask["fn"] = _permission` |
| `__main__` | `permissions` | runtime | `restore_always` on resume and reset |
| `__main__` | `resolve_path` | import-time | reads `SANDBOX`, `classify` |
| `__main__` | `tools.shell` | import-time | reads the `output` display flag |
| `agent` | `schema_generator` | import-time | `tool_from_fn` wraps each tool once |
| `agent` | `permissions` | runtime | `decide`, `force_ask`, `plan_touches` |
| `agent` | `resolve_path` | runtime | `classify`, `approve`, `clear_approved` |
| `agent` | `sessions` | import-time | `sessions.data_root()` inside `SYSTEM` |
| `agent` | OpenAI | runtime | the one `chat.completions.create` |
| `sessions` | `permissions` | runtime | `snapshot_always` at save |
| `sessions` | `resolve_path` | import-time | reads `SANDBOX` for the project key |
| `permissions` | `__main__` | callback | calls the registered prompt |
| `tools` | `resolve_path` | runtime | `_resolve`, `SANDBOX` |

`permissions` is a policy gate, not a parent of the tools it governs. It
decides and remembers; `agent._permit` applies the decision; the tool never
sees a permission call. `schema_generator` is not in the turn: it wraps each
tool once at import. `agent.py`, `tools/edit.py`, and `tools/shell.py` print
to stdout. The title worker does no file I/O and no printing; the main thread
saves.

## Import order

`agent.py` calls `load_dotenv()` before any `os.getenv`, and imports
`sessions`, which imports `permissions` and `resolve_path`. `SANDBOX` is
resolved at import from `sys.argv` and the working directory, so `--sandbox`
must be on the command line at process start. Nothing re-reads it later.

`agent.py` builds `MODELS` at import by walking `_SERVERS` and keeping the
servers whose id env is non-empty. A server with no id is skipped, not
disabled later.

`TOOLS` and `SCHEMAS` are built at import by wrapping each tool function.
`shell.__name__` is already the loaded shell's name by then, so the registry
key is `bash`, `sh`, or `powershell`, never `shell`.

## A turn across modules

The ordering rules are in `docs/loop.md`. This is the same turn seen by module.

1. `__main__.main` reads the line and handles any slash command. Nothing
   starting with `/` reaches `agent`.
2. `__main__` creates the session file on the first message and starts the
   title worker.
3. `agent.agent` resets usage, resolves the model record, and builds a client.
4. `agent._create` streams one completion. `_consume` separates reasoning,
   text, and tool-call deltas.
5. `agent._permit` answers allow or deny for each call, then the wrapped tool
   runs and returns a string.
6. Back in `__main__`, the status block prints from `last_usage` and
   `session_usage`, and `sessions.save` writes the file.

## Verification

- `uv run python -m minicode` prints `Type /help for available commands` and a
  status block, then waits at `>>> `.
- One prompt that needs a tool produces exactly one `|Tool Used:` line and one
  status block.
- `grep -rn "chat.completions.create" src/` returns one hit, in
  `agent._create`.
- `grep -rn "from minicode.agent" src/minicode/tools/` returns nothing.

## Gaps

- History is unbounded. Compaction is deferred until the context gap hurts on a
  real codebase.
- No automated tests. Verification above is manual.
- `agent.py` carries a commented-out alternative `session_title` implementation
  from an earlier attempt. It is dead code and should be deleted in a code
  pass, not a docs pass.

## History

- 2026-09-30  Transport moved from LiteLLM to the `openai` package. One create
  site replaced the per-call LiteLLM completion helper.
- 2026-10-04  Package split from a single module into `agent`, `__main__`,
  `schema_generator`, `resolve_path`, and `tools/`.
