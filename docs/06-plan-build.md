# 06 — Plan/build swap (tool-list swap)

Do first: `docs/05-search.md`. Layer 4 is done. This layer is implemented
in `agent.py` and `__main__.py`. Shipped names have no leading underscore.
Do not rename them.

Registry, loop, `SYSTEM`, and the one `chat.completions.create` site live in
`agent.py`. `/plan`, `/build`, `/model`, and the status print live in
`__main__.py`. `tool_from_fn` stays in `schema_generator.py`. Sandbox stays
in `resolve_path.py`. A new tool is `tools/<name>.py` plus one registry line
in `agent.py`. Do not grow `__main__.py` with the loop.

## What you'll build

Layer 5: two modes on one session, one history. `build` keeps the full
registry (`read,write,edit,glob,grep`). `plan` drops `write`/`edit` from
`tools=` so the model cannot propose them, and denies them at dispatch if
it tries anyway. `/plan` and `/build` switch. Status shows the mode.
Startup default is `plan`. Restart restores `plan`.

## Why it matters

The guarantee is the **tool list**, not a prompt asking nicely. That is
OpenCode's shape (plan runs with edits restricted, build has the full
toolset, same session) minus the second agent: one `agent`, two `tools=`
views. Pi's `PLAN.md` file is a separate convention (an agent-written plan
file you edit together) — useful inside either mode, but it is not the
mechanism. This layer is the mechanism only. No `PLAN.md` file, no approval
gate, no lifecycle.

## Skeleton

**Keep the loop. Keep the registry. Swap the view.**

1. Keep: tools, `SYSTEM`, message flow, `_resolve`, `.env` denial, escape
   error, tool line `|Tools Used: \`name\` ({args})|`, status block
   `{prompt:,} In | {out:,} Out | {session:,} Session | Elapsed: {_elapsed(elapsed)}`. No Tok/s.
2. Add: `agent.py` keeps `mode = {"name": "plan"}` (same dict pattern as
   `active` and `last_usage` so `main()` reassigns without `global`),
   `PLAN_DENIED`, `PLAN_SYSTEM`, `active_schemas()`, `active_names()`.
3. Replace: `agent` reads the record once per turn (keep), then passes
   `tools=active_schemas()` to the one `chat.completions.create`, and
   denies `PLAN_DENIED` at dispatch even if the model guesses the name.
4. Replace: `__main__.py` drops the local `MODE` constant, imports `mode`,
   handles `/plan` / `/build` before appending a user message (same rule
   as `exit` and `/model`: handled locally, never sent to the model),
   swaps `messages[0]["content"]`, prints `Mode: {mode["name"]}`.
5. Replace: status prints `Mode: {mode["name"]}` and
   `Tools Loaded: {', '.join(active_names())}` so the restriction is
   visible. Do not touch `SANDBOX`, `_SERVERS`, `default_id`, or
   `tool_from_fn`.
6. Do not rewrite history on a mode switch. Old assistant dicts stay as-is
   (prefix stability). Only `messages[0]` changes going forward.

## Segment 1 — Mode state + denied set + plan prompt

File: `src/minicode/agent.py`. Keep `SYSTEM`, `TOOLS`, `SCHEMAS`,
`MODELS`, `active`, `last_usage`. Add this below `SYSTEM`:

```python
mode = {"name": "plan"}

PLAN_DENIED = ("write", "edit")

PLAN_SYSTEM = (
    "You are in plan mode. Read, search, and reason. "
    "Do not create or modify files. Propose steps and wait for approval. "
    "Never name internal tools. Speak in user actions: 'I will edit...', 'I checked...', not 'Use edit/glob/grep'. "
    "Propose file + change + reason. To build, the user runs /build. "
    "After `glob` returns, read every matching file in that same response. Do not read one file per turn."
)
```

`mode` starts `"plan"`, so a new session cannot use `write` or `edit` until `/build`.
`PLAN_DENIED` is the whole guarantee: `docs/07-shell.md` adds `bash` and
`powershell` to this tuple. Do not add them from this file. Nothing else
changes. `PLAN_SYSTEM` is a separate sentence block. Do not
concatenate it onto the `write`/`edit` routing rule and do not edit
per-tool docstrings (only the first docstring line reaches the model).
`MAX_STEPS` is `16`. Do not raise it per mode. The only batching sentence
is the plan-mode read-after-`glob` line. Do not add one to `SYSTEM`.

Helpers in the same file:

```python
def active_schemas() -> list:
    """Return the schemas for the current mode."""
    if mode["name"] != "plan":
        return SCHEMAS
    return [s for s in SCHEMAS if s["function"]["name"] not in PLAN_DENIED]


def active_names() -> list[str]:
    """Return the tool names for the current mode."""
    if mode["name"] != "plan":
        return list(TOOLS)
    return [n for n in TOOLS if n not in PLAN_DENIED]
```

No new package dirs. No new deps. No `if/elif` chain on tool names.

## Segment 2 — One create site, filtered view + dispatch deny

File: `src/minicode/agent.py`. Replace `agent` with this. Full body:

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
                tools=active_schemas(),
            )
            body = json.loads(raw.text)
        except Exception as exc:
            return f"Model Error: {exc}"
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
            if mode["name"] == "plan" and name in PLAN_DENIED:
                content = f"Plan mode: `{name}` is disabled. Propose the change and ask to run /build."
            else:
                run = TOOLS.get(name)
                if run:
                    args = call["function"]["arguments"]
                    content = run(args)
                    print(f"\n|Tools Used: `{name}` ({args})|\n")
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

What this locks:

- `tools=active_schemas()` is the restriction the model sees. In `plan`
  the model never receives `write`/`edit` schemas, so it cannot call them
  by discovery.
- The `mode["name"] == "plan"` dispatch check is the backstop: a guessed
  name, a stale history replay, or a cached reply still returns a
  `role: "tool"` string, never a write. Tool code never raises out of the
  loop. Unknown tools stay silent on stdout (no `|Tools Used:|` line).
- `last_usage` still overwrites `prompt_tokens` (`In`) and sums
  `completion_tokens` (`Out`). Still one `chat.completions.create` site.
  Still no `max_tokens`, no `model_dump`, no thought-signature parser.

## Segment 3 — `/plan` / `/build` + system swap + status

File: `src/minicode/__main__.py`. Keep the loop, `/model`, `exit`,
`Sandbox: {SANDBOX}` startup print, `In | Out | Session | Elapsed: {_elapsed}`.
No Tok/s.

Replace the import line:

```python
from minicode.agent import agent, TOOLS, last_usage, SYSTEM, PLAN_SYSTEM, active, MODELS, mode, active_names
```

Delete the local `MODE` constant. `mode` in `agent.py` is the state.

Full body of `main` after the change:

```python
def main() -> None:
    print(f"Sandbox: {SANDBOX}")
    print(f"\nMode: {mode['name']} | Tools Loaded: {', '.join(active_names())}\n")
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
        stripped = text.strip()
        if stripped == "/plan" or stripped == "/build":
            want = stripped[1:]
            if mode["name"] != want:
                mode["name"] = want
                if want == "plan":
                    messages[0]["content"] = SYSTEM + " " + PLAN_SYSTEM
                else:
                    messages[0]["content"] = SYSTEM
            print(f"\nMode: {mode['name']} | Tools Loaded: {', '.join(active_names())}\n")
            continue
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
        messages.append({"role": "user", "content": text})  # once, here only
        start_time = time.perf_counter()
        answer = agent(messages)
        elapsed = time.perf_counter() - start_time
        prompt_tokens = last_usage["prompt_tokens"]
        out_tokens = last_usage["completion_tokens"]
        print(f"\nminicode >> {answer}\n")
        window = MODELS[active["id"]]["context_window"]
        ctx = f" | {prompt_tokens / window:.1%} context" if window else ""
        print(
            f"---"
            f"\nModel: {active['id']} | Mode: {mode['name']} | Tools Loaded: {', '.join(active_names())}"
            f"\nSandbox: {SANDBOX}"
            f"\n{prompt_tokens:,} In | {out_tokens:,} Out | {session_tokens:,} Session | Elapsed: {_elapsed(elapsed)}{ctx}\n"
            f"---"
        )
```

What this locks:

- `/plan` / `/build` are exact matches only. `/plans` is not this command.
  Handled before `messages.append`, same as `exit` and `/model` — never
  appended, never sent to the model.
- Idempotent: switching to the current mode just prints `Mode: …` and
  `Tools Loaded:` and does not double-append `PLAN_SYSTEM`.
- `messages[0]` swap only affects future creates. History is not rewritten.
- Status `Tools Loaded:` is `active_names()`: `read,glob,grep` in plan,
  `read,write,edit,glob,grep` in build. That is how the restriction is
  observed.

## Segment 4 — Commands

From the launch dir (product):

```powershell
uv run python -m minicode
```

```text
Mode: plan | Tools Loaded: read, glob, grep
user >> add retries to agent.py
minicode >> I found the loop in agent.py:12: def agent... Propose: 1) ... Run /build to apply.
---
Model: gemini-3.5-flash-lite | Mode: plan | Tools Loaded: read, glob, grep
Sandbox: C:\Users\hp\Desktop\PyCharm Projects\MiniCode
398 In | 12 Out | 12 Session | Elapsed: 1.7s
---
user >> /build
Mode: build | Tools Loaded: read, write, edit, glob, grep
```

**Expected:** startup prints `Mode: plan` and
`Tools Loaded: read, glob, grep`. Asking for an edit in plan proposes
steps, prints
`|Tools Used: \`read\||` / `|Tools Used: \`grep\||` on success, and never
prints `|Tools Used: \`write\||` or `|Tools Used: \`edit\||`. A guessed
`write`/`edit` call returns `Plan mode: … is disabled` as `role: "tool"`
content. `user >> /build` restores full tools with no restart. `/model`
still lists/switches ids. `exit` still leaves before any create.

## Your finished modules

`agent.py` holds `mode`, `PLAN_DENIED`, `PLAN_SYSTEM`,
`active_schemas()`, `active_names()`, and the one filtered create site.
`__main__.py` holds `/plan` / `/build`, the `messages[0]` swap, and the
`Mode:` / `Tools Loaded:` status. Shell and permissions are later layers.
Live plan keeps `bash` / `powershell` and asks. No
`PLAN.md` convention, no new package dirs.

## Open gaps at this layer

- Plan hides `write` / `edit` only. Shell stays in the tool list and asks.
- Cost display is deferred until more models are added.

## Don't add yet

Shell, allow/ask/deny, `external_directory` gate, streaming, sessions,
compaction, cost display, diff viewer, `PLAN.md` file lifecycle, models.dev
import, `/connect`, variants, passing `max_tokens`, Tok/s. If plan proposes
without writing, build writes, the switch needs no restart, and the status
tells which is active — stop.

## Checkpoint

1. Where does the mode live, and which file must not own a copy of it?
2. What does the model see of `write`/`edit` in plan — and where is that enforced?
3. What happens if the model guesses `write` in plan? Does a file change?
4. What happens to `/plan` — appended, sent, or neither? What about history?
5. What does `Tools Loaded:` show in each mode — and which function builds it?
6. Why is there no `PLAN.md` file in this layer?
7. Why must this layer not change `SANDBOX` or add a tool?

Answers: (1) `mode = {"name": "plan"}` in `agent.py`; `__main__.py`
imports it — no `MODE =` copy; (2) nothing — `tools=active_schemas()`
omits them, backstopped by the dispatch deny; (3) a `role: "tool"` string
`Plan mode: … is disabled`, file untouched, model re-plans; (4) neither —
handled locally and `continue`s like `exit`; only `messages[0]` is swapped,
history is never rewritten; (5) `active_names()`: `read,glob,grep` in plan,
full list in build; (6) the file is a collaboration convention inside either
mode, not the restriction mechanism — the mechanism is the tool list;
(7) the swap is a view change, not a root or registry change — one finished
layer at a time.
