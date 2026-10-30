# Architecture

**Status:** shipped · **Layer:** 0-10 · **Files:** `src/minicode/*.py`
**Verified:** 2026-10-30

MiniCode is one synchronous agent loop behind an `input()` REPL. A prompt is
appended once, the loop calls the model, runs whatever tools it asks for, and
repeats until the model answers without a tool call or the step limit is
reached. Everything else in the package exists to serve that loop.

## Contract

The turn, exactly:

```text
REPL        append {"role": "user"} once
agent       for step in range(16):
              stream one create
              append the assistant message once
              if no tool_calls: return
              for each call:
                check plan deny, then permission
                run the tool            # never raises out of the loop
                append one {"role": "tool"} per call, same tool_call_id
            reach 16: return "Max limit reached: 16. Try smaller request."
```

| Rule | Where |
|---|---|
| One `chat.completions.create` site in the package | `agent._create` |
| The agent and the title worker both call it | `agent.agent`, `agent.session_title` |
| The REPL appends the user message, once | `__main__.main` |
| The loop never appends the user message | `agent.agent` |
| The history holds plain dicts, never SDK objects | `agent._assistant` |
| Tool code never raises out of the loop | `schema_generator.tool_from_fn` → `run` |
| `max_steps` returns a string | `agent.agent` |

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
tool once at import.

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

## A turn, in order

1. REPL reads a line. `exit`, `quit`, `bye` leave before any model call.
2. A line starting with `/` is handled by a command branch and never sent.
3. Otherwise the first message of a session creates the file and starts the
   title worker; the user message is appended.
4. `agent` resets `last_usage`, picks the active model record, and builds a
   client for it.
5. Each step streams one completion into `_consume`, which separates
   reasoning, text, and tool-call deltas.
6. The assistant message is appended once, as a plain dict.
7. No tool calls means the turn is over. The REPL prints the status block and
   saves.
8. Tool calls are checked against the plan deny list, then permissions, then
   run. Each result is appended as `role: "tool"` with the same id.
9. The step counter increments. At 16 the loop returns the limit message.

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
