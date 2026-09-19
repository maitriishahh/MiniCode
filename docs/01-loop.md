# 01 — Loop + sandbox + read + status

Do first: `docs/00-setup.md` (venv, `.env`, Gemini reachable).

## What you'll build

`src/minicode` Layer 0: a REPL that sends one message, runs the tool loop to
completion, prints one status line, and exits cleanly on `exit`. One tool:
`read`. Still one growing module.

## Why it matters

Every later layer (file tools, model registry, plan/build, shell) is this
loop with more entries in the registry. Get the message flow exactly right
once.

## Skeleton

**REPL owns the user message. Loop owns the turn.**

1. REPL: read line → `exit`/`quit` leaves before any model call → else append
   `{"role": "user", ...}` once and call `run_agent(messages)`.
2. `run_agent`: `completion()` → append assistant once → no `tool_calls`?
   return text → else run each tool (never raise out), append one
   `role: "tool"` per call with the same `tool_call_id` → repeat.
3. `max_steps` reached → return a message the user can act on. Never raise.
4. REPL prints the answer + one status line: model, mode, tools, tokens.

## Segment 1 — Package + config

Create the package as one growing module:

```
src/minicode/__init__.py      # empty
src/minicode/__main__.py      # everything in this guide lives here
```

After those two files exist, make the package runnable. Add this to
`pyproject.toml` (keep the existing `[project]` table):

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

Then from the repo root:

```powershell
uv sync
uv run python -m minicode
```

`uv sync` installs `minicode` editable so `-m minicode` finds `src/minicode`.
Without the build-system block, that command fails with `No module named minicode`.

Config, at the top of `__main__.py`:

```python
import os
from dotenv import load_dotenv

load_dotenv()  # before litellm: it reads LITELLM_LOG at import time

from litellm import completion

MODEL = os.getenv("GEMINI_MODEL", "gemini/gemini-3.5-flash-lite")
API_KEY = os.getenv("GEMINI_API_KEY")
MAX_STEPS = 8
```

Keep `MODEL`, `API_KEY`, `MAX_STEPS` and the import order. Everything below
grows in this same file until it is awkward — then it splits into
`loop.py` / `tools.py` with the same function names.

## Segment 2 — Clean loop, no tools yet

Add this. **Do not run yet** — there is no REPL until Segment 5. The
`for call` branch is scaffolding; Segment 4 replaces it and adds `tools=`.

```python
SYSTEM = "You are a concise coding assistant. Use tools when they help. Be brief."

def run_agent(messages: list) -> str:
    for step in range(MAX_STEPS):
        resp = completion(model=MODEL, api_key=API_KEY, messages=messages)
        msg = resp.choices[0].message
        messages.append(msg)  # always, once
        if not msg.tool_calls:
            return msg.content or ""
        for call in msg.tool_calls:
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": f"Unknown tool: {call.function.name}",
                }
            )
    return f"Stopped after {MAX_STEPS} steps without an answer. Try a smaller request."
```

No `tools=` yet, so the `for call` branch never fires until Segment 4.

**What just moved:** the assistant message is stored before anything else, so
the next `completion()` sees what the model proposed. The `max_steps` fallthrough
returns instead of raising, so the REPL survives.

## Segment 3 — `tool_from_fn`

The control point. Google-style docstring in, OpenAI schema + validation out.
`pydantic.create_model` from day one: schema and validation in one step.

```python
import inspect
from typing import get_type_hints
from pydantic import create_model, ValidationError

TYPE_MAP = {"str": "string", "int": "integer", "float": "number", "bool": "boolean"}

def tool_from_fn(fn):
    """Build (openai_schema, run) from a function with a Google-style docstring."""
    sig = inspect.signature(fn)
    hints = get_type_hints(fn)
    doc = inspect.getdoc(fn) or fn.__name__
    lines = doc.splitlines()
    description = lines[0].strip()
    # parse "Args:" block:  name: description
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
        "type": "function",
        "function": {
            "name": fn.__name__,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }
    def run(raw_json: str) -> str:
        try:
            args = model.model_validate_json(raw_json)
        except ValidationError as exc:
            return f"Invalid arguments: {exc}"
        try:
            return str(fn(**args.model_dump()))
        except Exception as exc:  # tool code never raises out of the loop
            return f"Tool error: {exc}"
    return schema, run
```

Adapt the parser to your taste, but keep the contract: **(schema, run)**,
validation errors as strings, tool exceptions as strings. Do not use
`litellm.utils.function_to_dict`. Do not add a `Returns:` block to tool
docstrings unless the parser skips section headers — a line like
`Returns: ...` would be treated as a fake parameter named `Returns`.

## Segment 4 — Sandbox + `read`

Paths resolve inside a sandbox directory and never escape. `.env` files stay
denied even inside it.

```python
from pathlib import Path

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
```

Why `offset=1`: files and editors are 1-indexed, so 1 is the first line and
omitting it starts at the top. `limit` caps how much of a huge file enters
the context.

Wire the registry and dispatch. Replace the Segment 2 placeholder branch:

```python
TOOLS = {}
SCHEMAS = []
for _fn in (read,):
    _schema, _run = tool_from_fn(_fn)
    TOOLS[_fn.__name__] = _run
    SCHEMAS.append(_schema)
```

Replace Segment 2's `run_agent` with this. `tools=SCHEMAS` is required —
without it the model never sees `read`.

```python
last_usage = {"total_tokens": 0}

def run_agent(messages: list) -> str:
    for step in range(MAX_STEPS):
        resp = completion(
            model=MODEL,
            api_key=API_KEY,
            messages=messages,
            tools=SCHEMAS,
        )
        usage = getattr(resp, "usage", None)
        last_usage["total_tokens"] = getattr(usage, "total_tokens", 0) or 0
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
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": content,
                }
            )
    return f"Stopped after {MAX_STEPS} steps without an answer. Try a smaller request."
```

**Expected:** ask "read `pyproject.toml`" (or any sandbox file) and see the
numbered contents. Ask for a missing file or `../` escape → a tool-error
string the model acknowledges, not a traceback.

**What just moved:** the model never sees `read`'s Python. It sees the schema
`tool_from_fn` built from the docstring, proposes a call, and your code runs
it inside the sandbox.

## Segment 5 — REPL + status line

```python
MODE = "build"  # plan mode arrives later; the status line already shows it

def main() -> None:
    messages = [{"role": "system", "content": SYSTEM}]
    while True:
        try:
            text = input("minicode> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if text.strip().lower() in ("exit", "quit"):
            break  # never sent to the model
        if not text.strip():
            continue
        messages.append({"role": "user", "content": text})  # once, here only
        answer = run_agent(messages)
        print(answer)
        print(
            f"-- {MODEL}  {MODE}  tools: {','.join(TOOLS)}  "
            f"{last_usage['total_tokens']:,} tok --"
        )

if __name__ == "__main__":
    main()
```

Now you can run `uv run python -m minicode`. Status line for this layer:
model id, mode, enabled tool names, tokens from `last_usage` (updated inside
`run_agent` from `resp.usage` — not from the returned string).

```
-- gemini/gemini-3.5-flash-lite  build  tools: read  1,204 tok --
```

Context % waits for Layer 2's Model registry (`usage` ÷ `context_window`).
Cost waits for pricing on the record. Don't fake either here.

## Your finished module

`src/minicode/__main__.py`: `MODEL`, `API_KEY`, `MAX_STEPS`, `SYSTEM`,
`SANDBOX`, `tool_from_fn`, `read`, `TOOLS`/`SCHEMAS`, `run_agent`,
`main`. Roughly 150–200 lines. No `write`, `edit`, shell, modes, or config
file.

## Don't add yet

`write`/`edit` (next guide), shell, plan/build swap, permissions UI, Rich,
streaming, sessions, compaction, cost, diff viewer. If the REPL reads files,
survives bad args and escapes, shows the status, and exits cleanly — stop.

## Checkpoint

1. Where is the user message appended, and how many times?
2. What is appended for every assistant reply, even one with `tool_calls`?
3. What happens to a `ValidationError`? To `max_steps`?
4. What does the model see of `read` — the Python or something else?
5. Why does `exit` never reach `completion()`?

Answers: (1) in the REPL, once, before `run_agent`; (2) the assistant message
itself, once; (3) both become strings returned to the user / model — the loop
never raises; (4) only the schema (name, description, types); (5) the REPL
breaks before appending or calling.
