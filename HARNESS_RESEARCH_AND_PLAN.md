# MiniCode — Research, Decisions, and Build Plan

**What this is:** a small, reliable coding agent harness in Python. Built to be
understood end-to-end. Few features, each finished.

**Non-goal:** feature parity with OpenCode, Pi, or anything else. Completion of
whatever features exist beats breadth.

**Target:** a stable minimum that handles real coding tasks — loop that never
dies, `read` / `write` / `edit` inside a sandbox, separate plan and build
modes, swappable models, and enough observability to see what is happening.
Not a demo loop, not a product.

---

## 1. The loop

One shape, no doubles:

```
REPL appends the user message once
run_agent:
  msg = completion(messages, tools)
  append the assistant message        # always, once
  if no tool_calls:
    return msg text
  for each call:
    result = run the tool             # never raises out
    append one role:"tool" message    # once per call, same tool_call_id
  repeat
max_steps reached:
  return a message the user can act on (never raise)
```

`exit` / `quit` leave before any `completion()` call. The REPL owns the user
message; `run_agent` never appends it again. One `completion()` site in the
whole codebase.

This is the same shape as Pi, Claude Code, Codex, and OpenCode: prompt →
model → tool calls → results → repeat. One node with a self-loop, not a graph.
LangGraph is for genuine branching (supervisor routing between distinct
nodes). It would be abstraction tax on a `while` loop.

`deepagents` is the thing being built here (planning tool, filesystem,
subagents, HITL, skills, compaction). It stays a **capability checklist**,
never a dependency, until the hand-built loop is fully owned. Whether to adopt
it later for delegation machinery — or keep building by hand — is decided then,
on control vs convenience. Not now.

LlamaIndex `FunctionAgent` hides `tool_calls`, the `role: "tool"` message, the
loop, and the stop condition. Steering, abort, compaction, and cost tracking
cannot be added through it.

---

## 2. Decisions

| Topic | Call |
|---|---|
| Loop | Hand-written, sync, LiteLLM `completion()` |
| LiteLLM | Transport only. We own the model registry |
| Tools | Own `tool_from_fn`: Google-style docstring + type hints → schema + `pydantic.create_model` validation |
| Errors | Tool failures and `ValidationError` return as `role: "tool"` content so the model self-corrects |
| `max_steps` | Return a usable message. Never raise (raising kills the REPL) |
| Prompt | ~4 sentences + tool list. Prompt + schemas under ~1000 tokens |
| Workspace | Sandbox directory. Tools cannot leave it in v0 |
| Modes | Plan and build are **separate** (§6) |
| Permissions | YOLO inside the sandbox for now. Allow/ask/deny later (§5) |
| UI | `input()` REPL + tool line + status block per turn (§7) |
| Layout | `src/minicode/`, growing from one module (§8) |
| Sync vs async | Sync until abort/streaming is actually needed |
| Tests | After `tool_from_fn` exists — the schema compiler is the first thing worth testing without an API key |

---

## 3. Providers and models

Free-tier Gemini is rate-limited for long agentic loops. Zen-style gateways and
local models exist for exactly that reason. The fix is structural: never store
just a model *string*. Own a **Model record** that turns a definition into
whatever `completion()` needs.

OpenCode's shape, adapted:

- Model ids look like `provider/model` (`gemini/gemini-3.5-flash-lite`,
  `ollama_chat/qwen3-coder`, `openai/<id>` with a custom `api_base`).
- Credentials live in env (later a `0600` auth file). Never in the model
  config that gets committed.
- A custom provider is `api_base` + key + model map. Zen is just another entry
  (`https://opencode.ai/zen/v1/...` + key). Ollama is
  `http://127.0.0.1:11434/v1`. llama.cpp is its `/v1` endpoint.
- Switching models mid-session changes the next `completion(model=...)` call.
  History stays as Chat Completions messages, which LiteLLM already
  normalizes across providers.

LiteLLM is **not** the limit here — it already speaks Gemini, Ollama
(`ollama_chat/` prefix for `/api/chat` + tool calling), any OpenAI-compatible
endpoint (`openai/<name>` + `api_base`), OpenRouter, Anthropic, and more. What
LiteLLM does not give you is the product layer: a typed catalogue, context
windows, pricing, cache flags, `/connect`, `/models`. The Model record is that
layer, built to the size actually needed:

```
id, provider, api_base (optional), api_key_env,
context_window, max_tokens,
cost {input, output, cache_read, cache_write} (0 for local),
capabilities {tools, caching}
```

Start with 2–3 entries in a dict (later TOML). Adding Zen later is one entry,
not a new loop. No models.dev scrape, no 75 providers, no OAuth in v0.

**Day one:** Gemini via `.env` (`GEMINI_MODEL`, `GEMINI_API_KEY`).
**Layer 2:** registry + `/model` + status line shows the active id. Prove the
shape with one OpenAI-compatible endpoint (Ollama or llama.cpp alongside
Gemini).

**Caching — planned, not faked:**

- Cloud: LiteLLM already surfaces cache-read tokens in `usage` where the
  provider supports it. Anthropic needs explicit cache breakpoints (system
  prompt + last stable prefix); Gemini/OpenAI are mostly automatic. No custom
  cache code until a second provider actually needs it.
- Local (Ollama / llama.cpp): prefix KV-cache hits require the **prompt
  prefix to stay byte-identical**. Do not shuffle old messages, and do not
  compact by rewriting history, until this is understood. Stability of the
  prefix is a correctness property, not an optimization.

---

## 4. Tools

`tool_from_fn` compiles an ordinary function into everything the loop needs:

```python
def add(a: float, b: float) -> float:
    """Add two numbers and return the sum.

    Args:
        a: First addend
        b: Second addend
    """
    return a + b
```

Google-style docstrings (the AgenticRoadmap convention). First line →
description. `Args:` entries → parameter descriptions. `inspect.signature` +
`get_type_hints` → JSON types. `pydantic.create_model` (approved from day
one) → schema and validation in one step. Bad JSON from the model becomes a
`ValidationError` string returned as tool output, never an exception out of
the loop.

Do not use `litellm.utils.function_to_dict` (numpy-docstring-specific, not
this convention). Do not hand-maintain an `if/elif` dispatch chain forever —
the registry (`name → {schema, fn}`) replaces it once the second tool lands.

**v0 tools (no shell):** `read`, then `write`, `edit`. Shell (PowerShell on
this machine) arrives after file tools are boring — it is needed for tests and
git, which is what makes the harness real, but it is also the largest safety
hole, so it waits its turn.

**`read(path, offset=1, limit=2000)`.** Offset is 1 because files and editors
are 1-indexed: `offset=1` is the first line, and omitting it starts at the
top. `limit=2000` caps how much of a huge file enters the context (same as
Pi). Output is line-numbered text. Missing files and arithmetic errors return
as strings.

**`write(path, content)`** — new files or full rewrites. Creates parents.
**`edit(path, old_text, new_text)`** — exact match only. Fail as a tool error
on 0 or >1 matches. Line numbers drift as files change; exact text is the
stable handle.

---

## 5. Sandbox and permissions

Product workspace is the launch directory, like Pi and OpenCode: cwd, or
`--sandbox path`. `read` / `write` / `edit` resolve every path against it
and **reject** escapes (`..`, absolute paths outside). `.env` files stay
denied even inside the sandbox.

The code's current default is a root `sandbox/` dir, not cwd. That is the
dev fence while the harness is being built, so tool tests cannot overwrite
`src/`. It is not the product rule. A real repo today is
`--sandbox <that repo>`. Flipping the default to cwd is its own later pass,
after file tools are boring — not part of the model registry.

YOLO is fine inside that box for now. Pi's argument stands: once an agent can
write and run code, permission prompts are mostly theater — but the sandbox
still bounds *where* files land, which is the accident class that matters
first.

Later, researched as needed (OpenCode's model): `allow` / `ask` / `deny` per
tool, glob rules with last-match-wins, and an `external_directory` gate so
reads outside the sandbox (Desktop, other checkouts) ask first instead of
being silently allowed or silently impossible. That is how OpenCode navigates
outside the project safely. Containerization stays the real boundary for
untrusted work.

---

## 6. Plan vs build — separate, and what Pi's `PLAN.md` actually is

You know OpenCode's version: two primary agents, Tab to switch. **Plan** runs
with edits and bash restricted (`ask`/`deny`) — analysis, no silent writes.
**Build** has the full toolset. Same session, same files. The guarantee is the
**tool list / permission**, not a prompt asking nicely. MiniCode implements
that: plan mode drops `write` / `edit` (later `shell`) from `tools=`.
`/plan` and `/build` switch, and the status line shows which is active.

Pi's `PLAN.md` is a different, smaller thing — worth understanding because it
is useful *inside* either mode, but it is not a mode:

1. You tell the agent: think with me, do not touch code.
2. Optionally you restrict tools for that session (`--tools read,...`).
3. The agent uses `write` to create a `PLAN.md` in the repo: goal, approach,
   steps, current step.
4. Nothing auto-approves or auto-deletes it. **You** read and edit the file,
   collaboratively, in the open. Then you say "implement PLAN.md".
5. The file persists and versions with git. Next session can reuse it.

No approval gate, no lifecycle — a markdown convention with full
observability, as opposed to Claude Code's black-box plan subagent. MiniCode
can adopt the convention (an agent-written plan file during plan mode) without
making it the mechanism. The mechanism stays the restricted tool list.

v0 may ship build-only until `write` / `edit` exist. Plan mode without
anything to restrict is theater.

---

## 7. Observability — early, in the REPL

No TUI yet. After a successful tool run, one line:

```
Tool: `read` executed
```

Print **after** the tool returns, not before. Unknown tools stay silent on
stdout. After the model's reply, a status block:

```
---
Model: gemini/gemini-3.5-flash-lite | Mode: build | Tools: read
1,204 Tokens | 152.8776 Tok/s
---
```

| Now (Layer 0) | Next | Later |
|---|---|---|
| Active model id | Context % (`usage` totals ÷ `context_window`) | Cost (needs pricing on the Model record) |
| Mode | Prompt-cache hits when `usage` reports cache tokens | Diff **viewer** UI |
| Enabled tool names | | Sessions / resume |
| Tokens this turn (sum of `resp.usage.total_tokens` across steps) | | |
| Tok/s (turn tokens / wall clock of `run_agent`; 0 if elapsed is 0) | | |

Reset `last_usage` at the start of each turn and add each step — a read is
two `completion()` calls. LiteLLM `usage` is enough for Gemini token counts —
no tiktoken needed. Cost and cache-hit display wait for the Model registry to
carry pricing and cache flags. Edit diffs: a short unified-diff print in the
REPL when `edit` lands is useful for testing and is not a viewer; the viewer
itself is deferred. The numbered body of `read` is `role: "tool"` content;
Gemini may quote it or summarize.

---

## 8. Layout

```
src/minicode/          # the harness; starts as one growing module
docs/                  # setup + build guides + STATUS
AGENTS.md              # session start
HARNESS_RESEARCH_AND_PLAN.md  # this file
.env.example
```

`src/minicode` looks professional and splits without rewrites: start with the
whole loop in `__main__.py` (REPL + loop + `tool_from_fn` + `read`), split
into `loop.py` / `tools.py` only when the file is hard to hold in your head.
Same functions either way. Rule that survives the split: the loop owns
dispatch; tools never import the LLM; a future UI is never imported by the
loop.

Docs follow the AgenticRoadmap shape (guide first, then the `.py` from it),
as a product spine rather than a course: `docs/STATUS.md` (done / next),
`docs/00-setup.md`, one build guide per layer. `tests/` arrives with
`tool_from_fn`. `README.md` when the REPL actually runs. No `plans/` dump, no
empty package scaffolding.

---

## 9. Layers

**Layer 0 — loop + sandbox + `read` + status.**
Fix the five raw-loop bugs (`user_input = str`, unused `user_text`, `exit`
sent to the model, `max_steps` raising, unbounded history — note it, don't
build compaction). `tool_from_fn`. Sandbox. `read`. Tool line + status block.
REPL that exits cleanly.
Checkpoint: a session that reads a file, prints `Tool: `read` executed` on
a successful call, survives bad tool args, shows model/mode/tools/tokens/Tok/s,
and exits without sending `"exit"` to Gemini.

**Layer 1 — `write` + `edit`.** Exact-match `edit`. Optional one-shot diff
print. Still no shell.
Checkpoint: the agent edits a local file correctly; a mismatched `old_text`
returns a tool error and the model retries.

**Layer 2 — model registry.** Model records, `/model` mid-session switch,
Gemini + one OpenAI-compatible endpoint to prove the shape.
Checkpoint: `/model` to another entry, next turn uses it, status shows it.

**Then, for real work (order may slip):** flip the default workspace from
the dev `sandbox/` fence to launch cwd → one capped search tool (`grep` or
`find`, not a shell) → plan/build via tool-list swap → `shell` →
permissions (`ask`/`deny`, `external_directory`) → streaming + Ctrl+C that
leaves a coherent session → sessions/resume → cache control → cost → diff
viewer → `AGENTS.md` injection into the system prompt. Search before shell:
`read` of a known path cannot find anything in a large tree, and shell is
still the safety hole.

---

## 10. Deferred until the gap hurts

Subagents, MCP, skills, LSP, LangGraph, LlamaIndex, RAG/Chroma, background
bash, models.dev bulk import, Rich/Textual, web UI, compaction, JSONL session
tree, granular approvals. Each gets promoted only after the missing piece is
felt — and every promotion must leave the harness as finished as it was
before.

---

## 11. Reliability rules

- Tool code never raises out of the loop.
- Unknown tool name → string, not crash.
- Paths outside the sandbox → string error.
- One `completion()` site. Provider quirks stay in LiteLLM.
- No invisible behavior. Config is env first; every key inspectable later.
- Secrets never in committed config.

---

## 12. Stack

Python ≥3.13, **uv**, `litellm`, `pydantic`, `python-dotenv`.
Not: LangGraph, LangChain, deepagents, LlamaIndex, Rich, pi-agent-core.

## 13. Sources

- Mario Zechner, "What I learned building an opinionated and minimal coding
  agent" and "What if you don't need MCP at all" (mariozechner.at) — four
  tools, tiny prompt, files-not-features, no MCP/subagents/background-bash.
- Pi docs (pi.dev): sessions, compaction, session format.
- OpenCode docs: providers, Zen, config, models, agents (plan/build),
  permissions (`allow`/`ask`/`deny`, `external_directory`).
- LiteLLM docs: function calling, Ollama (`ollama_chat/`), OpenAI-compatible
  endpoints.
- AgenticRoadmap (`docs/`, `AGENTS.md`, Phase 2 raw loop) — docs-first,
  growing-file guide structure.
- Armin Ronacher, "Agent Design Is Still Hard" — own the loop, reinforcement
  and failure isolation notes.
