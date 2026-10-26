import json
import os
import uuid
from dotenv import load_dotenv

load_dotenv()

from openai import OpenAI

from minicode.schema_generator import tool_from_fn
from minicode.tools.read import read
from minicode.tools.write import write
from minicode.tools.edit import edit
from minicode.tools.glob import glob
from minicode.tools.grep import grep
from minicode.tools.shell import shell
from minicode.permissions import decide, force_ask, plan_touches
from minicode.resolve_path import SANDBOX, classify, approve, clear_approved

MAX_STEPS = 16

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai/"
OLLAMA_BASE = "http://127.0.0.1:11434/v1"

_SERVERS = (
    ("GEMINI_MODEL", "GEMINI_API_KEY", GEMINI_BASE),
    ("OLLAMA_MODEL", "OLLAMA_API_KEY", OLLAMA_BASE),
)

def _entry(model_id, api_key_env, api_base, context_window=None, max_tokens=None):
    return {
        "id": model_id,
        "api_key": api_key_env,
        "api_base": api_base,
        "context_window": context_window,
        "max_tokens": max_tokens,
        "cost": {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0},
        "tools": True,
    }

MODELS = {}
for id_env, key_env, base in _SERVERS:
    model_id = os.getenv(id_env)
    if model_id:
        MODELS[model_id] = _entry(model_id, key_env, base)

default_id = os.getenv("GEMINI_MODEL")
active = {"id": default_id if default_id in MODELS else next(iter(MODELS), None)}

SYSTEM = (
    "You are a concise coding assistant. Use tools when they help. Be brief. "
    "`write` creates a new file, or overwrites an existing file with complete content. "
    "To overwrite, `read` then `write` the full file. "
    "`edit` changes one exact unique span. For add/append/insert or replace X with Y, `read` then `edit`; "
    "add/append means insert while preserving all existing content — never delete or rewrite it; "
    "never `write` with partial content. "
    "A new file is `write`, not the shell. "
    f"Workspace is {SANDBOX}. A path may be absolute. Outside it asks permission. "
    "A path the user already named is read with `read`, not `glob` and not the shell. "
    "Locate an unknown file with `glob`, then `grep`, then `read`. "
    f"Run tests and git with `{shell.__name__}`. Do not use it to read or search files."
)


mode = {"name":"plan"}
PLAN_DENIED = ("write", "edit")
PLAN_SYSTEM = (
    "You are in plan mode. Read, search, and reason. "
    "Do not create or modify files. Do not paste file contents. "
    "Do not create or delete files with the shell. "
    "Never name internal tools. Speak in user actions: 'I will edit...', 'I checked...', not 'Use edit/glob/grep'. "
    "Propose the file, the change, and the reason. "
    "If the user asks you to create or change a file, end by telling them to run /build. "
    "After `glob` returns, read every matching file in that same response. Do not read one file per turn. "
    "If the user named a file, read that path; do not glob first."
)


TOOLS = {}
SCHEMAS = []
KEYS = {
    "read": "read",
    "write": "edit",
    "edit": "edit",
    "glob": "glob",
    "grep": "grep",
    "bash": "shell",
    "powershell": "shell",
}

def _value(key: str, parsed: dict) -> str | None:
    if key in ("shell", "glob", "grep"):
        field = "command" if key == "shell" else "pattern"
        raw = parsed.get(field)
        return raw if isinstance(raw, str) else None
    raw = parsed.get("path")
    return raw if isinstance(raw, str) else None


def _permit(name: str, raw: str) -> str | None:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    path = parsed.get("path")
    if isinstance(path, str) and name in ("read", "write", "edit", "glob", "grep"):
        kind, resolved = classify(path)
        if kind == "dotenv":
            shown = resolved.as_posix()
            if decide("read", shown) == "deny":
                return f"Permission denied: read {shown}"
            approve(resolved)
            return None
        if kind == "external":
            shown = resolved.as_posix()
            if decide("external_directory", shown) == "deny":
                return f"Permission denied: external_directory {shown}"
            approve(resolved)
    key = KEYS.get(name)
    if key is None:
        return None
    value = _value(key, parsed)
    if value is None:
        return None
    if key == "shell" and mode["name"] == "plan" and plan_touches(value):
        if force_ask(key, value) == "deny":
            return (
                "Plan mode: that command was denied. "
                "Do not try another shell command to create or change a file. "
                "Tell the user to run /build."
            )
        return None
    action = decide(key, value)
    if action == "deny":
        return f"Permission denied: {key} {value}"
    return None

def active_schemas() -> list:
    """
    Return the schemas for the current code.
    """
    if mode["name"] != "plan":
        return SCHEMAS
    return [s for s in SCHEMAS if s["function"]["name"] not in PLAN_DENIED]

def active_names() -> list[str]:
    """
    Return the tool names for the current mode.
    """
    if mode["name"] != "plan":
        return list(TOOLS)
    return [n for n in TOOLS if n not in PLAN_DENIED]

for _fn in (read, write, edit, glob, grep, shell):
    _schema, _run = tool_from_fn(_fn)
    TOOLS[_fn.__name__] = _run
    SCHEMAS.append(_schema)

last_usage = {"prompt_tokens": 0, "completion_tokens": 0}
session_usage = {"completion_tokens": 0}

def _tool_note(content: str) -> None:
    print(f"\n{content}\n")

def _apply_usage(usage: dict | None) -> None:
    if not usage:
        return
    last_usage["prompt_tokens"] = usage.get("prompt_tokens") or 0
    step_out = usage.get("completion_tokens") or 0
    last_usage["completion_tokens"] += step_out
    session_usage["completion_tokens"] += step_out


def _consume(stream, on_event, state: dict) -> None:
    state["text"] = ""
    state["calls"] = []
    state["extra"] = None
    state["usage"] = None
    by_index: dict = {}
    by_id: dict = {}
    reasoning = False
    closed = False

    def emit(kind: str, piece: str = "") -> None:
        if on_event:
            on_event(kind, piece)

    def close_reasoning() -> None:
        nonlocal closed
        if reasoning and not closed:
            emit("reasoning_end")
            closed = True

    for chunk in stream:
        data = chunk.to_dict()
        if data.get("usage"):
            state["usage"] = data["usage"]
        choices = data.get("choices") or []
        if not choices:
            continue
        delta = choices[0].get("delta") or {}
        if delta.get("extra_content") is not None:
            state["extra"] = delta["extra_content"]
        if not state["text"] and not state["calls"]:
            think = delta.get("reasoning_content") or delta.get("reasoning")
            if isinstance(think, str) and think:
                if not reasoning:
                    emit("thinking")
                    reasoning = True
                emit("reasoning", think)
        piece = delta.get("content")
        if isinstance(piece, str) and piece:
            close_reasoning()
            state["text"] += piece
        items = delta.get("tool_calls") or []
        if items:
            close_reasoning()
            for item in items:
                _merge_call(state["calls"], by_index, by_id, item)
    close_reasoning()

def _merge_call(calls: list, by_index: dict, by_id: dict, delta: dict) -> None:
    fn = delta.get("function") or {}
    index = delta.get("index")
    call_id = delta.get("id")
    name = fn.get("name") or ""
    arguments = fn.get("arguments") or ""
    target = None
    if index is not None and index in by_index:
        target = by_index[index]
    elif isinstance(call_id, str) and call_id in by_id:
        target = by_id[call_id]
    elif calls and not call_id and not name:
        target = calls[-1]
    if target is None:
        fresh = call_id if isinstance(call_id, str) and call_id else str(uuid.uuid4())
        target = {
            "id": fresh,
            "type": delta.get("type") or "function",
            "function": {"name": "", "arguments": ""},
        }
        calls.append(target)
        by_id[fresh] = target
    if index is not None:
        by_index[index] = target
    if isinstance(call_id, str) and call_id:
        by_id[call_id] = target
        target["id"] = call_id
    if name:
        target["function"]["name"] += name
    if arguments:
        target["function"]["arguments"] += arguments
    if delta.get("extra_content") is not None:
        target["extra_content"] = delta["extra_content"]


def _assistant(text: str, calls: list, extra) -> dict:
    msg: dict = {"role": "assistant", "content": text or None}
    if calls:
        stored = []
        for call in calls:
            item = {
                "id": call["id"],
                "type": call.get("type") or "function",
                "function": {
                    "name": call["function"]["name"],
                    "arguments": call["function"]["arguments"] or "{}",
                },
            }
            if "extra_content" in call:
                item["extra_content"] = call["extra_content"]
            stored.append(item)
        msg["tool_calls"] = stored
    if extra is not None:
        msg["extra_content"] = extra
    if not text and not calls:
        msg["content"] = "[empty response]"
    return msg


def _marked(text: str, marker: str) -> str:
    body = text.rstrip()
    return f"{body}\n\n{marker}" if body else marker

def agent(messages: list, on_event=None) -> str | None:
    last_usage["prompt_tokens"] = 0
    last_usage["completion_tokens"] = 0
    record = MODELS[active["id"]]
    api_key = os.getenv(record["api_key"])
    base = record["api_base"]
    if not api_key and base.startswith(("http://127.0.0.1", "http://localhost")):
        api_key = "ollama"
    try:
        client = OpenAI(api_key=api_key, base_url=base)
    except Exception as exc:
        return f"Model Error: {exc}"
    for step in range(MAX_STEPS):
        state = {"text": "", "calls": [], "extra": None, "usage": None}
        appended = False
        try:
            stream = client.chat.completions.create(
                model=record["id"],
                messages=messages,
                tools=active_schemas(),
                stream=True,
                stream_options={"include_usage": True},
            )
            _consume(stream, on_event, state)
            _apply_usage(state["usage"])
        except KeyboardInterrupt:
            if on_event:
                on_event("reasoning_end")
            messages.append({
                "role": "assistant",
                "content": _marked(state["text"], "[interrupted by user]"),
                **({"extra_content": state["extra"]} if state["extra"] is not None else {}),
            })
            if state["text"] and on_event:
                on_event("text", state["text"])
            return None
        except Exception as exc:
            if on_event:
                on_event("reasoning_end")
            messages.append({
                "role": "assistant",
                "content": _marked(state["text"], "[model error]"),
                **({"extra_content": state["extra"]} if state["extra"] is not None else {}),
            })
            if state["text"] and on_event:
                on_event("text", state["text"])
            return f"Model Error: {exc}"
        msg = _assistant(state["text"], state["calls"], state["extra"])
        messages.append(msg)
        appended = True
        if not state["calls"]:
            if on_event:
                on_event("text", msg["content"], final=True)
            return ""
        done: set[str] = set()
        try:
            if state["text"] and on_event:
                on_event("text", state["text"])
            for call in msg["tool_calls"]:
                name = call["function"]["name"]
                args = call["function"]["arguments"]
                if mode["name"] == "plan" and name in PLAN_DENIED:
                    content = f"Plan mode: `{name}` is disabled. Propose the change and ask to run /build."
                    note = True
                    ran = False
                else:
                    run = TOOLS.get(name)
                    if run:
                        denied = _permit(name, args)
                        try:
                            if denied is not None:
                                content = denied
                                note = True
                                ran = False
                            else:
                                content = run(args)
                                note = False
                                ran = True
                        finally:
                            clear_approved()
                    else:
                        content = f"Unknown tool: {name}"
                        note = True
                        ran = False
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": content})
                done.add(call["id"])
                if note:
                    _tool_note(content)
                elif ran:
                    print(f"\n|Tools Used: `{name}` ({args})|\n")
        except KeyboardInterrupt:
            for call in msg["tool_calls"]:
                if call["id"] not in done:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": "Interrupted by user.",
                    })
            return None
        _ = appended
    return f"Max limit reached: {MAX_STEPS}. Try smaller request."