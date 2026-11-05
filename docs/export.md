# Export

**Status:** shipped · **Layer:** 9 · **Files:** `__main__.py`
**Verified:** 2026-11-06

`/export` writes the current conversation to a plain-text file in the same shape
the resume replay prints. It is a view of live state: no model call, no message
append, no save, no change to any counter.

## Contract

| Input | Result |
|---|---|
| `/export` | write `<title> - <session id>.txt` in the workspace root |
| `/export <path>` | write there, absolute or workspace-relative |
| `/export` before the first message | `Nothing to export yet`, no file |
| `/export .env` or `/export .env.local` | `Export Error: refusing to write .env files`, no file |
| outside the workspace | `external_directory` prompt, then write or deny |
| `/export my notes.txt` | the whole remainder is the path, spaces included |

The default name comes from the session title and id:

```python
def _export_name(title: str, session_id: str) -> str:
    # Remove any trailing date stamp like "- 2026-10-29 21:36"
    clean = _strip_stamp(title)
    # Remove characters not allowed in filenames
    safe = _INVALID_CHARS.sub("", clean).strip()
    suffix = f" - {session_id}" if session_id else ""
    return f"{safe or 'New Session'}{suffix}.txt"
```

A trailing date stamp is removed, then characters that Windows cannot use in a
filename. The session id is appended after both, so two sessions with the same
title get different files and a re-export of one session overwrites its own.
An empty title falls back to `New Session`. The fallback title
`New session - 2026-10-31 14:25` therefore exports as
`New session - 20261031-142500-3d1d.txt`; the id is the session's own.

Because the name follows the title, a rename or a late title changes the default
target. The previous file stays where it was.

### File shape

```text
Fix login redirect
Exported: 29-10-2026 15:02

>>> the login form redirects to / instead of /home

I found the handler in auth.py...

|Tool Used: `read`
```

- Line 1 is the stored title verbatim; line 2 is the local export time. The
  `created` stamp is not repeated, because the fallback title already carries
  its own date. `Exported:` uses `%d-%m-%Y %H:%M`, the same shape as
  `/sessions`.
- A blank line, then `_transcript()` joined with one blank line between blocks,
  then one trailing newline.
- No model id and no mode: both can change mid-session and would misdescribe
  earlier turns.
- No system prompt, no `role: "tool"` bodies, no reasoning. A call marked
  `note` is omitted the same way replay omits it.
- Tool lines follow the current `/args` value, exactly as replay does.
- `[interrupted by user]` and `[model error]` export as written.
- Newlines are `\n` via `newline="\n"`, matching session files and git.
- An existing file is overwritten.

### Path handling

`_export` classifies the given path with `resolve_path.classify` and never calls
`_resolve`:

| Kind | Handling |
|---|---|
| `inside` | write, then print the path relative to the workspace |
| `dotenv` | `Export Error: refusing to write .env files` |
| `external` | `permissions.decide("external_directory", path)`; deny prints `Permission denied: external_directory {path}` |

`.env.example` classifies as inside, so it is not refused; the rule is about the
secret, not the template. On Windows the name check is case-insensitive, so
`.ENV` is refused even before the file exists. A leading `~` or `~/` is expanded
by `classify` before the workspace check, so `~/notes.txt` is outside and asks.
`~user` is not expanded. Parent directories are created, like `write`.

Success prints the workspace-relative path for an inside target and an absolute
forward-slash path for an outside one:

```text
Exported as notes/session.txt
```

## Why this shape

**One formatter for the screen and the file.** `_transcript()` builds the
blocks; `_replay` prints them and `_export` writes them. A second formatter for
export would drift from what resume shows, and the export is supposed to be
what the user saw.

**No tool bodies.** The transcript is the conversation, not the filesystem. A
`read` result can be a whole file and a shell result can be a build log; neither
belongs in a document the user might paste somewhere. The tool line records that
the call happened.

**No model metadata.** The model and mode change during a session, so a single
header value would be wrong for most of the file. The stored title already
names the conversation. Repeating `created` doubled the date on a fallback
title such as `New session - YYYY-MM-DD HH:MM`.

**The id belongs in the filename.** A title-only name made two sessions share
one file. The session id is unique and does not change on rename, so a
re-export still overwrites that session's file and leaves the other alone.

**The permission path is `decide`, not `_resolve`.** `_resolve` raises for
`.env` and outside paths; export needs to print a specific message and offer the
same `external_directory` prompt the tools use. Calling `decide` directly reuses
the rule without the exception.

**`.txt`, not Markdown or JSON.** The session file is already the structured
form. The export is for a human or a chat window, and Markdown would escape the
prompts.

## Invariants

- Export never appends a message and never calls `_save()`. `__main__._export`.
- `.env` is refused before any write. `classify` decides, so `resolve_path` owns
  the rule.
- An outside target uses `external_directory`, the same key as the tools.
- `_transcript` omits every `role: "tool"` body. A call with `note` true is
  omitted; a saved message without `note` falls back to `__main__._NOTE_PREFIXES`.
- The header is the stored title, then `Exported:`. The stored title is not
  stripped.
- The file ends with exactly one newline when it has blocks.

## Edge cases

| Input | Result |
|---|---|
| `/export` with a trailing space | default name |
| `/export ..\out.txt` | asks; deny writes nothing |
| `/export` answered `always` | the next export to that path does not ask |
| a target that is a directory | `Export Error:` from `OSError` |
| a session with no messages | header lines only |
| two sessions, same title | different default names; each file stays |
| export before the title worker lands | `New session - {id}.txt`; a later export writes the titled file and leaves the first |
| `/export ~/notes.txt` | expands to the home path and asks |
| rename, then export | a new file; the old one stays |
| plan mode | works; `/export` is not `write` or `edit` |
| `/export` after `/new` | `Nothing to export yet` |

## Verification

- One turn, then `/export`: default name, two header lines, the prompt, the
  answer, the tool line.
- Search the file for a string that came only from a `read` or shell result; it
  must be absent.
- `/export out.txt` writes inside; `/export ..\out.txt` asks and a deny writes
  nothing.
- `/export .env` prints `Export Error:` and writes nothing; `.env.example` writes.
- `/export` as the first command prints `Nothing to export yet`.
- Export twice: one file, the second content.
- `/help` lists `/export`.

## Gaps

- No Markdown, JSON, or HTML export, and no range selection.
- No timestamped default name, so a second export of the same session overwrites.
- `~user` is not expanded.
- The export includes tool names and arguments but not results, so a transcript
  cannot be replayed from the file.

## History

- 2026-10-30  `/export` arrived, sharing `_transcript()` with the resume replay.
- 2026-10-31  Windows `.ENV` names classify as `dotenv`, so the export refuses
  them instead of creating a secrets file.
- 2026-11-06  The default name appends the session id, and the header keeps the
  stored title without a second date.
- 2026-11-06  A leading `~` expands before classification, including `/export`.
- 2026-11-06  Replay trusts a stored `note` and falls back to the old prefixes.
