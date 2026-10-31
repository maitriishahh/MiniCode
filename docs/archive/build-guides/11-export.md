# 11 — Export

Do first: `docs/10-sessions.md`. Layer 9 is committed. This layer adds
`/export`. It writes the current session transcript to a `.txt`. It does not
add a model call, a session schema change, reasoning capture, a diff viewer,
or compaction.

The command, the formatter, and the file write live in `__main__.py`.
Export itself does not change `sessions.py`. No new module, no new dependency.

## What it is

`/export` writes the current conversation as plain text, in the same shape
the resume replay prints. `/export path` writes it where you say. A session
that has not started yet has nothing to export.

The export is display, not history. It never calls the model, never appends a
message, never saves the session, and never changes `last_usage` or
`session_usage`.

```
/export
/export notes/session.txt
```

| Command | Effect |
|---|---|
| `/export` | Write `<title>.txt` in the workspace root. |
| `/export <path>` | Write to that path, absolute or workspace-relative. Outside asks. |
| `/export .env` | Refused. No write. |

The default filename comes from the session title. A trailing date stamp such
as ` - 2026-10-29 21:36` is removed, then characters that are invalid in a
filename (`\ / * ? : " < > |`) are removed. An empty result becomes
`New Session.txt`. For a title `The Evolution of Artificial Intelligence`:

```
The Evolution of Artificial Intelligence.txt
```

The fallback title `New session - YYYY-MM-DD HH:MM` loses its stamp and exports
as `New session.txt`. A title change, including a rename or the background
title landing, changes the default filename; the old file stays where it was.

`~` is not expanded. Use an absolute path or a workspace-relative one.

## File shape

```text
The Evolution of Artificial Intelligence - 29-10-2026 14:50
Exported: 29-10-2026 15:02

>>> write an essay on ai evolution

The Evolution of Artificial Intelligence: ...

|Tool Used: `bash`
```

- Line one is the title and the local `created` stamp. Line two is the local
  export time. Both use the same `%d-%m-%Y %H:%M` shape as `/sessions`.
- A blank line follows the header.
- The body is `_transcript()` joined with one blank line between blocks, and
  one trailing newline.
- No model id, no mode. Both can change mid-session and would lie about
  older turns.
- No system prompt. History does not store one.
- No `role: "tool"` bodies. File contents, search results, and shell output
  stay out. What `/output off` hid stays hidden.
- No reasoning. History does not store it.
- Tool lines follow the current `/args` value, exactly like replay. `/args
  off` prints the name only; `/args on` prints the one-liner or the left rail.
- `[interrupted by user]` and `[model error]` markers export as written.
- Newlines are `\n`, written with `newline="\n"`. That matches session files
  and git, not the platform default.
- An existing target is overwritten. The default name is per session, so a
  re-export replaces the same file.

## Keep

- `sessions.py`, its schema, and `last_turn`.
- `_resume`, `_replay`'s output, `_status()`, `_save()`, and `_NOTE_PREFIXES`.
- The `/sessions` handler and every other command.
- `session_usage`, `last_usage`, and the status block. Export changes none.

## Replace `_replay`

Split the block builder out so the screen and the file share one formatter.
The printed output does not change.

```python
def _transcript() -> list[str]:
    results: dict[str, str] = {}
    for message in _STATE["messages"][1:]:
        if message.get("role") == "tool" and isinstance(message.get("content"), str):
            results[message.get("tool_call_id", "")] = message["content"]
    blocks: list[str] = []
    for message in _STATE["messages"][1:]:
        role = message.get("role")
        if role == "user":
            blocks.append(f">>> {message.get('content', '')}")
        elif role == "assistant":
            content = message.get("content")
            if isinstance(content, str) and content:
                blocks.append(content)
            for call in message.get("tool_calls") or []:
                if not isinstance(call, dict):
                    continue
                if results.get(call.get("id", ""), "").startswith(_NOTE_PREFIXES):
                    continue
                function = call.get("function") or {}
                line = _tool_line(function.get("name", "?"), function.get("arguments", ""))
                blocks.append(line)
    return blocks


def _replay() -> None:
    blocks = _transcript()
    if blocks:
        print("\n\n".join(blocks))
```

## Add `_export_name`

```python
_INVALID_CHARS = re.compile(r'[\\/*?:"<>|]')
_TRAILING_STAMP_RE = re.compile(r"\s*-\s*\d{2,4}[-/]\d{2}[-/]\d{2,4}\s+\d{2}:\d{2}$")


def _export_name(title: str) -> str:
    clean = _TRAILING_STAMP_RE.sub("", title).strip()
    safe = _INVALID_CHARS.sub("", clean).strip()
    return f"{safe or 'New Session'}.txt"
```

The trailing-stamp pattern removes both the fallback's `YYYY-MM-DD HH:MM`
suffix and a `DD-MM-YYYY HH:MM` suffix. The invalid-character pattern covers
Windows' reserved filename characters.

## Add `_export`

```python
def _export(raw: str) -> None:
    session = _STATE["session"]
    if session is None:
        print("\nNothing to export yet\n")
        return
    blocks = _transcript()
    text = (
        f"{session.get('title', 'Untitled')} - {_stamp(session.get('created', ''))}\n"
        f"Exported: {datetime.now():%d-%m-%Y %H:%M}\n"
    )
    if blocks:
        text += "\n" + "\n\n".join(blocks) + "\n"
    target = None
    kind = "inside"
    given = raw.strip()
    if given:
        kind, target = classify(given)
        if kind == "dotenv":
            print("\nExport Error: refusing to write .env files\n")
            return
        if kind == "external":
            shown = target.as_posix()
            if decide("external_directory", shown) == "deny":
                print(f"\nPermission denied: external_directory {shown}\n")
                return
    if target is None:
        target = SANDBOX / _export_name(session.get("title", "New Session"))
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    except OSError as exc:
        print(f"\nExport Error: {exc}\n")
        return
    if kind == "inside":
        shown = target.relative_to(SANDBOX).as_posix()
    else:
        shown = target.as_posix()
    print(f"\nExported as {shown}\n")
```

Notes:

- `classify` resolves the path and returns `inside`, `dotenv`, or `external`.
  It also rewrites a Git Bash drive path on Windows.
- `decide("external_directory", ...)` is the same rule the tools use. `once`
  and `always` both write; `always` is saved in the session on the next save.
  A deny returns the same `Permission denied:` line as a tool.
- Do not call `_resolve`. It refuses `.env` and outside paths with a
  `ValueError`; this path already handled both with a printed line.
- Do not call `_save()`. Export reads live state and mutates nothing.
- `target.parent.mkdir` matches `write`: a missing directory is created.
- A directory path, a locked file, or a full disk becomes `Export Error: ...`
  and no traceback.
- `kind == "inside"` covers the default name too. `relative_to` is safe
  because `classify` proved the target is under `SANDBOX`.
- The default target is `SANDBOX / _export_name(session["title"])`. It moves
  when the title changes; it is not tied to the session id.

## Add imports

```python
import re

from minicode.permissions import ask as permission_ask, restore_always, decide
from minicode.resolve_path import SANDBOX, classify
```

## Add the handler

After the `/sessions` block, before `/plan`:

```python
        if stripped == "/export" or stripped.startswith("/export "):
            _export(stripped[len("/export"):])
            continue
```

It must stay before the unmatched-slash guard, so `/export` is a command and
not `Unknown command`.

## Add the `COMMANDS` row

After the `/sessions` row:

```python
    ("/export", "Write this session's transcript to a .txt in the workspace.", "/export notes/session.txt"),
```

`/help` prints it. Do not write a second help string.

## Same pass, docs

- `README.md` commands table, after the `/sessions` rows:

  ```
  | `/export` | Write the current session transcript to a `.txt` named from the session title in the workspace. |
  | `/export <path>` | Write it to that path. A path outside the workspace asks. `.env` is refused. |
  ```

- `README.md` sessions section: one sentence. Export is the replay shape, no
  tool bodies, no reasoning, and an explicit path follows the permission rules.
- `AGENTS.md`, sessions bullet: one sentence. `/export` writes `_transcript()`
  with a title/created/exported header, defaults to the title-derived name, uses
  `external_directory` for an outside path, refuses `.env`, works in plan, and
  is not a tool call.
- `docs/STATUS.md`: tick this layer, and name `docs/12-cache.md` next.

## Edge cases

- No session: `Nothing to export yet`. No file. `/new` then `/export` does
  this too.
- A session with no blocks: only the two header lines. Harmless.
- Two sessions with the same title: the same default filename, so the second
  export overwrites the first.
- Export during the first seconds, before the title thread lands: the filename
  is `New session.txt`. A later export after the title lands writes a new file
  named from the title; the fallback file stays.
- A fallback title's own ` - YYYY-MM-DD HH:MM` suffix stays in the header.
  Only the filename strips it.
- Rename after export: the next `/export` writes a new file named from the new
  title. The old file stays.
- `/export` with a trailing space: `raw.strip()` is empty, so it takes the
  default.
- `/export my notes.txt`: the whole remainder is the path, spaces included.
- Relative path: resolved under `SANDBOX`, same as a tool path.
- Absolute path inside: written there.
- Absolute path outside: asks. Deny prints `Permission denied:
  external_directory <posix>` and writes nothing.
- A path that is a directory: `Export Error:` from `OSError`.
- `.env`, `.env.local`: refused. `.env.example` is not dotenv to `classify`,
  so it would write; do not special-case it.
- Plan mode: works. Export is not `write` or `edit`, so `PLAN_DENIED` and the
  schema list do not apply, and the model never sees it.
- `/export` is not sent to the model and adds no tokens.
- `~` is not expanded. `~/x.txt` becomes `<SANDBOX>/~/x.txt`.

## Verification

- One turn, then `/export`. Check the default name, both header lines, the
  prompt, the answer, and the tool line.
- Search the file for a string that came from a shell command or a `read`
  body. It must be absent.
- `/export out.txt` and `/export ..\out.txt`. The second asks; `deny` writes
  nothing; `always` then a second export does not ask.
- `/export .env` prints `Export Error:` and writes nothing.
- `/export` before the first message prints `Nothing to export yet`.
- Export twice. One file, second content wins.
- Two sessions with the same prompt. The same default filename; the later
  export overwrites it.
- Rename, then export. A second file appears; the old one stays.
- `/help` lists `/export`.
- `/build`, change a file, `/export`. The tool line appears; the diff and the
  shell block do not.
- `uv run python -m compileall src`, `git diff --check`.

## Next

`docs/12-cache.md`: display cache-read and cache-write tokens when `usage`
reports them. No custom cache code, no model flag, until a second provider
needs it.
