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
effort = {"name": "low"}
args_display = {"name": "off"}
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

TITLE_SYSTEM = (
    "Extract a concise 2 to 5 word title from the user prompt. "
    "Capitalize major words and keep minor words like 'in', 'of', 'the', 'and' in lowercase "
    "(example: 'The Evolution of Artificial Intelligence'). "
    "Output only the title."
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

def _tool_line(name: str, args: str) -> str:
    if args_display["name"] == "off":
        return f"|Tool Used: `{name}`"
    one = f"|Tool Used: `{name}` ({args})|"
    try:
        data = json.loads(args)
    except json.JSONDecodeError:
        return one
    if not isinstance(data, dict):
        return one
    if not any(isinstance(v, str) and "\n" in v for v in data.values()):
        return one
    lines = [f"|Tool Used: `{name}`"]
    for key, value in data.items():
        text = value if isinstance(value, str) else json.dumps(value)
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        parts = text.split("\n")
        lines.append(f"|{key}: {parts[0]}")
        for part in parts[1:]:
            lines.append(f"|{part}")
    return "\n".join(lines)

_OPEN_TAGS = (("<thought>", "</thought>"), ("<think>", "</think>"))

def _gemini_extra(base: str) -> dict | None:
    if "generativelanguage.googleapis.com" not in base:
        return None
    return {
        "extra_body": {
            "google": {
                "thinking_config": {
                    "include_thoughts": True,
                    "thinking_level": effort["name"],
                }
            }
        }
    }

def _tag_suffix(text: str, tags: tuple[str, ...]) -> str:
    best = ""
    lowered = text.lower()
    for tag in tags:
        limit = min(len(text), len(tag) - 1)
        for n in range(limit, 0, -1):
            if lowered.endswith(tag[:n]):
                if n > len(best):
                    best = text[-n:]
                break
    return best

def _apply_usage(usage: dict | None) -> None:
    if not usage:
        return
    last_usage["prompt_tokens"] = usage.get("prompt_tokens") or 0
    step_out = usage.get("completion_tokens") or 0
    last_usage["completion_tokens"] += step_out
    session_usage["completion_tokens"] += step_out


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

    # record = MODELS.get(model_id)
    # if record is None:
    #     return None
    # base = record["api_base"]
    #
    # # 45s timeout and 512 max_tokens so reasoning models have room to finish
    # create_kwargs = {
    #     "model": record["id"],
    #     "messages": [
    #         {"role": "system", "content": TITLE_SYSTEM},
    #         {"role": "user", "content": first_prompt[:2000]},
    #     ],
    #     "max_tokens": 512,
    #     "stream": False,
    #     "timeout": 45.0,
    # }
    #
    # # Use thinking_level: minimal (valid for Gemini 3.x) with double-nested extra_body
    # if "generativelanguage.googleapis.com" in base:
    #     create_kwargs["extra_body"] = {
    #         "extra_body": {
    #             "google": {
    #                 "thinking_config": {
    #                     "thinking_level": "minimal",
    #                     "include_thoughts": False,
    #                 }
    #             }
    #         }
    #     }
    # elif base.startswith(("http://127.0.0.1", "http://localhost")):
    #     create_kwargs["reasoning_effort"] = "low"
    #
    # try:
    #     client = _client_for(record, max_retries=2)
    #     response = _create(client, **create_kwargs)
    #     content = response.choices[0].message.content
    #     title = _clean_title(content)
    #     if title:
    #         return title
    # except Exception:
    #     pass
    #
    # # Safe fallback: extract first 5-6 words from prompt if API call fails
    # words = [w for w in first_prompt.strip().split() if w]
    # if words:
    #     clean_prompt = " ".join(words[:6]).strip("\"'`*# ")
    #     return clean_prompt[:60]
    # return None


def _consume(stream, on_event, state: dict) -> None:
    state["text"] = ""
    state["calls"] = []
    state["extra"] = None
    state["usage"] = None
    by_index: dict = {}
    by_id: dict = {}
    reasoning = False
    in_thought = False
    close_tag = ""
    held = ""
    state["streamed"] = False

    def emit(kind: str, piece: str = "") -> None:
        if on_event:
            on_event(kind, piece)

    def close_reasoning() -> None:
        nonlocal reasoning
        if reasoning:
            emit("reasoning_end")
            reasoning = False

    def emit_reasoning(text: str) -> None:
        nonlocal reasoning
        if not text:
            return
        if not reasoning:
            if not text.strip():
                return
            emit("thinking")
            reasoning = True
        emit("reasoning", text)

    def emit_text(piece: str) -> None:
        if not piece:
            return
        close_reasoning()
        state["text"] += piece
        state["streamed"] = True
        emit("text", piece)

    def feed(piece: str) -> None:
        nonlocal held, in_thought, close_tag
        buf = held + piece
        held = ""
        while buf:
            if not in_thought:
                lower = buf.lower()
                found_at = -1
                found_open = ""
                found_close = ""
                for open_tag, close in _OPEN_TAGS:
                    at = lower.find(open_tag)
                    if at != -1 and (found_at == -1 or at < found_at):
                        found_at = at
                        found_open = open_tag
                        found_close = close
                if found_at == -1:
                    suffix = _tag_suffix(buf, tuple(tag for tag, _ in _OPEN_TAGS))
                    if suffix:
                        emit_text(buf[:-len(suffix)])
                        held = suffix
                        return
                    emit_text(buf)
                    return
                if found_at:
                    emit_text(buf[:found_at])
                in_thought = True
                close_tag = found_close
                buf = buf[found_at + len(found_open):]
                continue
            lower = buf.lower()
            at = lower.find(close_tag)
            if at == -1:
                suffix = _tag_suffix(buf, (close_tag,))
                if suffix:
                    emit_reasoning(buf[:-len(suffix)])
                    held = suffix
                    return
                emit_reasoning(buf)
                return
            end = at + len(close_tag)
            if at:
                emit_reasoning(buf[:at])
            close_reasoning()
            in_thought = False
            close_tag = ""
            buf = buf[end:]

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
        think = delta.get("reasoning_content") or delta.get("reasoning")
        if isinstance(think, str) and think:
            emit_reasoning(think)
        piece = delta.get("content")
        if isinstance(piece, str) and piece:
            feed(piece)
        items = delta.get("tool_calls") or []
        if items:
            if in_thought and held:
                emit_reasoning(held)
            elif held:
                emit_text(held)
            held = ""
            in_thought = False
            close_reasoning()
            for item in items:
                _merge_call(state["calls"], by_index, by_id, item)
    if in_thought and held:
        emit_reasoning(held)
    elif held:
        emit_text(held)
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
    base = record["api_base"]
    try:
        client = _client_for(record)
    except Exception as exc:
        return f"Model Error: {exc}"
    for step in range(MAX_STEPS):
        state = {"text": "", "calls": [], "extra": None, "usage": None}
        appended = False
        try:
            create = {
                "model": record["id"],
                "messages": messages,
                "tools": active_schemas(),
                "stream": True,
                "stream_options": {"include_usage": True},
            }
            extra = _gemini_extra(base)
            if extra:
                create["extra_body"] = extra
            elif base.startswith(("http://127.0.0.1", "http://localhost")):
                create["reasoning_effort"] = effort["name"]
            stream = _create(client, **create)
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
            if state["text"] and on_event and not state.get("streamed"):
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
            if state["text"] and on_event and not state.get("streamed"):
                on_event("text", state["text"])
            return f"Model Error: {exc}"
        msg = _assistant(state["text"], state["calls"], state["extra"])
        messages.append(msg)
        appended = True
        if not state["calls"]:
            if on_event and not state.get("streamed"):
                on_event("text", msg["content"])
            return ""
        done: set[str] = set()
        try:
            if state["text"] and on_event and not state.get("streamed"):
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
                    print(f"\n{_tool_line(name, args)}\n")
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