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
agent:
  msg = chat.completions.create(messages, tools)
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

`exit` / `quit` / `bye` leave before any `chat.completions.create` call. The
REPL owns the user message; `agent` never appends it again. One
`chat.completions.create` site in the whole codebase. The function is
`agent` in `agent.py`, not `run_agent`. The assistant message appended is
the raw JSON object from the response body, not an SDK object and not a
rebuilt `tool_calls` list.

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
loop, and the stop condition. Steering, abort, compaction, and cost display
cannot be added through it.

---

## 2. Decisions

| Topic | Call |
|---|---|
| Loop | Hand-written, sync, OpenAI `chat.completions.create` |
| Transport | `openai` package. `base_url` selects the server. We own the registry |
| Tools | Own `tool_from_fn`: Google-style docstring + type hints → schema + `pydantic.create_model` validation |
| Errors | Tool failures and `ValidationError` return as `role: "tool"` content so the model self-corrects |
| `max_steps` | Return a usable message. Never raise (raising kills the REPL) |
| Prompt | ~4 sentences + tool list. Prompt + schemas under ~1000 tokens |
| Workspace | Launch cwd, or `--sandbox path`. Outside paths ask `external_directory` (§5) |
| Modes | Plan and build are **separate** (§6) |
| Permissions | Implemented: `allow` / `ask` / `deny`, last matching rule wins (§5) |
| UI | `input()` REPL + tool line + status block per turn (§7) |
| Layout | `src/minicode/`, growing from one module (§8) |
| Sync vs async | Sync. Streaming, abort, conditional reasoning labels, and the final-answer-only prefix are implemented (`docs/09-streaming.md`). Stay sync |
| Tests | Not written. Planned after `tool_from_fn`; still open |
| Cost | Deferred until more models are added; then needs pricing on the Model record |

---

## 3. Providers and models

Free-tier Gemini is rate-limited for long agentic loops. Zen-style gateways and
local models exist for exactly that reason. The fix is structural: never store
just a model *string*. Own a **Model record** that turns a definition into
the kwargs `chat.completions.create` needs.

OpenCode's shape, adapted, without the catalog:

- The id is the server's id, from `.env` (`GEMINI_MODEL`, `OLLAMA_MODEL`).
  No `provider/` prefix. No hardcoded tag. The base URL selects the server.
- Credentials live in env. Later, a `0600` auth file in the user data dir
  (OpenCode: `~/.local/share/opencode/auth.json`). Not the project `.env`.
  Never in the model record. `api_key` stays the env name. Lookup stays
  `os.getenv`.
- A provider is `api_base` + key + id. Gemini's base is
  `https://generativelanguage.googleapis.com/v1beta/openai/`. Ollama is
  `http://127.0.0.1:11434/v1`. Groq is `https://api.groq.com/openai/v1`.
  llama.cpp is its `/v1` endpoint. A later entry is one `_SERVERS` tuple
  plus two env lines, not a new client. Do not add an OpenCode Console free
  model. Since 18 September 2026 the free tier returns `403 FreeTierError`
  unless the caller is the official client. A maintainer said that limit is
  the free tier only. Do not fake client headers. A paid chat-completions
  id is still one tuple if asked. It is not the free backup.
- Switching models mid-session changes the next create's `model` and
  `base_url`. History stays Chat Completions dicts: the raw assistant
  message from the response JSON, or the plain dict rebuilt from
  `chunk.to_dict()` in the streaming loop, so extra fields round-trip. A
  Gemini thought signature rides in that dict. Do not parse it. Preserve
  `extra_content`. Do not invent a signature.

The `openai` package is the transport, not a provider catalog. What it does
not give you is the product layer: a typed catalogue, context windows,
cache flags, `/connect`, `/models`. Pricing waits for cost display. The Model
record is that layer, built to the size actually needed:

```
id, api_base, api_key,
context_window, max_tokens,
cost {input, output, cache_read, cache_write} (0 for local),
capabilities {tools, caching}
```

Cost fields stay zero and are not printed. Cost display is deferred until
more models are added.

`api_key` holds the env name, not the secret. `api_base` is required.
Servers are a `_SERVERS` tuple, not a catalog in `.env`. No models.dev
scrape, no 75 providers, no OAuth yet, no LiteLLM, no SDK per brand.
`/connect` waits with that catalog. It is not a key-writer on `_SERVERS`,
and a name→base dict does not remove the tuple-plus-two-env-lines edit
until a command looks the name up. `/model` lists ids from `.env` only.
Fetching the list and context is `/models`. Cost is deferred until more
models are added. Variants are reasoning effort (`high`, `max`). They are
not a flag on the current create call.
Ollama local is a base URL, not a login.

The catalog phase adds one field, not a client per brand. The tuple becomes
`(id_env, key_env, base, transport)`. `agent()` keeps one call site. One
function, the same idea as `tool_from_fn`, picks the body from the tag.
Four tags cover the wires: `chat` (today's `chat.completions`: Gemini's
OpenAI URL, Groq, Ollama), `responses` (same `openai` package), `anthropic`
(messages body), `google` (native Gemini; the current Gemini base does not
need it). No installed SDK per brand. Console free ids are not an example.
They are refused outside the official client.

OAuth is not a fifth tag. `/connect` pastes a key or runs a browser login,
then writes a bearer token to the user auth file, mode `0600`. OpenCode
does this for ChatGPT Plus. A Grok subscription is that same kind of login,
not a new server. The record still holds a name, not the secret. Lookup
stays one function. An API key and a login both end as that token. Do not
build the tag or `/connect` in the permissions guide.
Do not add Groq until asked. When asked, it is one tuple plus two env lines,
not a registry redesign.

**Day one:** Gemini via `.env` (`GEMINI_MODEL`, `GEMINI_API_KEY`) and the
Gemini base URL on the record.
**Layer 2:** implemented. `_SERVERS` plus `/model`. Startup default is
`default_id` from `GEMINI_MODEL`. `/model <id>` changes `active["id"]` for
the session only. Ollama is the second tuple; its id is `OLLAMA_MODEL`.

**Caching — planned, not faked:**

- Cloud: `usage` may include cache-read tokens where the provider sends them.
  No custom cache code until a second provider actually needs it.
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

Do not hand-write the schema. Do not hand-maintain an `if/elif` dispatch
chain forever — the registry (`name → {schema, fn}`) replaces it once the
second tool lands.

**v0 tools:** `read`, then `write`, `edit`, then capped `glob` /
`grep` (`docs/05-search.md`). Shell is implemented in `docs/07-shell.md`.
One function, resolved once. Windows prefers Git Bash,
then PowerShell. Unix prefers bash, then `sh`. The registered name matches
the winner (`bash` or `powershell`) so the model does not speak bash into
PowerShell. Pi keeps those as two tools and does not fall through. OpenCode
falls through to `cmd.exe` and can launch the WSL shim via `SHELL`. Claude
Code uses PowerShell only when Git Bash is absent; on Linux `pwsh` is an
opt-in, not the missing-bash fallback. MiniCode starts a fresh process in
`SANDBOX`, 120s, 8000-character tail, prints the finished output once, and
denies both names in plan. No `cmd.exe`. No `System32\bash.exe`. No
`workdir`. No timeout parameter. No background process.

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
`--sandbox path`. `read` / `write` / `edit` / `glob` / `grep` accept an
absolute path or a workspace-relative one. An absolute path outside the
workspace is not silently rejected: it triggers `external_directory`.
`.env` and `.env.*` ask on read. `.env.example` does not.

Permissions are implemented (Layer 7, `docs/08-permissions.md`): `allow` /
`ask` / `deny`, last matching rule wins, `*` crosses `/`. Defaults are
`read` / `glob` / `grep` / `edit` allow, `shell` allow except `.env` text,
`external_directory`
ask. `ask` is a REPL prompt (`once` / `always` / `deny`); `always` is
in-memory and exact. No config file, no command scanner, no env scrubbing.
`always` does not outlive the process; that waits with sessions. `glob` and
`grep` return absolute forward-slash paths for a root outside the workspace,
and workspace-relative paths for an inside root.

The default workspace is the launch directory (`_sandbox_root()`:
`Path.cwd().resolve()`, `--sandbox path` overrides it). That is the
product rule. The old default was the root-level `sandbox/` dir — the dev
fence while the harness was being built, so tool tests could not overwrite
`src/`. It is now the dev override:
`uv run python -m minicode --sandbox sandbox`. `sandbox/` is gitignored.

YOLO is fine inside that box for now. Pi's argument stands: once an agent can
write and run code, permission prompts are mostly theater — but the sandbox
still bounds *where* files land, which is the accident class that matters
first.

The permissions guide is `docs/08-permissions.md`, implemented in
`permissions.py`, `agent.py`, and `__main__.py`. OpenCode's actions are
`allow` / `ask` / `deny`, last matching rule wins. Inside the sandbox, reads
and edits allow. `shell` allows ordinary commands. It asks when the text
contains `.env`, and in plan when a piece reads file contents, creates, or
deletes. `external_directory` asks, so a path outside the sandbox is a
prompt instead of a hard error. `.env` reads ask. `always` is exact and
dies with the process. No config file. No scanner. Containerization stays
the real boundary for untrusted work.

---

## 6. Plan vs build — separate, and what Pi's `PLAN.md` actually is

You know OpenCode's version: two primary agents, Tab to switch. **Plan** runs
with edits and bash restricted (`ask`/`deny`) — analysis, no silent writes.
**Build** has the full toolset. Same session, same files. The guarantee is the
**tool list / permission**, not a prompt asking nicely. MiniCode implements
that: plan mode drops `write` / `edit` from `tools=`. `docs/07-shell.md`
adds `bash` and `powershell` to that deny set. That pass is done.
`docs/08-permissions.md` puts both names back in the tool list. The same
plan verb check restricts content-read, create, and delete. It does not force-deny them, and
it is not a stricter prompt. `write` / `edit` stay dropped from the schema.
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
|Tools Used: `read`|
```

Print **after** the tool returns, not before. Unknown tools stay silent on
stdout. After the model's reply, a status block:

```
---
Model: gemini-3.5-flash-lite | Mode: plan | Tools Loaded: read
Sandbox: D:\Pycharm_Projects\MiniCode\sandbox
398 In | 12 Out | 12 Session | Elapsed: 1.7s
---
```

Streaming, abort, conditional reasoning (`Thinking:` only when reasoning
exists; no `Thought:` closer), and the final-answer-only `minicode >>` prefix
with buffered content are implemented per `docs/09-streaming.md`. Reasoning
streams live; content buffers per model step, so the final answer prints
once with the prefix and tool preambles print without it. Gemini asks for
thought summaries; `<thought>` / `<think>` stay display-only. An aborted
stream adds no usage. Do not put `prompt_tokens` into `Session`.

`In` is the last call's `prompt_tokens` (overwrite). `Out` is summed
`completion_tokens` for the turn. `Session` is summed `completion_tokens`
for the process. It is not cleared on `/plan` or `/model`. Do not add
`prompt_tokens` into it. Elapsed is `_elapsed` in `__main__.py`: under 60s
one decimal, then the two largest of `s m h d w y`. A week is 7 days. A year
is 365 days. No months. No Tok/s — a wall-clock rate is
network wait, and summed `total_tokens` counts the prompt once per step.
`AGENTS.md` wins if this section and the REPL ever disagree.

| Now | Next | Later |
|---|---|---|
| Active model id | Context % (last `prompt_tokens` ÷ `context_window`) | Cost — deferred until more models are added |
| Mode | Prompt-cache hits when `usage` reports cache tokens | Diff **viewer** UI |
| Enabled tool names | | Sessions / resume |
| `In` / `Out` / elapsed | | |

The response `usage` object is enough for token counts —
no tiktoken needed. Cache-hit display waits for `usage` to report cache
tokens. Cost is deferred until more models are added; when it lands it needs
pricing on the Model record. Edit diffs: a short unified-diff print in the
REPL when `edit` lands is useful for testing and is not a viewer; the viewer
itself is deferred. The numbered body of `read` is `role: "tool"` content;
Gemini may quote it or summarize.

---

## 8. Layout

```
src/minicode/            # package
  __main__.py            # REPL only
  agent.py               # loop, SYSTEM, registry
  schema_generator.py    # tool_from_fn
  resolve_path.py        # sandbox root + _resolve
  permissions.py         # allow / ask / deny gate
  tools/                 # read, write, edit, glob, grep, shell
docs/                    # setup + build guides + STATUS
AGENTS.md                # session start
HARNESS_RESEARCH_AND_PLAN.md  # this file
README.md                # user guide
.env.example
```

The loop owns dispatch. Tools never import the LLM. A future UI is never
imported by the loop. New guides name the file (`AGENTS.md`). They do not
grow `__main__.py` with the loop.

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
Checkpoint: a session that reads a file, prints `|Tools Used: `read`|` on
a successful call, survives bad tool args, shows model/mode/tools/`In`/`Out`/elapsed,
and exits without sending `"exit"` to Gemini.

**Layer 1 — `write` + `edit`.** Exact-match `edit`. Optional one-shot diff
print. Still no shell.
Checkpoint: the agent edits a local file correctly; a mismatched `old_text`
returns a tool error and the model retries.

**Layer 2 — model registry.** Done. `_SERVERS`, `/model`, OpenAI client.
Ids from `.env`. Bases in code.

**Layer 3 — workspace flip.** Done. `docs/04-workspace.md` implemented.
Default workspace is launch cwd. `--sandbox path` overrides.

**Layer 4 — search.** Done. `docs/05-search.md` implemented in
`tools/glob.py` and `tools/grep.py`.

**Layer 5 — plan/build.** Done. `docs/06-plan-build.md` implemented in
`agent.py` and `__main__.py`. Startup default is `plan`. Plan drops
`write`/`edit` from `tools=` and denies them at dispatch.

**Layer 6 — shell.** Done. `docs/07-shell.md` implemented in
`tools/shell.py` and `agent.py`. Plan denies `bash` and `powershell`.

**Layer 7 — permissions.** Done. `docs/08-permissions.md` implemented in
`permissions.py`, the dispatch gate in `agent.py`, and the prompt in
`__main__.py`. Plan keeps `bash` / `powershell` in the tool list; rules
restrict them, not a stricter prompt.

**Layer 8 — streaming and abort.** Code in the working tree;
`docs/09-streaming.md` is the guide. Conditional reasoning labels
(`Thinking:` only when reasoning exists; no `Thought:` closer) and the
final-answer-only `minicode >>` prefix with buffered content are implemented.
Gemini asks for thought summaries; the tags are stripped before history.
One streamed create, a `chunk.to_dict()` merge that keeps `extra_content`,
and a Ctrl+C that returns to `user >>` with a coherent history. No background
shell. `Session` still excludes prompt tokens.

**Known gaps by phase.** These are open, not new layers.

| Phase | Open gap | Trigger / next |
|---|---|---|
| Layer 0 | `tool_from_fn` and the tools have no tests | Planned after the schema compiler; still open |
| Layer 0 | History is unbounded; no compaction | Deferred until the context gap hurts (§10) |
| Layer 2 | `context_window` is `None`, so context `%` stays off | Set only a verified number |
| Layer 2 | Cache tokens in `usage` are not displayed | Cache control, after sessions |
| Layer 3 | Sandbox is a path boundary, not a container; shell can leave it | Containerization is separate |
| Layer 5 | Plan hides `write`/`edit` only; shell stays and asks | Tool-list restriction, not a shell deny |
| Layer 7 | `always` approvals die with the process | Sessions/resume |
| Layer 7 | No env scrubbing; shell inherits the process environment | Not planned |
| Layer 8 | Content buffers per step; the final answer is not token-streamed | Sessions/resume next |
| After Layer 8 | Sessions/resume, cache control, diff viewer, `AGENTS.md` injection | In that order |
| — | Cost display | Deferred until more models are added |

**Next:** sessions/resume → cache control → diff viewer → `AGENTS.md`
injection into the system prompt.
Cost is not in this chain. It is deferred until more models are added;
when it lands it needs pricing on the Model record.
A shell command can still `cd` out. Permissions asks before the command
runs. It does not parse the command. Do not reorder
abort ahead of permissions. Compaction is the context gap on a real
codebase. It stays deferred until that gap hurts. It is not the next layer.
`/connect` is not in this chain. It waits with the catalog, including the
transport tag and OAuth logins. Variants wait there too.

---

## 10. Deferred until the gap hurts

Subagents, MCP, skills, LSP, LangGraph, LlamaIndex, RAG/Chroma, background
bash, models.dev bulk import, `/connect` (with that catalog; transport tag
on the tuple, not a client per brand; API key or OAuth writes a bearer
token to a user `0600` auth file, not project `.env`; not a key-only
phase), Rich/Textual, web UI,
compaction (the context gap on a real codebase; still not a layer),
JSONL session tree, granular approvals, tests (still not written).
Each gets promoted only after the missing piece is
felt — and every promotion must leave the harness as finished as it was
before.

Cost is deferred for a different reason: do not add it until more models
are added. It then needs pricing on the Model record.

---

## 11. Reliability rules

- Tool code never raises out of the loop.
- Unknown tool name → string, not crash.
- Paths outside the sandbox → string error.
- One `chat.completions.create` site. A new server is `api_base` plus an id,
  not a new client.
- No invisible behavior. Config is env first; every key inspectable later.
- Secrets never in committed config.

---

## 12. Stack

Python ≥3.13, **uv**, `openai`, `pydantic`, `python-dotenv`.
Not: LiteLLM, one installed SDK per brand, LangGraph, LangChain, deepagents,
LlamaIndex, Rich, pi-agent-core.

## 13. Sources

- Mario Zechner, "What I learned building an opinionated and minimal coding
  agent" and "What if you don't need MCP at all" (mariozechner.at) — four
  tools, tiny prompt, files-not-features, no MCP/subagents/background-bash.
- Pi docs (pi.dev): sessions, compaction, session format.
- OpenCode docs: providers, Zen, config, models, agents (plan/build),
  permissions (`allow`/`ask`/`deny`, `external_directory`).
- OpenAI Python SDK; Groq OpenAI compatibility; Ollama `/v1`; Google's
  OpenAI-compatible Gemini endpoint.
- AgenticRoadmap (`docs/`, `AGENTS.md`, Phase 2 raw loop) — docs-first,
  growing-file guide structure.
- Armin Ronacher, "Agent Design Is Still Hard" — own the loop, reinforcement
  and failure isolation notes.
