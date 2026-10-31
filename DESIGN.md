# Design

A small, reliable coding agent harness in Python, built to be understood
end-to-end. Few features, each finished. This file is why those choices were
made. What the code does today lives in `docs/`; what is next lives in
`docs/STATUS.md`.

**Non-goal:** feature parity with OpenCode, Pi, or anything else. Completion of
whatever features exist beats breadth.

**Target:** a stable minimum that handles real coding tasks — a loop that never
dies, `read` / `write` / `edit` inside a workspace, separate plan and build
modes, swappable models, and enough observability to see what is happening.
Not a demo loop, not a product.

Decisions are numbered `D1`, `D2`, … Append only. Never renumber. A decision
that is replaced is marked `superseded by D<n>` and keeps its text.

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
the raw JSON object from the response body (`choices[0].message`), or the
plain dict rebuilt from `chunk.to_dict()` in the streaming loop — not an SDK
object and not a rebuilt `tool_calls` list. Preserve `extra_content`.

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

History stores plain dicts only. A Gemini thought signature rides in
`extra_content`. Do not parse it. A 400 that names `thought_signature` is the
only reason to touch that append.

## Decisions

### D1 — Hand-written sync loop

**Status:** active

**Decision.** One synchronous `while` loop over `chat.completions.create`.
The user message is appended once, by the REPL. The assistant message is
appended once per reply. Each tool call appends one `role: "tool"` message
with the same id. `MAX_STEPS` is 16.

**Alternative.** LangGraph, for a graph of nodes. LlamaIndex `FunctionAgent`,
for a hidden loop. `deepagents`, as a dependency that already has planning,
filesystem, subagents, and compaction.

**Consequence.** Branching, abort, and compaction have to be written here,
which is the point: they stay visible. Stay sync. Streaming did not change
that (`docs/streaming.md`). `deepagents` remains a checklist
(## Deferred), not an import. The comparison is the one in §1.

The original prompt budget was about four sentences plus the tool list, under
~1000 tokens. The prompt has grown with the tools. What remains is that routing
lives in `SYSTEM`, not in a tool docstring.

### D2 — Failures are strings

**Status:** active

**Decision.** Tool failures, validation errors, unknown tool names, and
`max_steps` return a string the model can read. Tool code never raises out of
the loop. `tool_from_fn` catches `Exception` only, so `KeyboardInterrupt`
stays control flow.

**Alternative.** Raise, and let the REPL die. That is what the first raw loop
did, and it is why `max_steps` returns `Max limit reached: 16. Try smaller request.`

**Consequence.** A bad call is a turn the model can correct, not a crash. The
five raw-loop bugs this replaced were: `user_input = str`, an unused
`user_text`, `"exit"` sent to the model, `max_steps` raising, and unbounded
history. The last one is noted, not fixed; compaction is deferred.

### D3 — `tool_from_fn`, not a hand-written schema

**Status:** active

**Decision.** An ordinary function with a Google-style docstring and type
hints becomes the JSON schema and a `pydantic.create_model` validator. The
first docstring line is the description. `Args:` entries are the parameter
docs. Anything else in the body is invisible to the model. The registry is
`name → {schema, fn}`. There is no `if/elif` dispatch chain.

**Alternative.** Hand-written schemas, which drift from the function the day
the signature changes.

**Consequence.** Routing rules that the model must follow live in `SYSTEM`,
not in docstring bodies. `path` docs say absolute or workspace-relative.
They do not say "in the sandbox" — that taught the model to try `.` and `..`.
The numbered body of `read` is `role: "tool"` content; the model may quote it
or summarize it.

### D4 — `write` and `edit` stay separate

**Status:** active

**Decision.** `write` creates a file or replaces it wholesale (`content` is
the full final text). `edit` changes one exact unique span. Insert is an
anchor: `old_text` is the anchor, `new_text` is the anchor plus the
insertion. A new file is `write`, not the shell. A partial change is `read`
then `edit`, never `write` with partial content.

**Alternative.** One tool that both creates and patches, or a line-number
edit. Line numbers drift as the file changes; exact text does not.

**Consequence.** `read` is 1-indexed (`offset=1` is the first line) with
`limit=2000`, the same cap Pi uses, so a huge file cannot fill the context.
`edit` prints a one-shot unified diff to stdout and does not send that diff
to the model.

### D5 — The `openai` package is the only transport

**Status:** active · supersedes the LiteLLM transport (2026-09-30)

**Decision.** One installed client. `base_url` selects the server. A new
server is one `_SERVERS` tuple — `(id_env, key_env, base)` — plus two env
lines. The id comes from `.env`. The base stays in code. No `gemini/` or
`ollama_chat/` prefix. No hardcoded id. The catalog is not in `.env`.

**Alternative.** LiteLLM, which was the first transport and hid the request.
One installed SDK per brand, which is the same problem with more packages.

**Consequence.** Gemini's base is
`https://generativelanguage.googleapis.com/v1beta/openai/`. Ollama is
`http://127.0.0.1:11434/v1`; an empty key on `127.0.0.1` or `localhost`
becomes `"ollama"`. llama.cpp is its `/v1` endpoint, the same shape, and is
not in `_SERVERS` until asked. A missing Gemini key still fails. A raised
call returns `Model Error:`. Groq, if asked, is
`https://api.groq.com/openai/v1` and nothing else — one tuple, not a registry
redesign. Do not add it until asked. A name-to-base dictionary does not remove
that edit until a command looks the name up.

The later catalog tuple is `(id_env, key_env, base, transport)` with tags
`chat`, `responses`, `anthropic`, `google`. One call site. One function,
the same idea as `tool_from_fn`, picks the body from the tag. That tag is
not built yet (## Deferred). It is not an SDK per brand.

### D6 — Own the model record; do not scrape a catalog

**Status:** active

**Decision.** Free-tier Gemini is rate-limited for a long agentic loop, which
is why a local server and a gateway exist at all. Never store just a model
string. The record is `id`, `api_base`,
`api_key` (the env name, not the secret), `context_window`, `max_tokens`,
cost fields, and capabilities. Lookup is `os.getenv(record["api_key"])`.
`default_id` is `os.getenv("GEMINI_MODEL")` once; that is the startup choice.
`/models` lists loaded ids. `/models N` or `/models <id>` changes
`active["id"]` for the session only. Restart restores `default_id`.
`/model` is not a command.

**Alternative.** OpenCode's provider catalog, and Pi's models.dev scrape.
Both are products. This harness needs two servers.

**Consequence.** The `openai` package is the transport, not a provider
catalog. It does not give a typed catalogue, context windows, cache flags,
`/connect`, or a catalog import. That import has no slash command yet;
`/models` lists what `.env` loaded, and it is not the catalog. Cost fields
stay zero and are not printed until more models exist. `context_window` stays
unset until a number is verified; context `%` stays off rather than show a
guess. No models.dev import, no 75 providers, no OAuth yet. OAuth is not a
fifth transport tag. `/connect` waits with that catalog. It is not a
key-writer on `_SERVERS`. Variants are not a flag on the current create call.
`/effort` is not that: it sets `thinking_level` on Gemini and
`reasoning_effort` on Ollama.

Do not add an OpenCode Console free model. Since 18 September 2026 that tier
returns `403 FreeTierError` outside the official client. A maintainer said
the limit is the free tier only. Do not fake client headers. A paid
chat-completions id is still one tuple if asked. It is not the free backup.

Switching models mid-session changes the next create's `model` and
`base_url`. History stays Chat Completions dicts, so no conversion is
required. Credentials later move to a `0600` file in the user data dir
(OpenCode: `~/.local/share/opencode/auth.json`), not the project `.env`, and
never into the record.

### D7 — The workspace is the launch directory

**Status:** active · supersedes the root-level `sandbox/` default

**Decision.** The workspace is `Path.cwd().resolve()`, or `--sandbox path`,
auto-created at startup. Paths may be absolute or workspace-relative. A path
outside the workspace asks `external_directory`; it is not a silent reject
and not a hard error. On Windows, `classify` rewrites a Git Bash drive path
`/d/Pycharm_Projects/...` to `D:/Pycharm_Projects/...` before the check.
`/tmp` and `/home` do not match. No rewrite on Unix.

**Alternative.** A dedicated `sandbox/` directory as the only root. That was
the dev fence so tool tests could not overwrite `src/`. It is now the dev
override: `uv run python -m minicode --sandbox sandbox`. `sandbox/` is
gitignored.

**Consequence.** The product matches Pi and OpenCode: the agent works in the
directory it was launched in. The accident class that matters first — a write
landing outside the project — is a prompt, not a container. Containerization
stays the boundary for untrusted work (## Deferred).

### D8 — Plan and build are one conversation

**Status:** active

**Decision.** Two modes, one history. The guarantee is the tool list, not a
prompt. Plan drops `write` and `edit` from `tools=` and denies them at
dispatch. Build offers every tool. `/plan` and `/build` switch before any
model call and always rebuild `messages[0]`. Startup is plan. `/new` resets
to plan. History is not rewritten.

**Alternative.** OpenCode's two primary agents, switched with Tab. A second
agent would split the conversation the plan was written in. A prompt that
asks the model not to write is a request; removing the tools is a fact about
the request body.

**Consequence.** No `PLAN.md`. Pi's plan file is a different, smaller thing,
and it is not a mode:

1. You tell the agent: think with me, do not touch code.
2. Optionally you restrict tools for that session.
3. The agent uses `write` to create a `PLAN.md`: goal, approach, steps,
   current step.
4. Nothing auto-approves or auto-deletes it. You read and edit the file.
   Then you say "implement PLAN.md".
5. The file persists and versions with git.

No approval gate, no lifecycle — a markdown convention, as opposed to Claude
Code's black-box plan subagent. MiniCode can adopt the convention later
without making it the mechanism. The mechanism stays the restricted tool
list. Shell stays in the plan list; D12 restricts it. `PLAN_SYSTEM` says not
to create or delete files with the shell, not to paste file contents, and,
if the user asked for a file, to end by telling them to run `/build`.

### D9 — The shell's name is the shell that won

**Status:** active

**Decision.** One function, resolved once at import. Windows: Git Bash, then
`pwsh`, then `powershell.exe`. Skip `System32\bash.exe`. Unix: bash, then
`sh`. No `pwsh` on Unix. No `cmd.exe`. The registered name is `bash` or
`powershell`, set before `tool_from_fn`, so the model speaks the dialect that
runs. `cwd` is the workspace. Timeout is 120s, not a parameter. Output is
capped at 8000 characters, tail kept. A non-zero exit returns `exit {code}`
plus output. No `workdir`, no background process, no persistent session.

**Alternative.** Pi keeps bash and PowerShell as two tools and does not fall
through; a Windows box with neither Git Bash nor `bash` on `PATH` gets an
error. OpenCode honors `OPENCODE_GIT_BASH_PATH`, auto-detects otherwise, and
falls through to `cmd.exe`; that fallback breaks quoting, and its detection
can pick the WSL launcher through `SHELL`. Claude Code uses PowerShell only
when Git Bash is absent; on Linux `pwsh` is an opt-in, not the missing-bash
fallback.

**Consequence.** MiniCode falls through to PowerShell on Windows, because a
box without bash can still run a command, and it does not fall through to
`cmd.exe`. `sh` registers as `bash` so the permission key stays `shell`.
`SYSTEM` names only the loaded winner.

### D10 — Deny the shell in plan

**Status:** superseded by D12

**Decision.** When the shell landed, `PLAN_DENIED` listed `bash` and
`powershell` as well as `write` and `edit`, so plan could not run a command.

**Alternative.** Leave the shell in the plan tool list and hope the prompt
held.

**Consequence.** A plan turn could not run `git diff`. A tool-list deny
cannot express "reading is fine, deleting is not". D12 puts both names back
and restricts by rule. Do not put both names in `PLAN_DENIED` again.

### D11 — `.env` is a hard refuse

**Status:** superseded by D12

**Decision.** A `read` of `.env` or `.env.*`, and a shell command whose text
contained `.env`, returned a tool error. There was no approval.

**Alternative.** Ask, and let the user allow a deliberate read.

**Consequence.** The model could not be granted a one-shot look at a secret,
so it retried with a different tool. D12 makes the same paths an `ask`.
`.env.example` was never refused.

### D12 — A permission gate, not a scanner

**Status:** active · supersedes D10 and D11

**Decision.** One gate in front of dispatch answers `allow`, `ask`, or
`deny`. Last matching rule wins. No match denies. `*` matches any character,
including `/` and a newline. `?` matches one. `pathlib.Path.match` is not
used: there `*` stops at `/`. Defaults: `read` / `glob` / `grep` / `edit`
allow (`edit` gates `write` and `edit`); `shell` allow, except a command
whose text contains `.env`, which asks; `read` of `*.env` and `*.env.*`
asks, `*.env.example` allows; `external_directory` asks. `always` is an
exact `(key, value)` pair, session-scoped, saved in the session file,
restored on resume, cleared by `/new` or deleting the active session. A
missing prompt denies. The prompt is a callback the REPL registers; the loop
does not import the REPL.

**Alternative.** OpenCode's command scanner. A scanner is a parser that must
be right about every shell's quoting, and a wrong parse is a silent allow.
Also rejected: prompting on every in-workspace edit. Pi's argument, and
OpenCode's current default: once the workspace bounds the path, that prompt
is theater. The prompt that matters is the one for a path outside the
workspace, and for a `.env`.

**Consequence.** In plan, a shell command asks when a piece's first word is
a content-read, create, or delete (`rm`, `touch`, `cat`, and the rest of
that list) or the text contains `>`. `ls`, `pwd`, `git`, `python`, `echo`,
and `find` do not. Do not parse past the first word. Do not force-deny shell
in plan. `python -c` can still write. A build-mode heredoc is allowed. A
plan-mode heredoc still asks, because its first word is a content-read verb
or the text contains `>`. A denied plan shell returns one
sentence telling the user to run `/build`; the prompt still showed the
command. No config file, no env scrubbing, no transport tag. A JSON
permissions file, where a configured `deny` beats `always`, is deferred.

YOLO is fine inside that box for now. Pi's argument stands: once an agent can
write and run code, permission prompts are mostly theater — but the workspace
still bounds where files land, which is the accident class that matters
first. A permitted command can `cd` out; that is a prompt on the command
text, not a jail, and not a reason to parse the command.

### D13 — Observability is a printed block, not a rate

**Status:** active

**Decision.** No TUI. After a successful tool, one line. `/args` defaults to
`off`, which prints `|Tool Used: \`name\``. `/args on` adds the arguments,
or a left `|` rail when a value contains a newline. A plan denial, a
permission denial, and an unknown tool print the tool string, not that line.
After the reply, one status block: model, mode, tools, the sandbox and
display flags, then
`{In} | {Out} | {Session} | Elapsed: {_elapsed}`. Startup and `/new` print
the block with no usage line.

**Alternative.** Tok/s, or a footer rewritten in place the way Pi and
OpenCode do. A wall-clock rate is network wait, not model speed, and summed
`total_tokens` counts the prompt once per step.

**Consequence.** `In` is the last call's `prompt_tokens` (overwrite). `Out`
sums `completion_tokens` across the turn. `Session` sums `completion_tokens`
for the conversation, is restored on resume, and resets on `/new` or
deleting the active session. Do not add `prompt_tokens` into it. A resent
prompt is not new work. An aborted stream adds nothing. `_elapsed` lives in
`__main__.py`: under 60s one decimal (`60.0` rolls to `1m`); after that the
two largest units from `s`, `m`, `h`, `d`, `w`, `y`, dropping a zero
remainder. A week is 7 days. A year is 365 days. No months. Context `%` is
appended only when `context_window` is set.

| Now | Next | Later |
|---|---|---|
| Active model id | Context % (`prompt_tokens` ÷ `context_window`) | Cost, once more models exist |
| Mode | Prompt-cache hits, when `usage` reports them | Diff viewer |
| Enabled tool names, session export | | Cache control |
| `In` / `Out` / elapsed | | |

The response `usage` object is enough for token counts. No tiktoken. The
edit diff is a testing print, not a viewer.

### D14 — Reasoning is display-only

**Status:** active

**Decision.** The agent call streams. Reasoning prints as it arrives when
`/thinking` is `on`; the answer streams with no `minicode >>` prefix. A
`<thought>` or `<think>` span is pulled out of content before it is printed
and before it is stored. Reasoning is never `content` and never history.
`extra_content` is preserved and not read as reasoning.

**Alternative.** Buffer the whole step and print it at the end, which is how
the first streaming pass worked, or keep a prefix that has to be rewritten
as tokens arrive.

**Consequence.** An abort must leave history the next request can send: no
empty assistant message, no unanswered tool-call id. Partial text is marked
`[interrupted by user]` or `[model error]`. Ctrl+C during a model call or a
tool call is control flow. The Windows case where Ctrl+C does not land while
httpx is blocked in Winsock `recv`, and a click paste that submits every
`input()` line, are deferred. The shape is an amendment to
`docs/streaming.md`, not a new doc.

### D15 — One JSON file per session, per workspace

**Status:** active

**Decision.** Sessions live under the user data directory, grouped by a
project key (sanitized workspace name plus a short hash of the resolved
path). One file per conversation. No file at startup. The first user message
creates it. `messages` excludes the system prompt; resume rebuilds
`messages[0]` from the current mode. No reasoning field. `always` pairs are
saved and restored. `/sessions` lists, resumes, renames, and deletes. There
is no `/resume`, `/rename`, or `/delete`.

**Alternative.** A database, or one global list, or a JSONL tree. A session
is a small document written and read whole. A database earns its place when
there is a query across sessions, and there is none. OpenCode also stores
sessions per project, because a coding session only means anything in the
directory it was about.

**Consequence.** The system prompt on disk would freeze an old tool list into
a resumed conversation, so it is rebuilt. A title is one daemon call after
the first save; rename wins; title tokens never enter history or the status
line. `/export` writes the same transcript the resume replay prints. It is
display, not history: no model call, no save.

### D16 — The prompt prefix stays byte-identical

**Status:** active · the cache itself is not built

**Decision.** Do not shuffle old messages, and do not compact by rewriting
history, until prefix stability is understood. For a local model (Ollama,
llama.cpp) a prefix KV-cache hit requires the prompt prefix to stay
byte-identical. That is a correctness property, not an optimization.

**Alternative.** Compact by summarizing and rewriting, which is the usual
fix for a long session and which silently misses the cache.

**Consequence.** Cache control is the next piece of work, named in
`docs/STATUS.md`. It is not faked. Cloud `usage` may include cache-read
tokens where the provider sends them; no custom cache code until a second
provider actually needs it. History stays unbounded until the context gap
hurts on a real codebase.

### D17 — Docs describe what shipped

**Status:** active · supersedes the one-guide-per-layer convention

**Decision.** A document describes what the system does now, why it is shaped
that way, and how to check. `docs/STYLE.md` is the convention. One feature
doc per subsystem. Planned work is a `docs/STATUS.md` entry, not a guide.
The twelve build guides are frozen under `docs/archive/build-guides/` and
are not linked from the doc map.

**Alternative.** AgenticRoadmap's shape: write the guide, then the `.py`
from it. That was the spine while the layers were being built. The guides
went stale — they still print `minicode >>` — which is why a doc may only
describe behaviour that exists in `src/` today.

**Consequence.** A behaviour change updates the feature doc, `CHANGELOG.md`,
and `README.md` when the user can see it, in the same commit. A shipped
decision is not edited; it is superseded here.

## Deferred

Deliberately not being built. Each row is the union of the lists that existed
before this file: the research plan's deferred section, its layer-gap table,
`docs/STATUS.md`, `README.md`, and the prohibitions in `AGENTS.md`. Nothing
from those lists was dropped. Where two lists gave different triggers, both
are kept.

The single next item is named in `docs/STATUS.md`. The order after that, for
the three that have one, is cache control, then a diff viewer, then
`AGENTS.md` injection. Cost is not in that chain. Compaction is not next.
`/connect` is not in that chain.

| Item | Trigger |
|---|---|
| Cache control | Next. Display cache-read tokens when `usage` reports them. No custom cache code until a second provider needs it. The prefix stays byte-identical (D16). |
| Context `%` | Only when `context_window` is a verified number. Do not invent one. It is `None` today, so the percentage stays off. |
| Diff viewer | After cache control. The one-shot `edit` diff is a testing print, not a viewer. |
| `AGENTS.md` injection | After the diff viewer. When the model needs the repo conventions without the user pasting them. Not injected today. |
| Compaction | When the context gap hurts on a real codebase. Do not rewrite history before D16 is understood. Not a layer, and not next. |
| Cost display | When more models are added. Then it needs pricing on the model record. Input becomes part of a total. Not before. |
| Tests | Planned with `tool_from_fn`. Still open. Ad-hoc checks only, for the registry, the tools, and sessions. |
| JSON permissions file | When a configured `deny` must beat `always`, or the rules must change without a code edit. OpenCode-shaped, loaded at startup. Not next. |
| Granular approvals | When exact `(key, value)` pairs are too coarse. Not a prefix match, and not a pattern approval. |
| models.dev import | With the catalog, when two servers are not enough. Pi scrapes it; this harness does not, yet. |
| `/connect` | With that catalog. Paste a key or run a browser login. Write a bearer token to the user data dir, mode `0600`, not the project `.env`. The record holds a name, not the secret. Lookup stays one function; do not replace `os.getenv`. Not a key-only phase. Ollama local stays a base URL plus an empty key, not a login. A Grok subscription is that same kind of login, not a new server. |
| Transport tag | With the catalog. The tuple gains `transport`: `chat`, `responses`, `anthropic`, `google`. One call site. Not an SDK per brand. Not added beside the permission gate. |
| Variants | Fetched with the catalog. Not a flag on the current create call. `high` / `max` reasoning effort is a variant, not `/effort`. |
| Gemini `reasoning_effort` | Do not add it. Gemini summaries use `include_thoughts` and `thinking_level` from `/effort`. Ollama is the server that gets `reasoning_effort`. |
| Windows paste and a stuck Ctrl+C | An amendment to `docs/streaming.md`, not a new doc, and not next. After `input()` returns, if the console already has more lines, do not send them. On interrupt, `FlushConsoleInputBuffer`. Run the stream on a worker and `time.sleep` on the main thread so Ctrl+C can close the httpx stream. A second Ctrl+C calls `os._exit`. No TUI, no asyncio, no short read timeout, no `prompt_toolkit`. |
| Subagents | When delegation is the gap that hurts. Checklist item, not a dependency (D1). |
| MCP | When a server is actually needed. The starting position, from Mario Zechner, is that it is not. |
| Skills | When a repeated workflow does not fit the system prompt. |
| LSP | When search and the shell stop being enough to navigate a codebase. |
| LangGraph | Only for genuine branching between distinct nodes. Not as a replacement for the loop (D1). |
| LlamaIndex | Not while it hides `tool_calls`, the tool message, the loop, and the stop condition. |
| RAG / Chroma | When the workspace is too big to read and search directly. |
| Background bash | When a command must outlive the turn. There is no background process and no persistent shell. |
| Rich / Textual | When the printed status block is not enough. No TUI yet. |
| Web UI | When a terminal is the wrong interface. A graphical interface is the same deferral. A future UI is never imported by the loop. |
| JSONL session tree | When one JSON file per conversation cannot express a branch. |
| Containerization | Separate from the path boundary. The real boundary for untrusted work. A shell command can still `cd` out; the gate asks, it does not jail. |
| Env scrubbing | Not planned. The child inherits the process environment. Promote only if a leaked key becomes the accident class that matters. |
| Groq | When asked. One `_SERVERS` tuple plus two env lines. Not a registry redesign. |
| OpenCode Console free model | Do not add. Since 18 September 2026 that tier returns `403 FreeTierError` outside the official client. Do not fake client headers. A paid chat-completions id is one tuple if asked. |

## Layers

Shipped. The contract for each one is the doc named here. The checkpoints are
what "done" meant; they are not a reading order.

| Layer | Doc | Checkpoint |
|---|---|---|
| 0 — loop, workspace, `read`, status | `docs/loop.md`, `docs/observability.md` | Reads a file, prints a tool line, survives bad args, shows the status block, exits without sending `"exit"` to the model. |
| 1 — `write` + `edit` | `docs/file-tools.md` | Edits a local file; a mismatched `old_text` returns a tool error and the model retries. |
| 2 — model registry | `docs/models.md` | `_SERVERS`, `/models`, ids from `.env`, bases in code. |
| 3 — workspace flip | `docs/workspace.md` | Default workspace is the launch cwd. `--sandbox path` overrides. |
| 4 — search | `docs/search.md` | `glob` and `grep` in `tools/`, capped. |
| 5 — plan/build | `docs/modes.md` | Startup is plan. Plan drops `write` / `edit` and denies them at dispatch. |
| 6 — shell | `docs/shell.md` | One resolved tool. D10 denied it in plan; D12 put it back. |
| 7 — permissions | `docs/permissions.md` | Gate in `permissions.py`, dispatch in `agent.py`, prompt in `__main__.py`. |
| 8 — streaming and abort | `docs/streaming.md` | One streamed create, `chunk.to_dict()` keeps `extra_content`, Ctrl+C returns to `>>> ` with a coherent history. |
| 9 — sessions | `docs/sessions.md` | One JSON file per workspace. Resume restores messages, settings, usage, `always`, and `last_turn`. |
| 10 — export | `docs/export.md` | `/export` writes the replay transcript. No reasoning capture, no compaction, no database. |

Known gaps that are still open, and are not new layers: no automated tests;
history unbounded; `context_window` unset; cache tokens not displayed; the
workspace is a path boundary, not a container; no permissions config file; no
env scrubbing; no diff viewer; `AGENTS.md` is not injected; cost is not
displayed; a paste can submit every line; Ctrl+C does not land in a blocked
Winsock `recv`. Each of those is a row in ## Deferred, except the ones that
are accepted limits of a shipped feature (`docs/export.md` overwrites a file
when two sessions share a title; session files exclude reasoning on purpose,
D15).

## Invariants

The original reliability rules, verbatim:

- Tool code never raises out of the loop.
- Unknown tool name → string, not crash.
- Paths outside the sandbox → string error.
- One `chat.completions.create` site. A new server is `api_base` plus an id,
  not a new client.
- No invisible behavior. Config is env first; every key inspectable later.
- Secrets never in committed config.

D7 superseded the outside-path bullet: an outside path asks
`external_directory` instead of returning a string error. The other five hold.
`AGENTS.md` wins if this file and the code ever disagree.

## Stack

Python ≥3.13, **uv**, `openai`, `pydantic`, `python-dotenv`.
Not: LiteLLM, one installed SDK per brand, LangGraph, LangChain, deepagents,
LlamaIndex, Rich, pi-agent-core.

```
src/minicode/            # package
  __main__.py            # REPL only
  agent.py               # loop, SYSTEM, registry
  schema_generator.py    # tool_from_fn
  resolve_path.py        # sandbox root + _resolve
  permissions.py         # allow / ask / deny gate
  sessions.py            # session JSON, list, rename, delete
  tools/                 # read, write, edit, glob, grep, shell
docs/                    # index + one doc per subsystem + STATUS + STYLE
docs/archive/            # retired build guides, frozen
AGENTS.md                # session start
DESIGN.md                # this file
README.md                # user guide
.env.example
```

The loop owns dispatch. Tools never import the LLM. A future UI is never
imported by the loop. New work names the file (`AGENTS.md`). It does not grow
`__main__.py` with the loop.

## Sources

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
