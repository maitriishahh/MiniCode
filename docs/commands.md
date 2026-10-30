# Commands

**Status:** shipped · **Layer:** 6-10 · **Files:** `__main__.py`
**Verified:** 2026-10-30

Every slash command is handled in the REPL before any model call and is never
sent as a prompt. Anything that starts with `/` and reaches the end of the
handler chain prints an unknown-command line and is not sent either.

The command list itself is the `COMMANDS` tuple in `__main__.py`. `/help` prints
it and nothing else; there is no second help string anywhere.

## Contract

| Command | Effect |
|---|---|
| `/plan` | Switch to plan mode. `write` and `edit` leave the tool list. |
| `/build` | Switch to build mode. Every tool is available. |
| `/models` | List loaded models. |
| `/models N` | Switch to model number `N` for this session. |
| `/models <id>` | Switch to a loaded model by id for this session. |
| `/new` | Save, then start a clean session with every setting at its startup default. |
| `/sessions` | List this workspace's saved sessions, newest first. |
| `/sessions N` | Resume session number `N`, or a full session id. |
| `/sessions N rename [name]` | Rename. Prompts when the name is missing. |
| `/sessions N delete` | Delete after a `[Y/N]` confirmation. |
| `/export [path]` | Write the transcript to a `.txt`. |
| `/thinking` | List `off` and `on`. |
| `/thinking N` / `/thinking off\|on` | Set reasoning display. |
| `/effort` | List `low`, `medium`, `high`. |
| `/effort N` / `/effort low\|medium\|high` | Set effort. |
| `/args` | List `off` and `on`. |
| `/args N` / `/args off\|on` | Set tool-argument display. |
| `/output` | List `off` and `on`. |
| `/output N` / `/output off\|on` | Set shell-output display. |
| `/help` | Print the command list. |
| `exit` / `quit` / `bye` | Leave. Not a slash command. |

Aliases: `del` for `delete`, `ren` for `rename`. Session actions are
case-insensitive; a bare number is always a list position, never an id.

Default settings: mode `plan`, thinking `off`, effort `low`, args `off`,
output `off`, model `default_id`.

### Output

Each entry is the exact text `__main__.py` prints, with the surrounding blank
lines as they appear.

**Mode.** `/plan` and `/build` always rewrite `messages[0]`, even when the mode
is already active.

```text
Mode: build | Tools Loaded: read, write, edit, glob, grep, bash
```

**Lists.** `/models`, `/thinking`, `/effort`, `/args`, `/output` share one
shape: a blank line, one row per choice, a blank line. The active value carries
a trailing ` (active)`.

```text
1 off
2 on (active)
```

**Set.** Setting a listed value prints `{Label}: {value}`.

```text
Model: gemini-3.5-flash-lite
Thinking: on
Effort: medium
Args: on
Output: on
```

A rejected value prints `Unknown {Label}: {token}`. The labels are `Model`,
`Thinking`, `Effort`, `Args`, `Output`, and `Session`.

**`/new`.** Saves first, prints `New session`, then the status block with no
usage line.

**`/sessions`.** One row per session: position, title, creation stamp, and
` (active)` when it is the current one. A title's trailing ` - 20...` date is
stripped for display.

```text
1 Fix login redirect - 29-10-2026 14:25 (active)
2 New session - 29-10-2026 12:04
```

`(no saved sessions)` when the workspace has none. A corrupt file is reported
as `Session Error: {file}: {reason}` and skipped.

**`/sessions N`.** `Resumed: {title}`, the replayed transcript, then the status
block rebuilt from the saved turn.

**`/sessions N rename`.** `Renamed: {name}`. With no name on the line, asks
`New name: `. An empty or control-only name prints `Cancelled`.

**`/sessions N delete`.** Asks `Delete session "{title}"? [Y/N] `. Anything
other than `y` or `yes` prints `Cancelled`. A delete prints `Deleted: {title}`.

**`/export`.** `Exported as {path}` with a workspace-relative path inside the
workspace and an absolute forward-slash path outside it. `.env` is refused with
`Export Error: refusing to write .env files`. A session that has not started
prints `Nothing to export yet`.

**`/help`.** A blank line, then for each entry `{name}: {summary}`, then
`example: {example}` when the entry has one, then a blank line.

**Failures.**

```text
Unknown command: /model. Use /models.
Unknown command: /foo. Use /help.
Unknown Session: 9
Unknown Session action: frobnicate
Session Error: {message}
```

`/model` is not a command. It is caught by name and answered with the `/models`
hint rather than the generic line, because the rename is recent enough that it
is the likely mistake.

## Why this shape

One handler per command in `__main__.py`, one row in `COMMANDS`, one README row.
The handler is written by hand; the table is not generated from it, because the
handler needs behaviour the table cannot express, and a generated table would
drift from `__help` differently.

`/models` is the loaded-list command, not a provider catalog. A model id is
switched for the session only, so a restart returns to `default_id`.

Commands that change a setting save the session immediately. Commands that only
read never save.

## Invariants

- Slash input never reaches the model. `__main__.main`.
- A bare integer selects a list position before an id is considered.
  `__main__._target`, `__main__._listed`.
- `/plan` and `/build` assign `messages[0]` unconditionally.
- `/new` and deleting the active session both reset mode, model, thinking,
  effort, args, and output. `__main__._reset_current`.
- `/model` stays a special-cased error. `__main__.main`.

## Edge cases

| Input | Result |
|---|---|
| `/models 0` | `Unknown Model: 0` |
| `/models 99` | `Unknown Model: 99` |
| `/models gemini-3.5-flash-lite` | switches, prints `Model: ...` |
| `/sessions 1 delete now` | `Unknown Session action: delete now` |
| `/sessions abc` | `Unknown Session: abc` |
| `/thinking 3` | `Unknown Thinking: 3` |
| `/thinking ON` | `on`; the value is lowercased |
| `/help x` | exact `/help` only; `/help x` is unknown-command |
| `/export .env` | refused, no write |
| empty line | ignored, no save |
| Ctrl+C at `>>> ` | leaves |

## Verification

- `/help` prints every row of `COMMANDS` once, with examples where defined.
- `/models 0` and `/models 99` print the unknown line and do not switch.
- `/sessions` marks the active session and lists newest first.
- `/sessions N rename` with no name prompts; an empty answer cancels.
- `/new` prints the status block with no usage line.
- `/foo` prints the unknown-command line and the turn does not start.
- `/model` prints the `/models` hint.

## Gaps

- No argument completion, no history recall, no aliases beyond `del` and `ren`.
- A command cannot be chained in one line.

## History

- 2026-09-26  `/model` was the command. It became `/models` on 2026-10-28 and
  `/model` was kept as a named error.
- 2026-10-24  `/help` arrived, replacing a header that printed the command list
  at startup.
- 2026-10-30  The `/new` help line said "Current settings are kept". The handler
  has always reset them; the summary was wrong and was corrected.
