# 10 — Sessions

Do first: `docs/09-streaming.md`. Layer 8 is committed. This layer adds
persistent sessions, live resume, rename, delete, `/new`, and one background
LLM title call. It does not add export, reasoning storage, compaction, a
database, or a second model client.

Registry, loop, `SYSTEM`, `TITLE_SYSTEM`, and the one
`client.chat.completions.create` call live in `agent.py`. The REPL, slash
commands, title thread, and status print live in `__main__.py`. Tool code
stays in `tools/`. Do not split a new package.

## What it is

One JSON file per session. `/sessions` lists the saved files for the current
workspace, newest first. `/sessions N` resumes one. `/new` starts a clean
session and resets the model to `default_id`, mode to `plan`, thinking to
`off`, effort to `low`, and args/output to `off`. The `Session` counter is
conversation lifetime, not process lifetime.

Sessions are written only when there is something to save. Startup shows no
session and creates no file. The first user message creates the id, fallback
title, and first file. Exit saves the current session.

```
~/.local/share/minicode/sessions/<project-key>/<session-id>.json
```

On Windows that is `%USERPROFILE%\.local\share\minicode\sessions`. On Unix,
honor `XDG_DATA_HOME`. The project key is the sanitized workspace directory
name plus a short SHA-1 of the resolved workspace path. On Windows the name
and hash input are case-folded. A different workspace gets a different list.
`SYSTEM` names this root from `sessions.data_root()`; individual session files
are not offered as tool paths.

Do not put sessions in the project, `.env`, or the sandbox. Do not add a
database. Do not commit session files.

## File shape

Version `1`. `created` and `updated` are local `DD-MM-YYYY HH:MM` strings.
Legacy ISO strings are rewritten to that shape on load. `messages` excludes
the system prompt; the current `SYSTEM` is rebuilt on resume. The raw
assistant dicts, including `extra_content`, stay as they were written by
`agent.py`.

```json
{
  "version": 1,
  "id": "20261029-142501-a1b2",
  "title": "Fix login redirect",
  "created": "29-10-2026 14:25",
  "updated": "29-10-2026 14:27",
  "cwd": "/home/me/project",
  "sandbox": "/home/me/project",
  "model": "gemini-3-flash",
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

`usage.completion_tokens` is the `Session` value at the last save. Restore
it; do not add prompt tokens. `last_turn` holds the last finished turn's `In`,
`Out`, and wall-clock `Elapsed` so a resume prints the same last status line.
A file without `last_turn` loads with zeros. A session with history or tokens
and no `Elapsed` uses `0.0`, so the usage line still prints. `/new` and
deleting the active session reset both. `always` is a sorted list of exact
`[key, value]` pairs already normalized by `permissions.py`. Resume restores
it. `/new` and deleting the active session clear it.

A corrupt, unreadable, unsupported, or mismatched file is skipped by the
list and reported as `Session Error: ...`; a direct load raises. Writes are
atomic: write a sibling `.tmp`, then `os.replace`.

Session id is local `YYYYMMDD-HHMMSS-4hex`. The 4 hex comes from
`secrets.token_hex(2)`. Retry on collision. File name is `<id>.json`.

## Commands

```
/sessions
/sessions N
/sessions N delete
/sessions N del
/sessions N rename
/sessions N ren
/sessions N rename New name
/sessions N ren New name
/new
```

`N` is the list number or the full session id. Actions are case-insensitive;
names preserve case. There is no `/resume`, `/rename`, or `/delete`, and no
CLI resume flag.

List rows:

```
1 Fix login redirect - 29-10-2026 14:25 (active)
2 New session - 29-10-2026 12:04
```

Newest id first. The id embeds the local creation time, so id order is newest
first. Resume and rename do not reorder. A delete shifts later numbers down.
A fallback title's ` - YYYY-MM-DD HH:MM` suffix is hidden in the row; the row
then shows `New session - DD-MM-YYYY HH:MM`. Empty list prints
`(no saved sessions)`.

Errors:

```
Unknown Session: 9
Unknown Session action: foo
Session Error: <detail>
```

Delete asks `Delete session "title"? [Y/N]`. Only `y` or `yes` confirms.
Rename without a name asks `New name: `. Blank, EOF, Ctrl+C, or a non-yes
delete answer prints `Cancelled` and does nothing.

Rename cleanup: replace Unicode control characters with spaces, collapse
whitespace, strip, reject empty, cap at 200 characters. Duplicate names are
allowed. A rename is permanent; an active rename sets `title_locked` so a
pending title thread cannot overwrite it.

Active delete: confirm, unlink, then `/new` semantics. Model, mode, thinking,
effort, args, and output reset to startup defaults; `always` clears;
`Session` resets; history returns to the system message only; and no file
exists until the next user message.

Non-active delete: current session is saved first, target file is removed,
current session is unchanged.

Active rename: lock title, update memory, update `updated`, save now.
Non-active rename: save current, load target, change title and `updated`,
write target, do not switch.

## Title

The title is an LLM summary of the first user prompt, not its first line.
Use the model active when the first message is sent. Launch one daemon
thread after the first message is saved. It runs alongside the agent turn.

- Prompt: extract a concise 2-5 word title, capitalize major words, and keep
  minor words such as `in`, `of`, `the`, and `and` lowercase. At most 60
  characters. Output only the title.
- Input cap: first 2000 characters.
- `max_tokens`: 64. `stream`: false. `timeout`: 30 seconds.
- One SDK retry (`max_retries=1`). No tools and no reasoning display.
- Thought tags (`<thought>`, `</thought>`, `<think>`, `</think>`) are removed
  before the title is used.
- Fallback at creation: `New session - YYYY-MM-DD HH:MM` in local time.
- The worker only calls the model, cleans the answer, and assigns
  `session["title"]` under `_TITLE_LOCK`.
- It does no file I/O, no printing, no message append, and no usage update.
- The main thread saves. Join the worker for at most 2 seconds on exit,
  then save.
- Tokens used by the title call never enter `In`, `Out`, or `Session`.
- Rename wins. Resume/new/delete makes the old worker stale; it must not
  write into the new session.
- No title text enters model history.

## Skeleton

**Keep** the loop shape, streaming, raw assistant dict append, `MAX_STEPS`,
`SYSTEM`, `PLAN_SYSTEM`, mode swap, tool dispatch, status shape, and the no
Tok/s rule.

**Add** `src/minicode/sessions.py`:

```python
import hashlib
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from secrets import token_hex

from minicode.permissions import snapshot_always
from minicode.resolve_path import SANDBOX

_VERSION = 1
_ID_RE = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{4}$")


class SessionError(Exception):
    pass


def _now() -> str:
    return datetime.now().astimezone().strftime("%d-%m-%Y %H:%M")


def data_root() -> Path:
    if sys.platform == "win32":
        base = Path.home() / ".local" / "share"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "minicode" / "sessions"


def _project_key(sandbox: Path) -> str:
    raw = str(sandbox.resolve())
    folded = raw.casefold() if sys.platform == "win32" else raw
    digest = hashlib.sha1(folded.encode("utf-8")).hexdigest()[:8]
    label = sandbox.name.casefold() if sys.platform == "win32" else sandbox.name
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", label).strip("._-") or "workspace"
    return f"{name[:40]}-{digest}"


def _project_dir() -> Path:
    return data_root() / _project_key(SANDBOX)


def _session_path(session_id: str) -> Path:
    return _project_dir() / f"{session_id}.json"


def new_id() -> str:
    while True:
        candidate = f"{datetime.now():%Y%m%d-%H%M%S}-{token_hex(2)}"
        if not _session_path(candidate).exists():
            return candidate


def fallback_title(when: str | None = None) -> str:
    try:
        moment = datetime.fromisoformat(when) if when else datetime.now(timezone.utc)
    except (TypeError, ValueError):
        moment = datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return f"New session - {moment.astimezone():%Y-%m-%d %H:%M}"


def _check(data, path: Path) -> dict:
    if not isinstance(data, dict):
        raise SessionError(f"{path.name}: invalid session")
    if data.get("version") != _VERSION:
        raise SessionError(f"{path.name}: unsupported session")
    session_id = data.get("id")
    if not isinstance(session_id, str) or session_id != path.stem or not _ID_RE.fullmatch(session_id):
        raise SessionError(f"{path.name}: invalid session id")
    if not isinstance(data.get("messages"), list):
        raise SessionError(f"{path.name}: invalid messages")
    if not isinstance(data.get("title"), str) or not data["title"].strip():
        data["title"] = fallback_title(data.get("created"))
    created_val = data.get("created")
    if not isinstance(created_val, str):
        data["created"] = _now()
    elif "T" in created_val or "+" in created_val or "Z" in created_val:
        try:
            dt = datetime.fromisoformat(created_val)
            data["created"] = dt.astimezone().strftime("%d-%m-%Y %H:%M")
        except (ValueError, TypeError):
            pass
    updated_val = data.get("updated")
    if not isinstance(updated_val, str):
        data["updated"] = data["created"]
    elif "T" in updated_val or "+" in updated_val or "Z" in updated_val:
        try:
            dt = datetime.fromisoformat(updated_val)
            data["updated"] = dt.astimezone().strftime("%d-%m-%Y %H:%M")
        except (ValueError, TypeError):
            pass
    if not isinstance(data.get("usage"), dict):
        data["usage"] = {"completion_tokens": 0}
    turn = data.get("last_turn")
    if not isinstance(turn, dict):
        turn = {}
    prompt = turn.get("prompt_tokens")
    completion = turn.get("completion_tokens")
    elapsed = turn.get("Elapsed") if turn.get("Elapsed") is not None else turn.get("elapsed")
    data["last_turn"] = {
        "prompt_tokens": max(0, int(prompt)) if isinstance(prompt, int) else 0,
        "completion_tokens": max(0, int(completion)) if isinstance(completion, int) else 0,
        "Elapsed": float(elapsed) if isinstance(elapsed, (int, float)) else None,
    }
    if not isinstance(data.get("always"), list):
        data["always"] = []
    return data


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SessionError(f"{path.name}: {exc}") from exc
    return _check(data, path)


def load(session_id: str) -> dict:
    if not isinstance(session_id, str) or not _ID_RE.fullmatch(session_id):
        raise SessionError("not found")
    path = _session_path(session_id)
    if not path.is_file():
        raise SessionError("not found")
    return _read(path)


def _write(data: dict) -> None:
    path = _session_path(data["id"])
    temp = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with temp.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp, path)
    except (OSError, TypeError, ValueError) as exc:
        try:
            temp.unlink()
        except OSError:
            pass
        raise SessionError(f"could not save {path.name}: {exc}") from exc


def new_session(settings: dict) -> dict:
    moment = _now()
    return {
        "version": _VERSION,
        "id": new_id(),
        "title": fallback_title(moment),
        "created": moment,
        "updated": moment,
        "cwd": str(Path.cwd().resolve()),
        "sandbox": str(SANDBOX),
        **settings,
        "usage": {"completion_tokens": 0},
        "last_turn": {"prompt_tokens": 0, "completion_tokens": 0, "Elapsed": None},
        "always": [],
        "messages": [],
    }


def _snapshot(
    session: dict,
    messages: list[dict],
    settings: dict,
    completion_tokens: int,
    last_turn: dict,
) -> dict:
    session.update(settings)
    session["usage"] = {"completion_tokens": max(0, int(completion_tokens))}
    session["last_turn"] = {
        "prompt_tokens": max(0, int(last_turn.get("prompt_tokens") or 0)),
        "completion_tokens": max(0, int(last_turn.get("completion_tokens") or 0)),
        "Elapsed": last_turn.get("Elapsed") if last_turn.get("Elapsed") is not None else last_turn.get("elapsed"),
    }
    session["always"] = snapshot_always()
    session["messages"] = [
        message for message in messages
        if isinstance(message, dict) and message.get("role") != "system"
    ]
    session["updated"] = _now()
    return session


def save(
    session: dict,
    messages: list[dict],
    settings: dict,
    completion_tokens: int,
    last_turn: dict,
) -> None:
    _write(_snapshot(session, messages, settings, completion_tokens, last_turn))


def clean_name(raw: str) -> str:
    if not isinstance(raw, str):
        return ""
    text = "".join(
        " " if unicodedata.category(char).startswith("C") else char
        for char in raw
    )
    return " ".join(text.split())[:200]


def rename(session_id: str, raw: str) -> str:
    name = clean_name(raw)
    if not name:
        raise SessionError("name is empty")
    data = load(session_id)
    data["title"] = name
    data["updated"] = _now()
    _write(data)
    return name


def delete(session_id: str) -> None:
    if not isinstance(session_id, str) or not _ID_RE.fullmatch(session_id):
        raise SessionError("not found")
    path = _session_path(session_id)
    try:
        path.unlink()
    except FileNotFoundError as exc:
        raise SessionError("not found") from exc
    except OSError as exc:
        raise SessionError(f"could not delete {path.name}: {exc}") from exc


def list_sessions() -> tuple[list[dict], list[str]]:
    folder = _project_dir()
    try:
        paths = sorted(folder.glob("*.json"))
    except OSError as exc:
        return [], [str(exc)]
    found: list[dict] = []
    errors: list[str] = []
    for path in paths:
        try:
            found.append(_read(path))
        except SessionError as exc:
            errors.append(str(exc))
    found.sort(
        key=lambda item: item.get("id", ""),
        reverse=True,
    )
    return found, errors
```

**Add** to `src/minicode/permissions.py`:

```python
def snapshot_always() -> list[list[str]]:
    return [list(item) for item in sorted(ALWAYS)]


def restore_always(items) -> None:
    ALWAYS.clear()
    if not isinstance(items, list):
        return
    for item in items:
        if (
            isinstance(item, (list, tuple))
            and len(item) == 2
            and isinstance(item[0], str)
            and isinstance(item[1], str)
        ):
            ALWAYS.add((item[0], item[1]))
```

Update `always` docs: it lives for the session, not only the process.

**Add** to `src/minicode/agent.py`:

```python
TITLE_SYSTEM = (
    "Extract a concise 2 to 5 word title from the user prompt. "
    "Capitalize major words and keep minor words like 'in', 'of', 'the', 'and' in lowercase "
    "(example: 'The Evolution of Artificial Intelligence'). "
    "Output only the title."
)


def _create(client, **kwargs):
    return client.chat.completions.create(**kwargs)


def _client_for(record: dict, max_retries: int | None = None) -> OpenAI:
    api_key = os.getenv(record["api_key"])
    base = record["api_base"]
    if not api_key and base.startswith(("http://127.0.0.1", "http://localhost")):
        api_key = "ollama"
    options = {"api_key": api_key, "base_url": base}
    if max_retries is not None:
        options["max_retries"] = max_retries
    return OpenAI(**options)


def _clean_title(text: str) -> str | None:
    if not isinstance(text, str):
        return None
    for tag in ("<thought>", "</thought>", "<think>", "</think>"):
        text = text.replace(tag, "")
    text = text.strip("\"'`*#: \n")
    if text.lower().startswith("title:"):
        text = text[6:].strip()
    return text[:60].strip() or None


def session_title(first_prompt: str, model_id: str) -> str | None:
    record = MODELS.get(model_id)
    if record is None:
        return None
    try:
        client = _client_for(record, max_retries=1)
        response = _create(
            client,
            model=record["id"],
            messages=[
                {"role": "system", "content": TITLE_SYSTEM},
                {"role": "user", "content": first_prompt[:2000]},
            ],
            max_tokens=64,
            stream=False,
            timeout=30.0,
        )
        return _clean_title(response.choices[0].message.content)
    except Exception:
        return None
```

**Replace** the client setup in `agent()`:

```python
    record = MODELS[active["id"]]
    base = record["api_base"]
    try:
        client = _client_for(record)
    except Exception as exc:
        return f"Model Error: {exc}"
```

**Replace** the create call in `agent()`:

```python
            stream = _create(client, **create)
```

There is still exactly one `client.chat.completions.create` call site:
inside `_create`.

**Add** to `src/minicode/__main__.py`:

```python
_TITLE_LOCK = Lock()
_title_thread: Thread | None = None
_title_locked = False
_STATE = {"session": None, "messages": []}


def _system() -> dict:
    content = SYSTEM + " " + PLAN_SYSTEM if mode["name"] == "plan" else SYSTEM
    return {"role": "system", "content": content}


def _settings() -> dict:
    return {
        "model": active["id"],
        "mode": mode["name"],
        "thinking": thinking["name"],
        "effort": effort["name"],
        "args": args_display["name"],
        "output": shell_output["name"],
    }


def _save() -> bool:
    session = _STATE["session"]
    if session is None:
        return True
    try:
        sessions.save(
            session,
            _STATE["messages"],
            _settings(),
            session_usage["completion_tokens"],
            {
                "prompt_tokens": last_usage["prompt_tokens"],
                "completion_tokens": last_usage["completion_tokens"],
                "Elapsed": last_turn["Elapsed"],
            },
        )
    except sessions.SessionError as exc:
        print(f"\nSession Error: {exc}\n")
        return False
    return True


def _reset_current() -> None:
    global _title_locked, _title_thread
    _STATE["session"] = None
    if default_id in MODELS:
        active["id"] = default_id
    elif MODELS:
        active["id"] = next(iter(MODELS))
    mode["name"] = "plan"
    thinking["name"] = "off"
    effort["name"] = "low"
    args_display["name"] = "off"
    shell_output["name"] = "off"
    _STATE["messages"] = [_system()]
    session_usage["completion_tokens"] = 0
    last_usage["prompt_tokens"] = 0
    last_usage["completion_tokens"] = 0
    last_turn["Elapsed"] = None
    restore_always([])
    with _TITLE_LOCK:
        _title_locked = False
        _title_thread = None


def _join_title() -> None:
    with _TITLE_LOCK:
        thread = _title_thread
    if thread is not None:
        thread.join(2.0)


def _start_title(target: dict, prompt: str, model_id: str) -> None:
    global _title_thread, _title_locked

    def work() -> None:
        title = session_title(prompt, model_id)
        if not title:
            return
        with _TITLE_LOCK:
            if _title_locked or _STATE["session"] is not target:
                return
            target["title"] = title

    with _TITLE_LOCK:
        _title_locked = False
        thread = Thread(target=work, daemon=True)
        _title_thread = thread
    thread.start()


def _stamp(value: str) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%d-%m-%Y %H:%M")
    except (TypeError, ValueError):
        return str(value)


def _target(items: list[dict], token: str) -> dict | None:
    if token.isdigit():
        number = int(token)
        if 1 <= number <= len(items):
            return items[number - 1]
        return None
    for item in items:
        if item.get("id") == token:
            return item
    return None


def _show_sessions(show: bool = True) -> list[dict]:
    _save()
    items, errors = sessions.list_sessions()
    for error in errors:
        print(f"\nSession Error: {error}\n")
    if not show:
        return items
    if not items:
        print("\n(no saved sessions)\n")
        return []
    current = _STATE["session"]
    print()
    for number, item in enumerate(items, 1):
        mark = " (active)" if current is not None and item.get("id") == current.get("id") else ""
        title = item.get("title", "New Session").split(" - 20")[0].strip()
        stamp = _stamp(item.get("created", ""))
        print(f"{number} {title} - {stamp}{mark}")
    print()
    return items


def _apply_session(data: dict) -> None:
    global _title_locked, _title_thread
    stored_model = data.get("model")
    if stored_model in MODELS:
        active["id"] = stored_model
    if data.get("mode") in ("plan", "build"):
        mode["name"] = data["mode"]
    if data.get("thinking") in ("off", "on"):
        thinking["name"] = data["thinking"]
    if data.get("effort") in ("low", "medium", "high"):
        effort["name"] = data["effort"]
    if data.get("args") in ("off", "on"):
        args_display["name"] = data["args"]
    if data.get("output") in ("off", "on"):
        shell_output["name"] = data["output"]
    history = [
        item for item in data.get("messages", [])
        if isinstance(item, dict) and item.get("role") != "system"
    ]
    _STATE["messages"] = [_system()] + history
    _STATE["session"] = data
    usage = data.get("usage")
    tokens = usage.get("completion_tokens") if isinstance(usage, dict) else 0
    session_usage["completion_tokens"] = max(0, int(tokens)) if isinstance(tokens, int) else 0
    turn = data.get("last_turn") if isinstance(data.get("last_turn"), dict) else {}
    last_usage["prompt_tokens"] = max(0, int(turn.get("prompt_tokens") or 0))
    last_usage["completion_tokens"] = max(0, int(turn.get("completion_tokens") or 0))
    seconds = turn.get("Elapsed") if turn.get("Elapsed") is not None else turn.get("elapsed")
    if seconds is None and (history or session_usage["completion_tokens"] or last_usage["prompt_tokens"]):
        seconds = 0.0
    last_turn["Elapsed"] = float(seconds) if isinstance(seconds, (int, float)) else None
    restore_always(data.get("always", []))
    with _TITLE_LOCK:
        _title_locked = False
        _title_thread = None


_NOTE_PREFIXES = ("Plan mode:", "Permission denied:", "Unknown tool:", "Tool error:", "Model Error:")


def _replay() -> None:
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
                blocks.append(_tool_line(function.get("name", "?"), function.get("arguments", "")))
    if blocks:
        print("\n\n".join(blocks))
```

`docs/11-export.md` splits this block builder into `_transcript()` so `/export`
and replay share it. That split is the current code.

```python
def _resume(target: dict) -> None:
    try:
        data = sessions.load(target["id"])
    except sessions.SessionError as exc:
        print(f"\nSession Error: {exc}\n")
        return
    _apply_session(data)
    print(f"\nResumed: {data.get('title', 'Untitled')}\n")
    _replay()
    _status()


def _rename(target: dict, raw: str) -> None:
    global _title_locked
    name = sessions.clean_name(raw)
    if not name:
        print("\nSession Error: name is empty\n")
        return
    current = _STATE["session"]
    if current is not None and target.get("id") == current.get("id"):
        with _TITLE_LOCK:
            _title_locked = True
        current["title"] = name
        if not _save():
            return
        print(f"\nRenamed: {name}\n")
        return
    try:
        name = sessions.rename(target["id"], name)
    except sessions.SessionError as exc:
        print(f"\nSession Error: {exc}\n")
        return
    print(f"\nRenamed: {name}\n")


def _delete(target: dict) -> None:
    current = _STATE["session"]
    active = current is not None and target.get("id") == current.get("id")
    title = target.get("title", "Untitled")
    try:
        answer = input(f'Delete session "{title}"? [Y/N] ').strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled\n")
        return
    if answer not in ("y", "yes"):
        print("\nCancelled\n")
        return
    try:
        sessions.delete(target["id"])
    except sessions.SessionError as exc:
        print(f"\nSession Error: {exc}\n")
        return
    if active:
        _reset_current()
    print(f"\nDeleted: {title}\n")


def _new() -> None:
    if not _save():
        return
    _reset_current()
    print("\nNew session")
    _status()
```

**Replace** the status fence with one helper that serves startup, `/new`, a
turn, and a resume:

```python
def _usage() -> str | None:
    if last_turn["Elapsed"] is None:
        return None
    window = MODELS.get(active["id"], {}).get("context_window")
    ctx = f" | {last_usage['prompt_tokens'] / window:.1%} context" if window else ""
    return (
        f"{last_usage['prompt_tokens']:,} In | {last_usage['completion_tokens']:,} Out | "
        f"{session_usage['completion_tokens']:,} Session | Elapsed: {_elapsed(last_turn['Elapsed'])}{ctx}"
    )


def _status() -> None:
    body = (
        f"\n---\n"
        f"Model: {active['id']} | Mode: {mode['name']} | Tools Loaded: {', '.join(active_names())}\n"
        f"Sandbox: {SANDBOX} | Thinking: {thinking['name']} | Effort: {effort['name']} "
        f"| Args: {args_display['name']} | Output: {shell_output['name']}"
    )
    usage = _usage()
    if usage is not None:
        body += f"\n{usage}"
    print(f"{body}\n---")
```

Declare `last_turn = {"Elapsed": None}` next to `_TITLE_LOCK`. No usage line
at startup or after `/new`; a turn and a resume include it. Import
`_tool_line` from `minicode.agent` for the replay.

**Add** at the end of each turn, replacing the inline `ctx` and fence:

```python
        last_turn["Elapsed"] = elapsed
        _status()
        _save()
```

Add imports:

```python
from datetime import datetime
from threading import Lock, Thread

from minicode import sessions
from minicode.permissions import ask as permission_ask, restore_always
```

`default_id` is imported from `minicode.agent` alongside the existing names.

**Replace** the startup message list:

```python
    _STATE["messages"] = [_system()]
```

**Replace** `/plan` and `/build` message assignment with:

```python
            _STATE["messages"][0] = _system()
```

**Add** `/new` and `/sessions` handling before the model call:

```python
        if stripped == "/new":
            _new()
            continue
        if stripped == "/sessions" or stripped.startswith("/sessions "):
            parts = stripped.split(maxsplit=3)
            items = _show_sessions(show=len(parts) == 1)
            if len(parts) == 1:
                continue
            token = parts[1]
            target = _target(items, token)
            if target is None:
                print(f"\nUnknown Session: {token}\n")
                continue
            if len(parts) == 2:
                _resume(target)
                continue
            action = parts[2].lower()
            if action in ("delete", "del"):
                if len(parts) > 3:
                    print(f"\nUnknown Session action: {parts[2]} {parts[3]}\n")
                    continue
                _delete(target)
                continue
            if action in ("rename", "ren"):
                if len(parts) == 4:
                    name = parts[3]
                else:
                    try:
                        name = input("New name: ")
                    except (EOFError, KeyboardInterrupt):
                        print("\nCancelled\n")
                        continue
                if not sessions.clean_name(name):
                    print("\nCancelled\n")
                    continue
                _rename(target, name)
                continue
            print(f"\nUnknown Session action: {parts[2]}\n")
            continue
```

**Add** `("/new", ...)` and `("/sessions", ...)` rows to `COMMANDS`.

**Add** the unknown-command guard after the `/models` handler and before the
user append:

```python
        if stripped.startswith("/"):
            print(f"\nUnknown command: {stripped.split(maxsplit=1)[0]}. Use /help.\n")
            continue
```

**Replace** the user append with:

```python
        fresh = _STATE["session"] is None
        if fresh:
            _STATE["session"] = sessions.new_session(_settings())
            _STATE["messages"] = [_system()]
        _STATE["messages"].append({"role": "user", "content": text})
        if fresh:
            _save()
            _start_title(_STATE["session"], text, active["id"])
```

**Replace** the `agent(messages, on_event)` argument with
`_STATE["messages"]`, set `last_turn["Elapsed"] = elapsed` before `_status()`,
and keep `_save()` after it.

**Add** after the REPL loop, before `main()` returns:

```python
    _join_title()
    _save()
```

Call `_save()` after a successful `/plan`, `/build`, `/thinking`, `/effort`,
`/args`, `/output`, or `/models` change. A command before the first user
message has no session, so `_save()` is a no-op.

## Edge cases

- A path outside the workspace still asks. `SYSTEM` names the sessions root;
  no individual session file is offered as a tool path.
- `list_sessions()` catches bad files; a bad target prints
  `Session Error: ...`.
- `always` pairs are exact. `git status` still does not cover
  `git status --short` after resume.
- The session's `model` is restored only if that id is still loaded.
  Otherwise keep the current model.
- History from disk may include an interrupted assistant marker or a tool
  error string. Restore it as plain dicts.
- No system prompt from disk. Rebuild from current `SYSTEM` / `PLAN_SYSTEM`.
- A title call failure is silent. The fallback stays after the one SDK retry.
- A title call never changes `last_usage` or `session_usage`.
- A corrupt session is not repaired in place by the list.
- `exit`, `quit`, and `bye` join the title worker briefly, save, then leave.
- No file at startup. No file after `/new` until the next message.
- An older file without `last_turn` loads with zeros. If it has history or
  tokens, `Elapsed` becomes `0.0` so the resume block still prints a usage
  line. A truly empty file has no last line until its next turn.
- A legacy ISO `created` / `updated` is rewritten to local
  `DD-MM-YYYY HH:MM` on load.
- Replay skips every `role: "tool"` body, so file contents and command output
  never reappear. A call whose result is a plan denial, a permission denial,
  an unknown tool, a tool error, or a model error prints no tool line.
- Replay uses the restored `/args` value: `off` prints the name only, `on`
  prints the one-liner or the left rail.
- A replay block ends before `_status()` so the fence adds the only blank
  line before it.
- An empty session prints the title and the block with nothing between.
- A prompt that begins with `/` and matches no handler prints
  `Unknown command: {first word}. Use /help.` and is not appended. `/plan`,
  `/build`, `/new`, and `/help` with an argument land there too.
- A lone POSIX path such as `/d/project` is rejected as a command. Wrap it in
  a sentence or use the drive form.

## Verification

- `uv run python -m compileall src`
- `git diff --check`
- Start in a temp workspace. Send one message. Check
  `~/.local/share/minicode/sessions/<project-key>/<id>.json` exists and has
  no system message, no reasoning field, and a local fallback title until
  the summary lands.
- `/sessions` shows newest first and marks the active row.
- `/sessions 1` restores messages, model, mode, thinking, effort, args,
  output, `always`, `Session`, and the last `In`, `Out`, and `Elapsed`, then
  replays the transcript and prints the same last line as before.
- `/new` prints the block with no last line, resets `Session` to 0, and resets
  the model, mode, thinking, effort, args, and output to their defaults.
- `/export` writes the transcript and does not call the model.
- Rename with spaces, rename with no name, blank name, 201 chars, control
  characters, duplicate name, full-id target.
- Delete active and non-active. Check cancel, `n`, EOF, and Ctrl+C.
- Clear `always` on `/new` and active delete; preserve it on resume.
- Check that a resumed session starts a new turn with the current system
  prompt and that no system message is duplicated.
- Check that `/new` resets settings and `Session` to their defaults.
- Corrupt one JSON file. The list skips it and prints `Session Error`;
  `sessions.load(id)` raises the same error on direct load.
- Run with `--sandbox sandbox`; confirm the list is separate from the
  workspace-root list.
- Exit immediately after the first answer. The fallback or summary is saved
  within the 2-second join.
- Confirm no title text appears in history and no title tokens appear in
  `In`, `Out`, or `Session`.

## Next

`docs/12-cache.md`: display cache-read and cache-write tokens when `usage`
reports them. Export is implemented in `docs/11-export.md`. No reasoning
capture in the session file. Cost display, compaction, and `AGENTS.md`
injection remain deferred.
