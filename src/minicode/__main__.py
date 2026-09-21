import os
import time
import sys
from dotenv import load_dotenv
load_dotenv()

from litellm import completion

import inspect
from typing import get_type_hints
from pydantic import create_model, ValidationError

from pathlib import Path
import difflib

MODEL = os.getenv("GEMINI_MODEL")
API_KEY = os.getenv("GEMINI_API_KEY")
MAX_STEPS = 8

SYSTEM = (
    "You are a concise coding assistant. Use tools when they help. Be brief. "
    "Read before mutating. `write` creates or overwrites whole files with complete content; "
    "`edit` changes one exact unique span. For add/append/insert or replace X with Y, `read` then `edit`; "
    "add/append means insert while preserving all existing content — never delete or rewrite it; "
    "never `write` with partial content."
)

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

def _sandbox_root() -> Path:
    if "--sandbox" in sys.argv:
        i = sys.argv.index("--sandbox")
        if i + 1 < len(sys.argv):
            return Path(sys.argv[i + 1]).resolve()
    return Path(__file__).resolve().parents[2] / "sandbox"

SANDBOX = _sandbox_root()
SANDBOX.mkdir(parents=True, exist_ok=True)

def _resolve(path: str) -> Path:
    p = (SANDBOX / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
    if p != SANDBOX and SANDBOX not in p.parents:
        raise ValueError(f"Outside sandbox: {path}")
    if p.name == ".env" or p.name.startswith(".env."):
        raise ValueError("Refusing to access .env files")
    return p

def read(path: str, offset: int = 1, limit: int = 2000) -> str:
    """Read line-numbered text from a file in the sandbox. Always to be used before editing or writing to any file.

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

def write(path:str, content:str) -> str:
    """
   Create a new file or overwrite an entire existing file with complete content.

    Args:
        path: Path to the file
        content: FULL final file contents — replaces everything
    """
    target = _resolve(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"Wrote {len(content.encode('utf-8'))} bytes to {path}"

def edit(path:str, old_text:str, new_text:str) -> str:
    """
    Replace one exact unique span in an existing file.
    Use for any partial change: replacements, insertions (old_text=anchor, new_text=anchor+insertion), deletions.
    Read the file first for exact text. Never rewrite the whole file; use `write` instead.

    Args:
        path: Path to the file
        old_text: Exact text to find (must match once)
        new_text: Replacement text
    """
    if not old_text:
        raise ValueError("old_text must not be empty")
    target = _resolve(path)
    original = target.read_text(encoding="utf-8", errors="replace")
    n = original.count(old_text)
    if n == 0:
        raise ValueError(f"old_text not found in {path}")
    if n > 1:
        raise ValueError(f"old_text found {n} times in {path}")
    updated = original.replace(old_text, new_text,1)
    diff = "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            updated.splitlines(keepends=True),
            fromfile=f"a/{path} (before)",
            tofile=f"b/{path} (after)",
            lineterm="\n",
        )
    )
    if diff:
        print(f"---\nDiff: {path}\n{diff}", end="---\n" if diff.endswith("\n") else "\n---\n")
        #alternative diff print
        #print(f"---\nDiff: {path}\n{diff.rstrip(chr(10))}\n---")

    target.write_text(updated,encoding="utf-8")
    return f"Replaced 1 occurrence in {path}"



TOOLS = {}
SCHEMAS = []

for _fn in (read,write,edit):
    _schema, _run = tool_from_fn(_fn)
    TOOLS[_fn.__name__] = _run
    SCHEMAS.append(_schema)

last_usage = {"total_tokens":0}


def run_agent(messages:list) -> str:
    last_usage["total_tokens"] = 0
    for step in range(MAX_STEPS):
        resp = completion(
            model=MODEL,
            api_key=API_KEY,
            messages=messages,
            tools=SCHEMAS
        )
        usage = getattr(resp,"usage",None)
        last_usage["total_tokens"] += getattr(usage,"total_tokens",0) or 0
        msg = resp.choices[0].message
        messages.append(
            msg.model_dump(exclude_none=True) if hasattr(msg,"model_dump") else msg
        )
        if not msg.tool_calls:
            return msg.content or ""
        for call in msg.tool_calls:
            run = TOOLS.get(call.function.name)
            if run:
               content = run(call.function.arguments)
               print(f"---\nTools Used: `{str(call.function.name)}`\n---")
            else:
                content = f"Unknown tool: {call.function.name}"

            messages.append(
                {
                    "role":"tool",
                    "tool_call_id":call.id,
                    "content":content,
                }
            )
    return f"Max limit reached: {MAX_STEPS}. Try smaller request."

MODE = "build"

def main() -> None:
    print(f"Sandbox: {SANDBOX}")
    messages = [
        {
            "role":"system",
            "content": SYSTEM
        }
    ]
    while True:
        try:
            text = input("minicode >> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if text.strip().lower() in ("exit", "quit"):
            break
        if not text.strip():
            continue

        messages.append(
            {
                "role":"user",
                "content": text
            }
        )
        start_time = time.perf_counter()
        answer = run_agent(messages)
        end_time = time.perf_counter()
        token_usage = last_usage["total_tokens"]
        token_time = end_time - start_time
        token_per_sec = token_usage / token_time if token_time else 0.0
        print(f"---\n{answer}\n---")
        print(
            f"---"
            f"\nModel: {MODEL} | Mode: {MODE} | Tools Loaded: {', '.join(TOOLS)}"
            f"\nSandbox: {SANDBOX}\n{token_usage:,} Tokens | {token_per_sec:.4f}  Tok/s\n"
            f"---"
        )

if __name__ == "__main__":
    main()
