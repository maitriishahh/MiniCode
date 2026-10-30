# Modes

**Status:** shipped · **Layer:** 4 · **Files:** `agent.py`, `__main__.py`
**Verified:** 2026-10-30

Two modes over one conversation. `plan` reads and reasons; `build` reads,
reasons, and writes. The difference is the tool list the model receives, plus a
dispatch check for the tools that are absent. Nothing else about the turn
changes.

## Contract

| Mode | Tools offered | `messages[0]` |
|---|---|---|
| `plan` | every tool except `write` and `edit` | `SYSTEM + " " + PLAN_SYSTEM` |
| `build` | every tool | `SYSTEM` |

`mode = {"name": "plan"}` in `agent.py` is the single copy of the state.
`__main__.py` imports it and never keeps its own `MODE`. Process startup is
`plan`; `/new` and deleting the active session reset to `plan`; a resumed
session restores whatever mode was saved.

`PLAN_DENIED = ("write", "edit")`. It is applied twice:

```python
"tools": active_schemas(),          # the model is never offered them
...
if mode["name"] == "plan" and name in PLAN_DENIED:
    content = f"Plan mode: `{name}` is disabled. Propose the change and ask to run /build."
```

`active_schemas()` returns `SCHEMAS` in build and filters `PLAN_DENIED` in
plan. `active_names()` mirrors it for `Tools Loaded:`. `TOOLS` itself is never
filtered, so a name that is denied in plan is still registered.

`/plan` and `/build` are exact matches, handled in `__main__.main` before the
user message is appended. They assign `mode["name"]`, rebuild
`messages[0]` from `_system()`, print, and save:

```text
Mode: build | Tools Loaded: read, write, edit, glob, grep, bash
```

The assignment is unconditional, including when the requested mode is already
active. `/plans` is not `/plan`; it is unknown-command input.

The system prompt is rebuilt, not appended:

```python
def _system() -> dict:
    content = SYSTEM + " " + PLAN_SYSTEM if mode["name"] == "plan" else SYSTEM
    return {"role": "system", "content": content}
```

History is never rewritten. Only `messages[0]` changes, so the prefix before
the conversation is identical for every create in a mode and changes once at a
switch.

### `PLAN_SYSTEM`

Reads as one block appended to `SYSTEM`. It says: read, search, reason; do not
create or modify files; do not paste file contents; do not create or delete
files with the shell; never name internal tools; speak in user actions; propose
file, change, reason; if the user asked for a file, end by telling them to run
`/build`; after `glob` returns, read every matching file in the same response;
if the user named a file, read that path instead of globbing first.

The last two sentences exist because a plan turn has one job — understand
before proposing — and the default step budget is 16. They are the only
batching instruction anywhere; `SYSTEM` has none.

## Why this shape

**The tool list is the guarantee, not the prompt.** OpenCode runs plan and
build as the same session with different tool permissions; MiniCode copies the
mechanism and drops the second agent. Asking a model not to write in a prompt
is a request. Removing `write` and `edit` from `tools=` is a fact about the
request body.

**The dispatch check is the backstop.** A guessed name, a replayed history, or
a cached reply can still contain a `write` call. Without the second check the
registry would run it. With it, the model gets a `role: "tool"` string and the
file is untouched.

**One conversation.** Switching modes does not restart, does not clear history,
and does not renumber anything. The user's plan discussion is the build
context.

**No `PLAN.md`.** Pi's plan file is a collaboration convention inside either
mode: an agent-written document you edit together. It is orthogonal to the
restriction. Building the file lifecycle here would not make plan mode safer.

**Shell stays in the plan tool list.** Layer 5 removed `bash` and `powershell`
from plan and Layer 6 put them back, restricted by rules instead
(`docs/permissions.md`). A tool-list deny cannot express "reading is fine,
deleting is not", and a plan turn that cannot run `git diff` is not planning.

## Invariants

- `mode["name"]` is the only mode state. `agent.mode`.
- `PLAN_DENIED` filters the schema and is re-checked at dispatch.
  `agent.active_schemas`, `agent.agent`.
- `TOOLS` is never filtered. Only the view is.
- `messages[0]` is assigned from `_system()`, never concatenated.
  `__main__._system`.
- History is not rewritten on a switch.
- A denied call returns a `role: "tool"` string and prints no `|Tool Used|`
  line. `agent._tool_note`.
- Startup, `/new`, and active delete all land in `plan`.

## Edge cases

| Input | Result |
|---|---|
| `/plan` while already in plan | prints the mode line, saves, no double prompt |
| `/build` while in build | same |
| `/plans` | `Unknown command: /plans. Use /help.` |
| model guesses `write` in plan | `Plan mode: \`write\` is disabled. Propose the change and ask to run /build.` |
| model guesses `bash` in plan | allowed by the tool list; the permission rules decide (`docs/permissions.md`) |
| resume a session saved in build | `messages[0]` is `SYSTEM`, tool list is full |
| resume a session saved in plan | `messages[0]` is `SYSTEM + " " + PLAN_SYSTEM` |
| `/new` from build | plan, defaults, no file until the next message |

## Verification

- Startup status shows `Mode: plan` and omits `write` and `edit` from
  `Tools Loaded:`.
- `/build` shows the full list and the next write runs.
- In plan, a request to change a file produces a proposal that ends with
  `/build`, and no `|Tool Used: \`write\`` line.
- A guessed `write` in plan returns the plan string and leaves the file
  untouched.
- `/plan` then `/build` then `/plan` leaves the transcript intact.
- Resume a build session: the status line says build before the first prompt.

## Gaps

- Two modes only. No per-tool allow list, no read-only build, no auto mode.
- `PLAN_DENIED` is a fixed tuple. A configured set would need the JSON
  permissions file that is still deferred.
- Plan mode still permits a `python -c` that writes, because the shell is
  gated by command text, not by effect.

## History

- 2026-10-09  Plan and build arrived as a filtered `tools=` view over one
  conversation. Startup became plan instead of build.
- 2026-10-21  Shell was added to `PLAN_DENIED` so plan could not run commands.
- 2026-10-23  Shell returned to plan and is restricted by permission rules
  instead. `PLAN_DENIED` is `("write", "edit")` again.
- 2026-10-26  Startup began building `messages[0]` from the restored mode, and
  `/plan` / `/build` began assigning it unconditionally. Before that a process
  that started in plan ran with `SYSTEM` only, and a repeat switch left the
  prompt stale.
