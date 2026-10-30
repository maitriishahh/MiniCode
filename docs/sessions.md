# Sessions

**Status:** shipped · **Layer:** 8 · **Files:** `sessions.py`, `__main__.py`
**Verified:** 2026-10-30

One JSON file per conversation, under the user data directory, grouped by
workspace. `/sessions` lists them, `/sessions N` resumes one, and `/new` starts
a clean one. Startup creates nothing.

## Contract

### Location

```text
~/.local/share/minicode/sessions/<project-key>/<session-id>.json
```

On Windows the base is `%USERPROFILE%\.local\share`; on Unix it honors
`XDG_DATA_HOME` and falls back to the same path. The project key is the
workspace directory name, sanitized to `[A-Za-z0-9._-]`, truncated to 40
characters, plus `-` and the first 8 hex characters of the SHA-1 of the resolved
workspace path. On Windows both are case-folded, so `D:\App` and `d:\app` share
a directory. A workspace with no usable name falls back to `workspace`.

The id is local `YYYYMMDD-HHMMSS-xxxx`, where `xxxx` is `token_hex(2)`. A
collision retries. The file is `<id>.json`, and ids sort newest first, which is
why `/sessions` needs no timestamp sort.

### File shape

```json
{
  "version": 1,
  "id": "20261029-142501-a1b2",
  "title": "Fix login redirect",
  "created": "29-10-2026 14:25",
  "updated": "29-10-2026 14:27",
  "cwd": "D:/project",
  "sandbox": "D:/project",
  "model": "gemini-3.6-flash",
  "mode": "build",
  "thinking": "on",
  "effort": "medium",
  "args": "off",
  "output": "on",
  "usage": {"completion_tokens": 1234},
  "last_turn": {"prompt_tokens": 512, "completion_tokens": 96, "Elapsed": 4.2},
  "always": [["external_directory", "d:/other/file.py"]],
  "messages": []
}
```

`messages` excludes the system prompt; `messages[0]` is rebuilt from the current
`SYSTEM`, `PLAN_SYSTEM`, and restored mode on every resume. The raw assistant
dicts are stored exactly as `agent` appended them, including `extra_content`.

`created` and `updated` are local `DD-MM-YYYY HH:MM`; a legacy ISO value is
rewritten on load and saved back in the new shape.

`usage.completion_tokens` is the conversation-lifetime `Session` counter.
`last_turn` holds the last finished turn's `In`, `Out`, and `Elapsed` so a resume
prints the same usage line; a file without it loads zeros, and a session with
history or tokens but no `Elapsed` loads `0.0`. `always` is a sorted list of
exact `[key, value]` permission pairs, already normalized by
`permissions.norm` (`docs/permissions.md`).

### When a save happens

| Moment | Call |
|---|---|
| after a turn, including an aborted one, and at exit | `__main__.main` |
| after `/plan`, `/build`, `/models`, `/thinking`, `/effort`, `/args`, `/output` | each handler |
| before `/sessions` lists, and therefore before resume, rename, and delete | `_show_sessions` |
| after renaming the active session | `_rename` |

Writing nothing is normal: `_save()` returns immediately when there is no
session. The first user message creates the file, and `/new` creates none until
the next message. A failed save prints `Session Error: {detail}` and keeps
working in memory.

`_write` is atomic: the JSON goes to a sibling `.tmp`, then `os.replace` swaps
it in. The encoding is UTF-8 with `ensure_ascii=False`, `indent=2`, and
`newline="\n"`.

### Validation

`_check` rejects a file that is not an object, has a version other than `1`, has
an `id` that matches neither the file stem nor the id pattern, or has a non-list
`messages`. It repairs defaults in memory: a blank title becomes the fallback, a
missing timestamp becomes now, `usage` and `always` become empty, and
`last_turn` is coerced to three fields.

The list skips a bad file and reports `Session Error: {file}: {reason}`;
`/sessions N` reports the same error and does not switch. Nothing repairs a bad
file on disk.

### Commands

| Input | Result |
|---|---|
| `/sessions` | rows newest first, `(no saved sessions)` when empty |
| `/sessions N` | resume that row, or a full id |
| `/sessions N delete` / `del` | confirm, then delete |
| `/sessions N rename [name]` / `ren` | rename, prompting when the name is missing |
| `/new` | save, reset, print `New session` |

Row format: `{n} {title} - {created}{ (active)}`. A title ending in a date stamp
loses that stamp for display. Actions are case-insensitive, names keep their
case, and a bare integer is a row number, never an id.

```text
Resumed: Fix login redirect
Renamed: Fix login redirect
Deleted: Fix login redirect
Cancelled
Unknown Session: 9
Unknown Session action: frobnicate
```

Deleting the active session does what `/new` does: reset every setting to its
startup default, clear `always`, reset `Session`, rebuild history from the
system message, and leave no file until the next message. Deleting another
session saves the current one first and does not switch.

An active rename locks the title so the pending title thread cannot overwrite
it, then saves. A non-active rename loads the target, writes the new title and
`updated`, and leaves the current session alone. A name is cleaned — control
characters to spaces, whitespace collapsed, empty rejected, 200 characters
maximum — and duplicates are allowed.

### Resume

`_apply_session` restores the model (only if still loaded), mode, thinking,
effort, args, output, `always`, `Session`, and `last_turn`, then prints
`Resumed: {title}`, replays the transcript, and prints the status block.

Replay prints `>>> {prompt}`, each assistant text, and one tool line per call
that actually ran. It never prints a `role: "tool"` body, so file contents and
command output do not reappear. A call whose result starts with `Plan mode:`,
`Permission denied:`, `Unknown tool:`, `Tool error:`, or `Model Error:` gets no
tool line. Tool lines follow the restored `/args` value.

### Title

After the first message is saved, one daemon thread asks the active model for a
title: `TITLE_SYSTEM`, the first 2000 characters of the prompt, `max_tokens=64`,
`stream=False`, `timeout=30.0`, `max_retries=1`, no tools. The answer is cleaned
(thought tags, surrounding quotes and markdown, a leading `title:`), capped at
60 characters, and assigned under `_TITLE_LOCK` only if the title is not locked
and the session is still current.

The worker does no file I/O, printing, message append, or usage accounting; the
main thread saves it. Exit joins it for at most 2 seconds, a rename wins, and
title tokens never enter `In`, `Out`, `Session`, or history. The fallback is
`New session - YYYY-MM-DD HH:MM` local, so a row always exists before the
summary lands.

## Why this shape

**A file per session, not a database.** A session is a small document written
and read whole: inspectable with `cat`, survives a killed process, and isolates
corruption to one conversation. Atomic replace is enough concurrency control for
a single-process REPL. A database earns its place when there is a query across
sessions, and there is none yet.

**Project-scoped storage.** OpenCode also stores sessions per project, because a
coding session only means anything in the directory it was about. The project
key makes `/sessions` a view of the current workspace instead of a junk drawer,
and it costs one hash.

**No system prompt on disk.** The prompt is code and it changes. Storing it
would freeze an old tool list into a resumed conversation; rebuilding
`messages[0]` from the current mode keeps the prompt matching the binary.

**The id is the sort key.** A timestamp in the id removes a sort field and a
tie-break.

**Titles are generated, not truncated.** A first line is often "can you look
at..." and useless in a list; a summary is one cheap call with a fallback.
Running it on a daemon thread keeps it out of the answer's path, and the lock
means a rename is never overwritten by a late reply.

**Counters are restored, not recounted.** `Session` is persisted because it is
conversation lifetime, and history stores no per-message usage to recount from.

## Invariants

- `messages` on disk never contains a system message.
  `sessions._snapshot`.
- Thinking and reasoning are never stored.
- `usage.completion_tokens` is the only usage field; prompt tokens are never
  added to it. `sessions._snapshot`.
- Writes are atomic. `sessions._write`.
- The title worker touches only `session["title"]`, only under the lock, and
  only when the session is still current. `__main__._start_title`.
- The title call never updates usage. `agent.session_title`.
- A bad file is skipped by the list and raises on direct load.
- `/new` and an active delete leave no file behind.

## Edge cases

| Input | Result |
|---|---|
| first prompt of a new session | file created before the model call |
| empty prompt | no file, no title thread |
| `/sessions` before any prompt | `(no saved sessions)` |
| `/sessions 0`, `/sessions 99` | `Unknown Session: 0` / `: 99` |
| `/sessions 1 delete now` | `Unknown Session action: delete now` |
| delete, answer `n`, empty, EOF, or Ctrl+C | `Cancelled`, nothing removed |
| rename to spaces only | `Cancelled` |
| rename to 300 characters | stored at 200 |
| resume a session whose model is unloaded | keeps the current model |
| resume a session saved in plan | plan, `SYSTEM + " " + PLAN_SYSTEM` |
| same workspace, two processes | last writer wins; no file lock |

## Verification

- New workspace, one prompt: one file under the project key, no system message,
  no reasoning.
- `/sessions` marks the active row; `/sessions N` restores settings, `Session`,
  and the last usage line, then replays the transcript.
- Resume a saved `build` session: the first status line says build.
- `/new` prints the block with no usage line and no file until the next prompt.
- Delete the active session: settings reset, `always` clears, the row is gone.
- Delete a non-active session: the current conversation continues unchanged.
- Rename the active session, then wait for the title worker: the name stays.
- Corrupt one file: the list prints `Session Error:` and skips it; a direct
  resume reports the same error and does not switch.

## Gaps

- No compaction and no message cap. A long session grows until the model
  refuses it.
- No search across sessions and no global list; only the current workspace.
- Two processes in one workspace share the directory with no lock, so the later
  save wins.
- A title is generated from the first prompt only, so a conversation that
  changes direction keeps its first name until renamed.
- No reasoning capture, by design: a resumed session shows the answer but not
  why the model chose it.
- No `/resume` flag at startup, and a corrupt file is reported but never
  repaired, quarantined, or removed.

## History

- 2026-10-29  Sessions arrived: one JSON file per workspace, list, resume,
  rename, delete, `/new`, the title thread, and persisted `always`.
- 2026-10-30  Timestamps became local `DD-MM-YYYY HH:MM`, with ISO values
  rewritten on load. Session paths and the status line restored by a resume
  were fixed in the same pass.
