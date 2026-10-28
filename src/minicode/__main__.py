import time
from datetime import datetime
from threading import Lock, Thread

from minicode import sessions
from minicode.resolve_path import SANDBOX
from minicode.agent import agent, TOOLS, last_usage, session_usage, SYSTEM, active, MODELS, mode, effort, args_display, active_names, PLAN_SYSTEM, session_title
from minicode.permissions import ask as permission_ask, restore_always
from minicode.tools.shell import output as shell_output

COMMANDS = (
    ("/plan", "Switch to plan mode. write and edit are disabled.", "/plan"),
    ("/build", "Switch to build mode. All tools are available.", "/build"),
    ("/models", "List loaded models. A number or an id switches for this session.", "/models\n/models 2"),
    ("/new", "Start a new session. Current settings are kept.", "/new"),
    ("/sessions", "List saved sessions. A number resumes. delete and rename are actions.", "/sessions\n/sessions 2\n/sessions 2 rename Fix login\n/sessions 2 delete"),
    ("/thinking", "Show or hide reasoning. 1 off, 2 on. Default off.", "/thinking 2"),
    ("/effort", "Set effort. 1 low, 2 medium, 3 high. Default low.", "/effort 2"),
    ("/args", "Show or hide tool arguments. 1 off, 2 on. Default off.", "/args on"),
    ("/output", "Show or hide the shell output block. 1 off, 2 on. Default off. The model still gets the output.", "/output on"),
    ("/help", "List commands.", "/help"),
    ("exit", "Leave. quit and bye do the same.", "exit"),
)

def _listed(label: str, choices: tuple[str, ...], current: dict, raw: str) -> None:
    parts = raw.split(maxsplit=1)
    if len(parts) == 1:
        print()
        for n, name in enumerate(choices, 1):
            mark = " (active)" if name == current["name"] else ""
            print(f"{n} {name}{mark}")
        print()
        return
    chosen = parts[1].strip()
    if chosen.isdigit():
        n = int(chosen)
        picked = choices[n - 1] if 1 <= n <= len(choices) else None
        if picked is None:
            print(f"\nUnknown {label}: {chosen}\n")
            return
        chosen = picked
    else:
        chosen = chosen.lower()
    if chosen not in choices:
        print(f"\nUnknown {label}: {parts[1].strip()}\n")
        return
    current["name"] = chosen
    print(f"\n{label}: {current['name']}\n")

def _permission(key:str, value:str) -> str:
    print(f"\nPermission: {key} | {value}")
    try:
        answer = input("[o]nce / [a]lways / [d]eny: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return "deny"
    if answer in ("o", "once"):
        return "once"
    if answer in ("a", "always"):
        return "always"
    return "deny"

permission_ask["fn"] = _permission
thinking = {"name": "off"}

def _elapsed(seconds: float) -> str:
    if seconds < 60:
        shown = f"{seconds:.1f}"
        if shown == "60.0":
            return "1m"
        return f"{shown}s"
    left = int(seconds + 0.5)
    parts: list[str] = []
    for name, size in (
        ("y", 365 * 24 * 3600),
        ("w", 7 * 24 * 3600),
        ("d", 24 * 3600),
        ("h", 3600),
        ("m", 60),
        ("s", 1),
    ):
        count, left = divmod(left, size)
        if count:
            parts.append(f"{count}{name}")
        if len(parts) == 2:
            break
    return " ".join(parts)

def _status(usage: str | None = None) -> None:
    body = (
        f"\n---\n"
        f"Model: {active['id']} | Mode: {mode['name']} | Tools Loaded: {', '.join(active_names())}\n"
        f"Sandbox: {SANDBOX} | Thinking: {thinking['name']} | Effort: {effort['name']} "
        f"| Args: {args_display['name']} | Output: {shell_output['name']}"
    )
    if usage is not None:
        body += f"\n{usage}"
    print(f"{body}\n---")

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
        )
    except sessions.SessionError as exc:
        print(f"\nSession Error: {exc}\n")
        return False
    return True

def _reset_current() -> None:
    global _title_locked, _title_thread
    _STATE["session"] = None
    _STATE["messages"] = [_system()]
    session_usage["completion_tokens"] = 0
    last_usage["prompt_tokens"] = 0
    last_usage["completion_tokens"] = 0
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
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return str(value)[:16].replace("T", " ")

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
        print(f"{number} {item.get('title', 'Untitled')} - {_stamp(item.get('created', ''))}{mark}")
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
    last_usage["prompt_tokens"] = 0
    last_usage["completion_tokens"] = 0
    restore_always(data.get("always", []))
    with _TITLE_LOCK:
        _title_locked = False
        _title_thread = None

def _resume(target: dict) -> None:
    try:
        data = sessions.load(target["id"])
    except sessions.SessionError as exc:
        print(f"\nSession Error: {exc}\n")
        return
    _apply_session(data)
    print(f"\nResumed: {data.get('title', 'Untitled')}\n")
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
        answer = input(f'Delete session "{title}"? [y/N] ').strip().lower()
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
    print("\nNew session\n")

def main() -> None:
    print(f"\nType /help for available commands")
    _status()
    _STATE["messages"] = [_system()]
    while True:
        try:
            text = input(">>> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if text.strip().lower() in ("exit", "quit", "bye"):
            break
        if not text.strip():
            continue

        stripped = text.strip()
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
        if stripped == "/plan" or stripped == "/build":
            want = stripped[1:]
            mode["name"] = want
            _STATE["messages"][0] = _system()
            print(f"\nMode: {mode['name']} | Tools Loaded: {', '.join(active_names())}\n")
            _save()
            continue
        if stripped == "/thinking" or stripped.startswith("/thinking "):
            choices = ("off", "on")
            parts = stripped.split(maxsplit=1)
            if len(parts) == 1:
                print()
                for n, name in enumerate(choices, 1):
                    mark = " (active)" if name == thinking["name"] else ""
                    print(f"{n} {name}{mark}")
                print()
            else:
                chosen = parts[1].strip()
                if chosen.isdigit():
                    n = int(chosen)
                    picked = choices[n - 1] if 1 <= n <= len(choices) else None
                    if picked is None:
                        print(f"\nUnknown Thinking: {chosen}\n")
                        continue
                    chosen = picked
                else:
                    chosen = chosen.lower()
                if chosen not in choices:
                    print(f"\nUnknown Thinking: {parts[1].strip()}\n")
                else:
                    thinking["name"] = chosen
                    print(f"\nThinking: {thinking['name']}\n")
            _save()
            continue
        if stripped == "/effort" or stripped.startswith("/effort "):
            choices = ("low", "medium", "high")
            parts = stripped.split(maxsplit=1)
            if len(parts) == 1:
                print()
                for n, name in enumerate(choices, 1):
                    mark = " (active)" if name == effort["name"] else ""
                    print(f"{n} {name}{mark}")
                print()
            else:
                chosen = parts[1].strip()
                if chosen.isdigit():
                    n = int(chosen)
                    picked = choices[n - 1] if 1 <= n <= len(choices) else None
                    if picked is None:
                        print(f"\nUnknown Effort: {chosen}\n")
                        continue
                    chosen = picked
                else:
                    chosen = chosen.lower()
                if chosen not in choices:
                    print(f"\nUnknown Effort: {parts[1].strip()}\n")
                else:
                    effort["name"] = chosen
                    print(f"\nEffort: {effort['name']}\n")
            _save()
            continue
        if stripped == "/args" or stripped.startswith("/args "):
            _listed("Args", ("off", "on"), args_display, stripped)
            _save()
            continue
        if stripped == "/output" or stripped.startswith("/output "):
            _listed("Output", ("off", "on"), shell_output, stripped)
            _save()
            continue
        if stripped == "/help":
            print()
            for name, summary, example in COMMANDS:
                print(name)
                print(summary)
                print(example)
                print()
            continue
        if stripped == "/model" or stripped.startswith("/model "):
            print("\nUnknown command: /model. Use /models.\n")
            continue
        if stripped == "/models" or stripped.startswith("/models "):
            ids = list(MODELS)
            parts = stripped.split(maxsplit=1)
            if len(parts) == 1:
                print()
                for n, mid in enumerate(ids, 1):
                    mark = " (active)" if mid == active["id"] else ""
                    print(f"{n} {mid}{mark}")
                print()
            else:
                chosen = parts[1].strip()
                if chosen.isdigit():
                    n = int(chosen)
                    picked = ids[n - 1] if 1 <= n <= len(ids) else None
                    if picked is None:
                        print(f"\nUnknown Model: {chosen}\n")
                        continue
                    chosen = picked
                if chosen not in MODELS:
                    print(f"\nUnknown Model: {chosen}\n")
                else:
                    active["id"] = chosen
                    print(f"\nModel: {active['id']}\n")
            _save()
            continue

        fresh = _STATE["session"] is None
        if fresh:
            _STATE["session"] = sessions.new_session(_settings())
            _STATE["messages"] = [_system()]
        _STATE["messages"].append({"role": "user", "content": text})
        if fresh:
            _save()
            _start_title(_STATE["session"], text, active["id"])
        start_time = time.perf_counter()

        wrote = False
        reasoning = False
        held_nl = ""

        def on_event(kind:str, piece:str = "", final: bool = False) -> None:
            nonlocal wrote, reasoning, held_nl
            show = thinking["name"] == "on"
            if kind == "thinking":
                held_nl = ""
                if show:
                    print("\nThinking:\n---", flush=True)
                else:
                    print("\nThinking:", flush=True)
                reasoning = True
                wrote = True
            elif kind == "reasoning":
                if show:
                    text = held_nl + piece
                    held_nl = ""
                    end = len(text)
                    while end and text[end - 1] == "\n":
                        end -= 1
                    if end < len(text):
                        held_nl = text[end:]
                        text = text[:end]
                    if text:
                        print(text, end="", flush=True)
                reasoning = True
                wrote = True
            elif kind == "reasoning_end":
                if reasoning and show:
                    held_nl = ""
                    print("\n---\n", flush=True)
                held_nl = ""
                reasoning = False
            elif kind == "text":
                print(piece, end="", flush=True)
                wrote = True

        answer = agent(_STATE["messages"], on_event)
        elapsed = time.perf_counter() - start_time
        prompt_tokens = last_usage["prompt_tokens"]
        out_tokens = last_usage["completion_tokens"]
        session_tokens = session_usage["completion_tokens"]
        window = MODELS[active["id"]]["context_window"]
        if wrote:
            print()
        if answer is None:
            print("\n[interrupted by user]\n")
        elif answer:
            print(f"\n{answer}\n")

        ctx = f" | {prompt_tokens / window:.1%} context" if window else ""
        _status(
            f"{prompt_tokens:,} In | {out_tokens:,} Out | {session_tokens:,} Session | Elapsed: {_elapsed(elapsed)}{ctx}"
        )
        _save()

    _join_title()
    _save()

if __name__ == "__main__":
    main()
