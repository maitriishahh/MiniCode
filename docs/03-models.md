# 03 — Model registry + `/model`

Do first: `docs/02-file-tools.md`. Layer 1 is split under `src/minicode/`.
The code still imports LiteLLM. This guide replaces that transport in the
same pass as the registry. Do not add a new LiteLLM call.

Registry and the one `chat.completions.create` site go in `agent.py`.
`/model` and the status id go in `__main__.py`. Do not grow `__main__.py`
with the loop.

Same pass: `uv remove litellm` and `uv add openai`. Local `.env` must drop
a `gemini/` prefix and delete `LITELLM_LOG`, or the first call 404s.

## What you'll build

Layer 2: a small model registry and a `/model` REPL command. Two entries.
Gemini stays the default. One local entry (`qwen3-coder` at Ollama `/v1`)
proves a second server without a new client. Still one create site. Still
no shell, and do not change `SANDBOX`.

## Why it matters

A model string cannot carry `api_base`, which env var holds the key, or a
context window. The `openai` package already speaks any server that exposes
`/chat/completions`. The base URL selects the server. The id is the server's
id. No `gemini/` prefix. No `ollama_chat/` prefix. No SDK per provider.

The registry is the product layer — the same kind of standardized record as
`tool_from_fn`. OpenCode's 75-provider catalog, `/connect`, variants, and
Pi's models.dev scrape are the thing this is not. Two entries prove the
shape. A third later is one dict entry, not a new loop. Groq is that third
entry when you want it: `https://api.groq.com/openai/v1`. Do not add it here.

History is the raw assistant message dict from the response JSON. A
mid-session switch does not need thinking-trace conversion. A Gemini thought
signature, if the server sent one, rides in that dict (`extra_content` on
the tool call). Do not parse it. Do not rebuild `tool_calls`. A 400 that
names `thought_signature` is the only reason to touch that append.

## Skeleton

**Keep the loop. Swap the client.**

1. Keep: tools, `SYSTEM`, message flow, `In | Out | elapsed`, separators.
   Do not touch `SANDBOX` or flip the default to cwd. Do not bring Tok/s
   or summed `total_tokens` back.
2. In `agent.py`, replace `from litellm import completion` with `json` and
   `from openai import OpenAI`. Add a `MODELS` dict and an `active` holder.
   Export `active` the same way as `last_usage`. The Gemini id comes from
   `GEMINI_MODEL`. No Python default. No prefix. Every record has `api_base`.
3. The one `chat.completions.create` in `agent()` reads the active record:
   `model`, `api_key=os.getenv(...)`, `base_url` always. Use
   `with_raw_response` and append the raw message dict. A raised create
   returns a string. It must not kill the REPL.
4. `__main__.py` handles `/model` and `/model <id>` before appending a user
   message, same as `exit`. Never sent to the model. Import `active`.
5. The status line shows `active["id"]`. Context % is appended to the
   existing `In | Out | elapsed` line only when `context_window` is a real
   number. No cost line.

## Segment 1 — Record + registry

File: `src/minicode/agent.py`, next to the old `MODEL` / `API_KEY`. `active`
is a dict so `main()` can reassign the id without a `global` statement —
same pattern as `last_usage`. `api_base` is required. Drop the module-level
`API_KEY`. `MODEL` remains only as the env read that fills the Gemini entry.

```python
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai/"
OLLAMA_BASE = "http://127.0.0.1:11434/v1"

def _entry(model_id, api_key_env, api_base, context_window=None, max_tokens=None):
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
    MODELS[MODEL] = _entry(MODEL, "GEMINI_API_KEY", GEMINI_BASE)

OLLAMA_ID = "qwen3-coder"
MODELS[OLLAMA_ID] = _entry(OLLAMA_ID, "OLLAMA_API_KEY", OLLAMA_BASE)
active = {"id": MODEL if MODEL in MODELS else next(iter(MODELS), None)}
```

`context_window` stays `None` until you have verified the number for that
exact model id from the provider's docs. Do not invent one. Cost stays
zeros and is not printed. `tools: True` is recorded, not acted on — plan
mode is later. `max_tokens` is stored and not passed to `create` in this
layer.

The Ollama id must match a local tag. The layer is done even if Ollama is
not installed: `/model` must list it. A later turn that actually calls it
may fail on the network; that failure is a string, not a dead REPL.

`__main__.py` imports `active` and `MODELS` with the other names from
`agent.py`. Drop the `MODEL` import once the status line uses
`active["id"]`.

```python
from minicode.agent import agent, TOOLS, last_usage, SYSTEM, active, MODELS
```

## Segment 2 — One create site

File: `src/minicode/agent.py`. Replace the `completion(...)` call and the
attribute-access dispatch inside `agent`. Keep the `last_usage` reset and
the step loop. Do not add `total_tokens` back. Do not `model_dump` the
assistant message. Do not rebuild `tool_calls`.

```python
def agent(messages: list) -> str:
    last_usage["prompt_tokens"] = 0
    last_usage["completion_tokens"] = 0
    record = MODELS[active["id"]]
    api_key = os.getenv(record["api_key_env"])
    base = record["api_base"]
    if not api_key and base.startswith(("http://127.0.0.1", "http://localhost")):
        api_key = "ollama"  # local dummy; never substitute this for Gemini
    client = OpenAI(api_key=api_key, base_url=base)
    for step in range(MAX_STEPS):
        try:
            raw = client.with_raw_response.chat.completions.create(
                model=record["id"],
                messages=messages,
                tools=SCHEMAS,
            )
            body = json.loads(raw.text)
        except Exception as exc:
            return f"Model error: {exc}"
        usage = body.get("usage") or {}
        last_usage["prompt_tokens"] = usage.get("prompt_tokens") or 0
        last_usage["completion_tokens"] += usage.get("completion_tokens") or 0
        msg = body["choices"][0]["message"]
        messages.append(msg)
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

Read `record` once per turn, before the step loop, so a `/model` between
turns is picked up and a switch mid-turn cannot happen (the REPL is blocked
inside `agent`). Overwrite `prompt_tokens`. Do not sum it. That last prompt
is `In`. Summed `completion_tokens` is `Out`. Neither is a Tok/s.

Do not pass `base_url` only sometimes. Every record has one. Do not pass the
dummy `"ollama"` key when the Gemini key is missing — a missing cloud key
must still fail visibly. The dummy is only for a loopback base.

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

`agent.py` holds `_entry`, `MODELS`, `active`, and the one
`chat.completions.create`. `__main__.py` holds `/model` and the status id.
Still no TOML. Still no new package dirs. Still no thought-signature parser.

## Don't add yet

models.dev import, `/connect`, variants, streaming, fallbacks,
thinking-trace conversion, a signature parser, shell, grep, plan/build,
flipping the sandbox default to cwd, a third registry entry, passing
`max_tokens`, a cost line, Tok/s, LiteLLM, one SDK per provider, moving
the loop back into `__main__.py`.

If `/model` lists both ids, an unknown id does not switch, the next real
turn uses the active record's `model` / `api_key` / `base_url`, a down
local endpoint returns `Model error: …` instead of killing the REPL, a
`read` then `edit` turn finishes, and the status id matches — stop.

## Checkpoint

1. Where does the active id get read, and how many create sites are there?
2. What happens to `/model` — is it appended, sent to the model, or neither?
3. What happens on an unknown id? On a create exception?
4. Why is context % not a summed token count divided by `context_window`?
5. Why is the Ollama id `qwen3-coder` and not `ollama_chat/qwen3-coder`?
   Why is a missing Ollama still a finished layer?
6. Why must this layer not change `SANDBOX`?
7. Where does a Gemini thought signature live, and what code parses it?

Answers: (1) `MODELS[active["id"]]` once per `agent` turn, in `agent.py`;
one `chat.completions.create` site; (2) neither — `__main__.py` handles it
and `continue`s, same as `exit`; (3) print `Unknown model: …` and keep the
current id; a raised create returns `Model error: …`; (4) `In` is the last
call's `prompt_tokens`, not a sum — skip the `%` when `context_window` is
`None`; `In | Out | elapsed` stay; (5) the base URL selects the server, so
the id is the server's id; the checkpoint is the record and the switch, not
a live local server; (6) `sandbox/` is the dev fence so tool tests cannot
touch harness source — product cwd is a later flip, not a registry change;
(7) it rides in the raw assistant message dict if the server sent it; no
code parses it.
