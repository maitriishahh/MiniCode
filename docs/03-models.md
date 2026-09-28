# 03 — Model registry + `/model`

Do first: `docs/02-file-tools.md`. Layer 1 is split under `src/minicode/`.
Registry and the one `completion()` site go in `agent.py`. `/model` and the
status id go in `__main__.py`. Do not grow `__main__.py` with the loop.

## What you'll build

Layer 2: a small model registry and a `/model` REPL command. Two entries.
Gemini stays the default. One local entry (`ollama_chat/`) proves a second
provider without a new loop. Still one `completion()` site. Still no shell,
and do not change `SANDBOX`.

## Why it matters

A model string cannot carry `api_base`, which env var holds the key, or a
context window. LiteLLM already speaks Gemini, `ollama_chat/`, and
`openai/<id>` plus `api_base`. The registry is the product layer — the same
kind of standardized record as `tool_from_fn`. OpenCode's 75-provider
catalog, `/connect`, variants, and Pi's models.dev scrape are the thing this
is not. Two entries prove the shape. A third later is one dict entry, not a
new loop.

History is already plain dicts (`model_dump`). A mid-session switch does not
need thinking-trace conversion. The next `completion()` just uses the active
record.

## Skeleton

**Keep the loop. Swap the model arguments.**

1. Keep: tools, `SYSTEM`, message flow, `In | Out | elapsed`, separators.
   Do not touch `SANDBOX` or flip the default to cwd. Do not bring Tok/s
   or summed `total_tokens` back.
2. In `agent.py`, add a `MODELS` dict and an `active` holder. Export
   `active` the same way as `last_usage`. The Gemini id comes from
   `GEMINI_MODEL`. No Python default.
3. The one `completion()` call in `agent()` reads the active record:
   `model`, `api_key=os.getenv(...)`, `api_base` only when set. A raised
   `completion()` returns a string. It must not kill the REPL.
4. `__main__.py` handles `/model` and `/model <id>` before appending a user
   message, same as `exit`. Never sent to the model. Import `active`.
5. The status line shows `active["id"]`. Context % is appended to the
   existing `In | Out | elapsed` line only when `context_window` is a real
   number. No cost line.

## Segment 1 — Record + registry

File: `src/minicode/agent.py`, next to `MODEL` / `API_KEY`. `active` is a
dict so `main()` can reassign the id without a `global` statement — same
pattern as `last_usage`.

```python
def _entry(model_id, api_key_env, api_base=None, context_window=None, max_tokens=None):
    return {
        "id": model_id,
        "api_key_env": api_key_env,
        "api_base": api_base,
        "context_window": context_window,
        "max_tokens": max_tokens,
        "cost": {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0},
        "tools": True,
    }

MODELS = {}
if MODEL:
    MODELS[MODEL] = _entry(MODEL, "GEMINI_API_KEY")

OLLAMA_ID = "ollama_chat/qwen3-coder"
MODELS[OLLAMA_ID] = _entry(
    OLLAMA_ID,
    "OLLAMA_API_KEY",
    api_base="http://127.0.0.1:11434",
)
active = {"id": MODEL if MODEL in MODELS else next(iter(MODELS), None)}
```

`context_window` stays `None` until you have verified the number for that
exact model id from the provider's docs. Do not invent one. Cost stays
zeros and is not printed. `tools: True` is recorded, not acted on — plan
mode is later. `max_tokens` is stored and not passed to `completion()` in
this layer.

Ollama tool calls need the `ollama_chat/` prefix, not `ollama/`. A generic
OpenAI-compatible server is the same record with id `openai/<name>` and an
`api_base` that ends in `/v1`. Do not add that third entry here. The layer
is done even if Ollama is not installed: `/model` must list it. A later
turn that actually calls it may fail on the network; that failure is a
string, not a dead REPL.

`__main__.py` imports `active` and `MODELS` with the other names from
`agent.py`. Drop the `MODEL` import once the status line uses
`active["id"]`.

```python
from minicode.agent import agent, TOOLS, last_usage, SYSTEM, active, MODELS
```

## Segment 2 — One `completion()` site

File: `src/minicode/agent.py`. Replace the `completion(...)` call inside
`agent`. Keep the existing `last_usage` reset, the step loop, dict-history
append, and tool dispatch. Do not add `total_tokens` back.

```python
def agent(messages: list) -> str:
    last_usage["prompt_tokens"] = 0
    last_usage["completion_tokens"] = 0
    record = MODELS[active["id"]]
    for step in range(MAX_STEPS):
        kwargs = {
            "model": record["id"],
            "messages": messages,
            "tools": SCHEMAS,
        }
        api_key = os.getenv(record["api_key_env"])
        if api_key is None and record["api_base"]:
            api_key = "ollama"  # local dummy; never substitute this for Gemini
        if api_key:
            kwargs["api_key"] = api_key
        if record["api_base"]:
            kwargs["api_base"] = record["api_base"]
        try:
            resp = completion(**kwargs)
        except Exception as exc:
            return f"Model error: {exc}"
        usage = getattr(resp, "usage", None)
        last_usage["prompt_tokens"] = getattr(usage, "prompt_tokens", 0) or 0
        last_usage["completion_tokens"] += getattr(usage, "completion_tokens", 0) or 0
        # rest of the loop unchanged: model_dump append, tool dispatch
```

Read `record` once per turn, before the step loop, so a `/model` between
turns is picked up and a switch mid-turn cannot happen (the REPL is blocked
inside `agent`). Overwrite `prompt_tokens`. Do not sum it. That last prompt
is `In`. Summed `completion_tokens` is `Out`. Neither is a Tok/s.

Do not pass `api_base=None`. Do not pass the dummy `"ollama"` key when the
Gemini key is missing — a missing cloud key must still fail visibly.

## Segment 3 — `/model`

File: `src/minicode/__main__.py`, in `main()`, after the empty-line
`continue` and before `messages.append`. Same rule as `exit`: handled
locally, never sent to the model.

```python
stripped = text.strip()
if stripped == "/model" or stripped.startswith("/model "):
    parts = stripped.split(maxsplit=1)
    if len(parts) == 1:
        for mid in MODELS:
            mark = " (active)" if mid == active["id"] else ""
            print(f"{mid}{mark}")
    else:
        chosen = parts[1].strip()
        if chosen not in MODELS:
            print(f"Unknown model: {chosen}")
        else:
            active["id"] = chosen
            print(f"Model: {active['id']}")
    continue
```

Unknown id prints an error and does not switch. `/model` with no argument
lists every id and marks the active one. Do not append a user message.
Do not call `agent`.

## Segment 4 — Status line

File: `src/minicode/__main__.py`. The status block prints `Model: {MODEL}`.
Print `active["id"]` instead. Append context % to the existing
`In | Out | elapsed` line only when both numbers exist:

```python
window = MODELS[active["id"]]["context_window"]
ctx = f" | {prompt_tokens / window:.1%} context" if window else ""
```

```python
print(
    f"---"
    f"\nModel: {active['id']} | Mode: {MODE} | Tools Loaded: {', '.join(TOOLS)}"
    f"\nSandbox: {SANDBOX}"
    f"\n{prompt_tokens:,} In | {out_tokens:,} Out | {elapsed:.1f}{ctx}\n"
    f"---"
)
```

No cost. No fake percent from summed tokens. If you have not verified
`context_window` for that exact id, leave it `None` and `{ctx}` stays empty.
Startup `Sandbox:` line stays. Do not retarget `SANDBOX`.

## Your finished modules

`agent.py` holds `_entry`, `MODELS`, `active`, and the `completion()` kwargs.
`__main__.py` holds `/model` and the status id. Still no TOML. Still no new
package dirs.

## Don't add yet

models.dev import, `/connect`, variants, streaming, fallbacks,
thinking-trace conversion, shell, grep, plan/build, flipping the sandbox
default to cwd, a third registry entry, passing `max_tokens`, a cost line,
Tok/s, new deps, moving the loop back into `__main__.py`.

If `/model` lists both ids, an unknown id does not switch, the next real
turn uses the active record's `model` / `api_key` / `api_base`, a down
local endpoint returns `Model error: …` instead of killing the REPL, and
the status id matches — stop.

## Checkpoint

1. Where does the active id get read, and how many `completion()` sites
   are there?
2. What happens to `/model` — is it appended, sent to the model, or neither?
3. What happens on an unknown id? On a `completion()` exception?
4. Why is context % not a summed token count divided by `context_window`?
5. Why `ollama_chat/` and not `ollama/`? Why is a missing Ollama still a
   finished layer?
6. Why must this layer not change `SANDBOX`?

Answers: (1) `MODELS[active["id"]]` once per `agent` turn, in `agent.py`;
one `completion()` site; (2) neither — `__main__.py` handles it and
`continue`s, same as `exit`; (3) print `Unknown model: …` and keep the
current id; a raised `completion()` returns `Model error: …`; (4) `In` is
the last call's `prompt_tokens`, not a sum — skip the `%` when
`context_window` is `None`; `In | Out | elapsed` stay; (5) LiteLLM tool
calls need the `ollama_chat/` prefix; the checkpoint is the record and the
switch, not a live local server; (6) `sandbox/` is the dev fence so tool
tests cannot touch harness source — product cwd is a later flip, not a
model-registry change.
