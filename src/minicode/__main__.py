import os
from dotenv import load_dotenv
load_dotenv()

from litellm import completion

import inspect
from typing import get_type_hints
from pydantic import create_model, ValidationError

from pathlib import Path

MODEL = os.getenv("GEMINI_MODEL")
API_KEY = os.getenv("GEMINI_API_KEY")
MAX_STEPS = 8
SYSTEM = "You are a concise coding assistant. Use tools when they help. Be brief."
#TYPE_MAP = {"string":"str","integer":"int","number":"float","boolean":"bool"}

TYPE_MAP = {"str": "string", "int": "integer", "float": "number", "bool": "boolean"}

def tool_from_fn(fn):
    """
    Build (openai_schema,run) from a function with a Google-style docstring.
    """
    sig = inspect.signature(fn)
    hints = get_type_hints(fn)
    doc = inspect.getdoc(fn) or fn.__name__
    lines = doc.splitlines()
    description = lines[0].strip()

    #parse "Args:" block: name: description
    params, in_args = {}, False
    for line in lines[1:]:
        s = line.strip()
        if s.lower().startswith("args:"):
            in_args = True
            continue
        if in_args:
            if not s or ":" not in s:
                if not s:
                    continue
                break
            name, desc = s.split(":", 1)
            params[name.strip()] = desc.strip()

    fields = {}
    properties = {}
    required = []
    for name, p in sig.parameters.items():
        t = hints.get(name, str)
        tname = getattr(t, "__name__", "str")
        fields[name] = (t, ...)
        properties[name] = {
            "type": TYPE_MAP.get(tname, "string"),
            "description": params.get(name, name),
        }
        if p.default is inspect.Parameter.empty:
            required.append(name)
        else:
            fields[name] = (t, p.default)

    model = create_model(fn.__name__ + "Args", **fields)
    schema = {
        "type":"function",
        "function":{
            "name":fn.__name__,
            "description":description,
            "parameters":{
                "type":"object",
                "properties":properties,
                "required":required,
            },
        },
    }

    def run(raw_json: str) -> str:
        try:
            args = model.model_validate_json(raw_json)
        except ValidationError as exc:
            return f"Invalid Arguments: {exc}"
        try:
            return str(fn(**args.model_dump()))
        except Exception as exc:
            return f"Tool error: {exc}"
    return schema, run

SANDBOX = Path.cwd().resolve()

def _resolve(path: str) -> Path:
    p = (SANDBOX / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
    if p != SANDBOX and SANDBOX not in p.parents:
        raise ValueError(f"Outside sandbox: {path}")
    if p.name == ".env" or p.name.startswith(".env."):
        raise ValueError("Refusing to read .env files")
    return p

def read(path: str, offset: int = 1, limit: int = 2000) -> str:
    """Read line-numbered text from a file in the sandbox.

    Args:
        path: Path to the file, relative to the sandbox
        offset: First line to read (1-indexed)
        limit: Maximum lines to return
    """
    target = _resolve(path)
    lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    start = max(offset - 1, 0)
    picked = lines[start:start + limit]
    numbered = [f"{start + i + 1}: {line}" for i, line in enumerate(picked)]
    return "\n".join(numbered) if numbered else "(empty file)"

TOOLS = {}
SCHEMAS = []

for _fn in (read,):
    _schema, _run = tool_from_fn(_fn)
    TOOLS[_fn.__name__] = _run
    SCHEMAS.append(_schema)

last_usage = {"total_tokens":0}


def run_agent(messages:list) -> str:
    for step in range(MAX_STEPS):
        resp = completion(
            model=MODEL,
            api_key=API_KEY,
            messages=messages,
            tools=SCHEMAS
        )
        usage = getattr(resp,"usage",None)
        last_usage["total_tokens"] = getattr(usage,"total_tokens",0) or 0
        msg = resp.choices[0].message
        messages.append(msg)
        if not msg.tool_calls:
            return msg.content or ""
        for call in msg.tool_calls:
            run = TOOLS.get(call.function.name)
            content = (
                run(call.function.arguments)
                if run
                else f"Unknown tool: {call.function.name}"
            )
            messages.append(
                {
                    "role":"tool",
                    "tool_call_id":call.id,
                    "content":content,
                }
            )
    return f"Max limit reached: {MAX_STEPS}. Try smaller request."

