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
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _data_root() -> Path:
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
    return _data_root() / _project_key(SANDBOX)


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
    if not isinstance(data.get("created"), str):
        data["created"] = _now()
    if not isinstance(data.get("updated"), str):
        data["updated"] = data["created"]
    if not isinstance(data.get("usage"), dict):
        data["usage"] = {"completion_tokens": 0}
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
        "always": [],
        "messages": [],
    }


def _snapshot(session: dict, messages: list[dict], settings: dict, completion_tokens: int) -> dict:
    session.update(settings)
    session["usage"] = {"completion_tokens": max(0, int(completion_tokens))}
    session["always"] = snapshot_always()
    session["messages"] = [
        message for message in messages
        if isinstance(message, dict) and message.get("role") != "system"
    ]
    session["updated"] = _now()
    return session


def save(session: dict, messages: list[dict], settings: dict, completion_tokens: int) -> None:
    _write(_snapshot(session, messages, settings, completion_tokens))


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
        key=lambda item: (item.get("created", ""), item.get("id", "")),
        reverse=True,
    )
    return found, errors
