# 01 — Loop + sandbox + read + status

The layer was built in one file, then split. It was also built on LiteLLM.
The live call is the OpenAI client. Snippets below are the live locations.
A new guide names the file — see `AGENTS.md`. Do not grow `__main__.py`
with the loop.

Do first: `docs/00-setup.md` (venv, `.env`, Gemini reachable).

## What you'll build

`../src` Layer 0: a REPL that sends one message, runs the tool loop to
completion, prints a tool line on success, a status block, and exits
cleanly on `exit` / `quit` / `bye`. One tool: `read`. Live files:
`__main__.py` (REPL), `agent.py` (loop), `schema_generator.py`,
`resolve_path.py`, `tools/read.py`.

## Why it matters

Every later layer (file tools, model registry, plan/build, shell) is this
loop with more entries in the registry. Get the message flow exactly right
once.

## Skeleton

**REPL owns the user message. Loop owns the turn.**

1. REPL (`__main__.py`): read line → `exit`/`quit`/`bye` leaves before any
   model call → else append `{"role": "user", ...}` once and call
   `agent(messages)`.
2. `agent` (`agent.py`): `chat.completions.create` → append the raw assistant
   message once → no
   `tool_calls`? return text → else run each tool (never raise out), append
   one `role: "tool"` per call with the same `tool_call_id` → repeat.
3. `max_steps` reached → return a message the user can act on. Never raise.
4. After a successful tool run, print `|Tools Used: `{name}`|`. Unknown
   tools stay silent on stdout. REPL then prints `minicode >> {answer}` and
   a status block: model, mode, tools, sandbox, `{In} | {Out} | {elapsed}`.
   No Tok/s.

## Segment 1 — Package + config

Create the package. The live split:

```
src/minicode/__init__.py
src/minicode/__main__.py         # REPL only
src/minicode/agent.py            # loop, SYSTEM, registry
src/minicode/schema_generator.py # tool_from_fn
src/minicode/resolve_path.py     # sandbox
src/minicode/tools/read.py
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

`uv sync` installs `minicode` editable so `-m minicode` finds `../src`.
Without the build-system block, that command fails with `No module named minicode`.

Config, at the top of `agent.py` (`load_dotenv()` before any `os.getenv`):

```python
import json
import os
from dotenv import load_dotenv

load_dotenv()

from openai import OpenAI

MODEL = os.getenv("GEMINI_MODEL")  # no prefix; no Python default
API_KEY = os.getenv("GEMINI_API_KEY")
API_BASE = "https://generativelanguage.googleapis.com/v1beta/openai/"
MAX_STEPS = 8
```

Keep `MODEL`, `API_KEY`, `API_BASE`, `MAX_STEPS`. `time` stays in the REPL
(`__main__.py`). Do not put the loop back in `__main__.py`. Layer 2 moves
`API_BASE` onto the model record.

## Segment 2 — Clean loop, no tools yet

File: `src/minicode/agent.py`. The function is `agent`.

Add this. **Do not run yet** — there is no REPL until Segment 5. The
`for call` branch is scaffolding; Segment 4 replaces it and adds `tools=`.

```python
SYSTEM = "You are a concise coding assistant. Use tools when they help. Be brief."

def agent(messages: list) -> str:
    client = OpenAI(api_key=API_KEY, base_url=API_BASE)
    for step in range(MAX_STEPS):
        raw = client.with_raw_response.chat.completions.create(
            model=MODEL,
            messages=messages,
        )
        msg = json.loads(raw.text)["choices"][0]["message"]
        messages.append(msg)  # raw dict, once
        if not msg.get("tool_calls"):
            return msg.get("content") or ""
        for call in msg["tool_calls"]:
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": f"Unknown tool: {call['function']['name']}",
                }
            )
    return f"Max limit reached: {MAX_STEPS}. Try smaller request."
```

No `tools=` yet, so the `for call` branch never fires until Segment 4.

**What just moved:** the assistant message is stored before anything else, so
the next create sees what the model proposed. Append that raw dict. Do not
rebuild `tool_calls`. The `max_steps` fallthrough returns instead of raising,
so the REPL survives.

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
            return f"Invalid Arguments: {exc}"
        try:
            return str(fn(**args.model_dump()))
        except Exception as exc:  # tool code never raises out of the loop
            return f"Tool error: {exc}"
    return schema, run
```

Adapt the parser to your taste, but keep the contract: **(schema, run)**,
validation errors as strings, tool exceptions as strings. Do not add a
`Returns:` block to tool
docstrings unless the parser skips section headers — a line like
`Returns: ...` would be treated as a fake parameter named `Returns`.

## Segment 4 — Sandbox + `read`

Sandbox: `src/minicode/resolve_path.py`. `read`: `src/minicode/tools/read.py`.
Registry and `agent`: `src/minicode/agent.py`.

Paths resolve inside a root-level `sandbox/` directory and never escape.
`.env` files stay denied even inside it. This default is the dev fence
(not cwd, not `src/`) so tool tests cannot overwrite the harness. Product
workspace is the launch cwd, like Pi and OpenCode; flipping the default is
a later pass. `--sandbox path` overrides it:

```python
import sys
from pathlib import Path

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

Replace Segment 2's `agent` with this. `tools=SCHEMAS` is required —
without it the model never sees `read`.

```python
last_usage = {"prompt_tokens": 0, "completion_tokens": 0}

def agent(messages: list) -> str:
    last_usage["prompt_tokens"] = 0
    last_usage["completion_tokens"] = 0
    client = OpenAI(api_key=API_KEY, base_url=API_BASE)
    for step in range(MAX_STEPS):
        raw = client.with_raw_response.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=SCHEMAS,
        )
        body = json.loads(raw.text)
        usage = body.get("usage") or {}
        last_usage["prompt_tokens"] = usage.get("prompt_tokens") or 0
        last_usage["completion_tokens"] += usage.get("completion_tokens") or 0
        msg = body["choices"][0]["message"]
        messages.append(msg)  # raw dict — do not rebuild tool_calls
        calls = msg.get("tool_calls") or []
        if not calls:
            return msg.get("content") or ""
        for call in calls:
            name = call["function"]["name"]
            run = TOOLS.get(name)
            if run:
                content = run(call["function"]["arguments"])
                print(f"|Tools Used: `{name}`|")
            else:
                content = f"Unknown tool: {name}"
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": content,
                }
            )
    return f"Max limit reached: {MAX_STEPS}. Try smaller request."
```

Reset `last_usage` at the start of each turn. `prompt_tokens` is the last
call only (`In`). `completion_tokens` sums across steps (`Out`). A read
turn is two create calls — summing `prompt_tokens` would count the prompt
twice. Print `|Tools Used: `{name}`|` **after** a successful run, not
before, and not for unknown tools. History stores the assistant message as
the raw JSON object from the response body. Do not `model_dump` it. Do not
rebuild `tool_calls`. A Gemini thought signature rides in that dict if the
server sent one. Do not parse it.

**Expected:** ask "read `pyproject.toml`" (or any sandbox file) and see
`|Tools Used: `read`|`. Numbered contents go to the model as `role: "tool"`;
Gemini may quote them or summarize — both are fine. Ask for a missing file
or `../` escape → a tool-error string the model acknowledges, not a traceback.

**What just moved:** the model never sees `read`'s Python. It sees the schema
`tool_from_fn` built from the docstring, proposes a call, and your code runs
it inside the sandbox.

## Segment 5 — REPL + status line

File: `src/minicode/__main__.py`.

```python
MODE = "build"

def main() -> None:
    print(f"Sandbox: {SANDBOX}")
    messages = [{"role": "system", "content": SYSTEM}]
    while True:
        try:
            text = input("user >> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if text.strip().lower() in ("exit", "quit", "bye"):
            break  # never sent to the model
        if not text.strip():
            continue
        messages.append({"role": "user", "content": text})  # once, here only
        start_time = time.perf_counter()
        answer = agent(messages)
        elapsed = time.perf_counter() - start_time
        prompt_tokens = last_usage["prompt_tokens"]
        out_tokens = last_usage["completion_tokens"]
        print(f"\nminicode >> {answer}\n")
        print(
            f"---"
            f"\nModel: {MODEL} | Mode: {MODE} | Tools Loaded: {', '.join(TOOLS)}"
            f"\nSandbox: {SANDBOX}"
            f"\n{prompt_tokens:,} In | {out_tokens:,} Out | {elapsed:.1f}\n"
            f"---"
        )

if __name__ == "__main__":
    main()
```

Now you can run `uv run python -m minicode` from the repo root. It prints
`Sandbox: {SANDBOX}` once at startup. Status block: model id, mode, enabled
tool names, sandbox path, last `prompt_tokens` (`In`), summed
`completion_tokens` (`Out`), elapsed seconds. No Tok/s.

```
---
Model: gemini-3.5-flash-lite | Mode: build | Tools Loaded: read
Sandbox: D:\Pycharm_Projects\MiniCode\sandbox
398 In | 12 Out | 1.7
---
```

Context % waits for Layer 2's Model registry (`usage` ÷ `context_window`).
Cost waits for pricing on the record. Don't fake either here.

## Your finished module

`agent.py` holds the loop. `__main__.py` holds the REPL. `read` is
`tools/read.py`. No `write`, `edit`, shell, modes, or config file.

## Don't add yet

`write`/`edit` (next guide), shell, plan/build swap, permissions UI, Rich,
streaming, sessions, compaction, cost, diff viewer. If the REPL reads files,
prints the tool line, survives bad args and escapes, shows the status block,
and exits cleanly — stop.

## Checkpoint

1. Where is the user message appended, and how many times?
2. What is appended for every assistant reply, even one with `tool_calls`?
3. What happens to a `ValidationError`? To `max_steps`?
4. What does the model see of `read` — the Python or something else?
5. Why does `exit` never reach `chat.completions.create`?

Answers: (1) in the REPL, once, before `agent`; (2) the assistant message
itself, once; (3) both become strings returned to the user / model — the loop
never raises; (4) only the schema (name, description, types); (5) the REPL
breaks before appending or calling.
