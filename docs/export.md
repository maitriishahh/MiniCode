# Export

**Status:** shipped · **Layer:** 9 · **Files:** `__main__.py`
**Verified:** 2026-10-30

`/export` writes the current conversation to a plain-text file in the same shape
the resume replay prints. It is a view of live state: no model call, no message
append, no save, no change to any counter.

## Contract

| Input | Result |
|---|---|
| `/export` | write `<title>.txt` in the workspace root |
| `/export <path>` | write there, absolute or workspace-relative |
| `/export` before the first message | `Nothing to export yet`, no file |
| `/export .env` or `/export .env.local` | `Export Error: refusing to write .env files`, no file |
| outside the workspace | `external_directory` prompt, then write or deny |
| `/export my notes.txt` | the whole remainder is the path, spaces included |

The default name comes from the session title:

```python
_TRAILING_STAMP_RE = re.compile(r"\s*-\s*\d{2,4}[-/]\d{2}[-/]\d{2,4}\s+\d{2}:\d{2}$")
_INVALID_CHARS = re.compile(r'[\\/*?:"<>|]')
```

A trailing date stamp is removed, then characters that Windows cannot use in a
filename. An empty result is `New Session.txt`. The fallback title
`New session - 2026-10-30 14:25` therefore exports as `New session.txt`.

Because the name follows the title, a rename or a late title changes the default
target. The previous file stays where it was.

### File shape

```text
Fix login redirect - 29-10-2026 14:25
Exported: 29-10-2026 15:02

>>> the login form redirects to / instead of /home

I found the handler in auth.py...

|Tool Used: `read`
```

- Line 1 is the title and the local `created` stamp; line 2 is the local export
  time. Both use `%d-%m-%Y %H:%M`, the same shape as `/sessions`.
- A blank line, then `_transcript()` joined with one blank line between blocks,
  then one trailing newline.
- No model id and no mode: both can change mid-session and would misdescribe
  earlier turns.
- No system prompt, no `role: "tool"` bodies, no reasoning. History stores none
  of them, so nothing has to be filtered out beyond the tool results.
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
secret, not the template. `~` is not expanded: `~/notes.txt` becomes
`<workspace>/~/notes.txt`. Parent directories are created, like `write`.

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
header value would be wrong for most of the file. The title and the creation
time are the two facts that hold for the whole conversation.

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
- `_transcript` omits every `role: "tool"` body and every call whose result
  starts with a note prefix. `__main__._NOTE_PREFIXES`.
- The header order is title, created, exported.
- The file ends with exactly one newline when it has blocks.

## Edge cases

| Input | Result |
|---|---|
| `/export` with a trailing space | default name |
| `/export ..\out.txt` | asks; deny writes nothing |
| `/export` answered `always` | the next export to that path does not ask |
| a target that is a directory | `Export Error:` from `OSError` |
| a session with no messages | header lines only |
| two sessions, same title | same default name; the later export overwrites |
| export before the title worker lands | `New session.txt`; a later export writes the titled file and leaves the first |
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
- No timestamped default name, so two exports of the same session overwrite.
- Two sessions with the same title collide on the default path.
- `~` is not expanded; there is no home shortcut.
- The export includes tool names and arguments but not results, so a transcript
  cannot be replayed from the file.

## History

- 2026-10-30  `/export` arrived, sharing `_transcript()` with the resume replay.
