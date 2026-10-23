# 03 — Model registry + `/model`

Do first: `docs/02-file-tools.md`. Layer 1 is split under `src/minicode/`.
This layer is implemented. Snippets below are the live code. Do not grow
`__main__.py` with the loop. Do not change `SANDBOX`.

Registry and the one `chat.completions.create` site live in `agent.py`.
`/model` and the status id live in `__main__.py`.

## What it is

A small model registry and a `/model` REPL command. Servers are a tuple.
Ids come from `.env`. Bases stay in code. Gemini is the startup default
when `GEMINI_MODEL` is set. Ollama is the second server. Still one create
site. Still no shell.

## Why it matters

A model string cannot carry `api_base`, which env var holds the key, or a
context window. The `openai` package speaks any server that exposes
`/chat/completions`. The base URL selects the server. The id is the server's
id. No `gemini/` prefix. No `ollama_chat/` prefix. No SDK per provider.

The registry is the product layer — the same kind of standardized record as
`tool_from_fn`. OpenCode's 75-provider catalog, `/connect`, variants, and
Pi's models.dev scrape are the thing this is not. A new server is one
`_SERVERS` tuple plus two env lines, not a new client. Groq later is
`https://api.groq.com/openai/v1`. Do not add it until asked.

History is the raw assistant message dict from the response JSON. A
mid-session switch does not need thinking-trace conversion. A Gemini thought
signature, if the server sent one, rides in that dict. Do not parse it.
Do not rebuild `tool_calls`. A 400 that names `thought_signature` is the
only reason to touch that append.

## Skeleton

**Keep the loop. The client reads the active record.**

1. Keep: tools, `SYSTEM`, message flow, separators. Do not touch `SANDBOX`
   or flip the default to cwd. Do not bring Tok/s or summed `total_tokens`
   back.
2. `_SERVERS` is `(id_env, key_env, base)`. Skip a server whose id env is
   unset. The record field is `api_key`, and its value is the env name, not
   the secret.
3. `default_id` is read once from `GEMINI_MODEL`. `active["id"]` starts
   there. `/model` may change it for the session. Restart restores
   `default_id`.
4. One `chat.completions.create`, via `with_raw_response`. Append the raw
   message dict. A raised call returns `Model Error:`. It must not kill
   the REPL.
5. `__main__.py` handles `/model` and `/model <id>` before appending a user
   message, same as `exit`. Never sent to the model.
6. Status shows `active["id"]`. Context `%` is appended only when
   `context_window` is set. Elapsed is `_elapsed`, not `{elapsed:.1f}s`.

## Segment 1 — Record + registry

File: `src/minicode/agent.py`. `active` is a dict so `main()` can reassign
the id without a `global` statement — same pattern as `last_usage`.

```python
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
```

`context_window` stays `None` until you have verified the number for that
exact model id. Do not invent one. Cost stays zeros and is not printed.
`tools: True` is recorded, not acted on. `max_tokens` is stored and not
passed to `create`.

An empty `OLLAMA_MODEL` skips that server. `/model` lists only what was
set at startup. The Ollama id must match a local tag. The layer is done
even if Ollama is not installed. A later turn that calls it may fail on
the network. That failure is `Model Error:`, not a dead REPL.

Do not hardcode an id in Python. Do not put the catalog in `.env`.

`__main__.py` imports `active` and `MODELS`:

```python
from minicode.agent import agent, TOOLS, last_usage, SYSTEM, active, MODELS
```

## Segment 2 — One create site

File: `src/minicode/agent.py`. Read `record` once per turn, before the step
loop, so a `/model` between turns is picked up and a switch mid-turn cannot
happen. Dispatch with `call["function"]["name"]`, not attribute access.

```python
def agent(messages: list) -> str:
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
        try:
            raw = client.with_raw_response.chat.completions.create(
                model=record["id"],
                messages=messages,
                tools=SCHEMAS,
            )
            body = json.loads(raw.text)
        except Exception as exc:
            return f"Model Error: {exc}"
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

Overwrite `prompt_tokens`. Do not sum it. That last prompt is `In`. Summed
`completion_tokens` is `Out`. Neither is a Tok/s.

The dummy `"ollama"` is only for an empty key on a loopback base. A missing
Gemini key must still fail. Do not pass `max_tokens`. Do not `model_dump`
the assistant message. Do not rebuild `tool_calls`.

## Segment 3 — `/model`

File: `src/minicode/__main__.py`, in `main()`, after the empty-line
`continue` and before `messages.append`. Same rule as `exit`: handled
locally, never sent to the model. The space after `/model` is required.
`/models` is not this command.

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
            print(f"Unknown Model: {chosen}")
        else:
            active["id"] = chosen
            print(f"Model: {active['id']}")
    continue
```

Unknown id prints an error and does not switch. `/model` with no argument
lists every id loaded at startup and marks the active one. It does not add
a model. It does not edit `.env`. Restart restores `default_id`.

## Segment 4 — Status line

File: `src/minicode/__main__.py`. Print `active["id"]`. Append context `%`
only when `context_window` is set:

```python
window = MODELS[active["id"]]["context_window"]
ctx = f" | {prompt_tokens / window:.1%} context" if window else ""
```

```python
print(
    f"---"
    f"\nModel: {active['id']} | Mode: {MODE} | Tools Loaded: {', '.join(TOOLS)}"
    f"\nSandbox: {SANDBOX}"
    f"\n{prompt_tokens:,} In | {out_tokens:,} Out | Elapsed: {_elapsed(elapsed)}{ctx}\n"
    f"---"
)
```

No cost. No fake percent. No Tok/s. Startup `Sandbox:` line stays.

## Your finished modules

`agent.py` holds `_SERVERS`, `_entry`, `MODELS`, `default_id`, `active`,
and the one `chat.completions.create`. `__main__.py` holds `/model` and the
status id. Still no TOML. Still no new package dirs. Still no
thought-signature parser.

## Don't add yet

models.dev import, `/connect`, variants, streaming, fallbacks,
thinking-trace conversion, a signature parser, shell, grep, plan/build,
flipping the sandbox default to cwd, a third server, passing `max_tokens`,
a cost line, Tok/s, LiteLLM, one SDK per provider, a hardcoded model id,
putting the catalog in `.env`.

If `/model` lists the ids that were set at startup, an unknown id does not
switch, the next real turn uses the active record's `model` / key /
`base_url`, a down local endpoint returns `Model Error:`, a `read` then
`edit` turn finishes, and the status id matches — stop.

## Checkpoint

1. Where does the active id get read, and how many create sites are there?
2. What happens to `/model` — is it appended, sent to the model, or neither?
3. What happens on an unknown id? On a create exception?
4. Why is context `%` not a summed token count divided by `context_window`?
5. Why is the Ollama id not a Python constant?
6. Why must this layer not change `SANDBOX`?
7. Where does a Gemini thought signature live, and what code parses it?

Answers: (1) `MODELS[active["id"]]` once per `agent` turn, in `agent.py`;
one `chat.completions.create` site; (2) neither — `__main__.py` handles it
and `continue`s, same as `exit`; (3) print `Unknown Model: …` and keep the
current id; a raised create returns `Model Error: …`; (4) `In` is the last
call's `prompt_tokens`, not a sum — skip the `%` when `context_window` is
`None`; (5) the id is `OLLAMA_MODEL` from `.env`; the code holds the base
URL, not the tag; (6) `sandbox/` is the dev fence so tool tests cannot
touch harness source — product cwd is a later flip, not a registry change;
(7) it rides in the raw assistant message dict if the server sent it; no
code parses it.
