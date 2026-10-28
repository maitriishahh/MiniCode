# AGENTS.md — MiniCode

A small Python coding harness. Docs first, then the `.py` from the doc.

## Read order (every new session)

1. This file (`AGENTS.md`)
2. `docs/STATUS.md` — what is done, what to write next
3. `HARNESS_RESEARCH_AND_PLAN.md` — decisions (loop, providers, sandbox,
   plan/build, observability)
4. The next build guide or amendment listed in STATUS

When a session locks a new convention, write it into `AGENTS.md` in the same
pass. A new session must not need prior chat history.

The next guide is the file named in `docs/STATUS.md`. Write that guide
before any code unless STATUS names an amendment to an existing guide. Do
not implement the next layer in the same pass as writing it unless the user
says implement.

## When the user questions a shipped choice

Do not defend it from this file, `docs/STATUS.md`, a build guide, or
`HARNESS_RESEARCH_AND_PLAN.md`. Those files record what was built. They are
not evidence it is the right shape. Compare it to a named project (OpenCode,
Pi, Aider, Claude Code) or that project's docs. Cite the mechanism. "It is
locked" is not a reason. If it still wins, say why in that comparison. If it
loses, say what to change.

## What this is

A minimal coding agent: hand-written tool loop over the OpenAI client, `read`
/ `write` / `edit` inside a sandbox, plan and build as separate modes, a small
model registry, and a REPL status line. Few features, each finished.

## Stack (only these)

| Role | Choice |
|---|---|
| LLM transport | `openai` package, one `chat.completions.create` |
| Validation | `pydantic` (`create_model` in `tool_from_fn`) |
| Env | `python-dotenv`, `.env` from `.env.example` (never commit `.env`) |
| Python | ≥3.13, managed with **uv** |

Not in the project: LiteLLM, one SDK per provider, LangGraph, LangChain,
deepagents, LlamaIndex, Rich / Textual (yet), pi-agent-core (read-only
reference).

## Layout

```
src/minicode/            # package
  __main__.py            # REPL only
  agent.py               # loop, SYSTEM, mode, registry
  schema_generator.py    # tool_from_fn
  resolve_path.py        # sandbox root + _resolve
  permissions.py         # allow / ask / deny gate
  tools/                 # read.py, write.py, edit.py, glob.py, grep.py, shell.py
docs/                    # STATUS + setup + one build guide per layer
.env.example             # copy to .env
```

Do not invent empty package dirs (`llm/`, `core/`, `session/`, `ui/` …).
Imports are `minicode.*`. Do not split further without a reason.

A guide names the file and pastes the functions that belong there. "Not
implemented" means those functions are not in `src/` yet. Do not say "grow
`__main__.py`" instead of pasting the REPL functions. The loop stays in
`agent.py`. A segment that only describes a function is not done. REPL, slash
commands, and the status print live in `__main__.py`. The loop, `SYSTEM`,
the registry, and the one `chat.completions.create` site live in `agent.py`.
The function is `agent`, not `run_agent`. `tool_from_fn` stays in
`schema_generator.py`. Sandbox stays in `resolve_path.py`. A new tool is
`tools/<name>.py` plus one registry line in `agent.py`. Snippets use
`user >>`, `|Tool Used: \`name\` ({args})|` (a newline in an argument is a
left `|` rail, not that one-liner), and
`{In} | {Out} | {Session} | Elapsed: {_elapsed}`.
No Tok/s. Future guides must not say `from litellm import completion`,
`ollama_chat/`, a `gemini/` prefix, `OLLAMA_ID = "qwen3-coder"`,
`api_key_env` as the record key, or that the code still imports LiteLLM.

## Conventions (do not break)

- User-facing behavior changes update `README.md` in the same pass. An
  architecture edge names an import or call site; label runtime, import-time,
  and callback edges. A policy gate is not a parent of the tools it governs.
- Growing file: each guide says keep / add / replace. The loop shape in
  `HARNESS_RESEARCH_AND_PLAN.md` §1 is fixed — user appended once in the
  REPL, assistant appended once per reply, one `role: "tool"` per call.
  History stores plain dicts only. The assistant message appended is the raw
  JSON object from the response body (`choices[0].message`) or the plain dict
  rebuilt from `chunk.to_dict()` in the streaming loop, not an SDK object and
  not a rebuilt `tool_calls` list. Preserve `extra_content`. A Gemini thought
  signature rides in that dict. Do not parse it. A 400 that names
  `thought_signature` is the only reason to touch that append. The streaming
  rebuild lives in `docs/09-streaming.md`. Do not implement streaming in a
  pass that is only writing the guide.
- Tool functions use Google-style docstrings. Only the first line becomes the
  model-visible description and `Args:` entries become parameter docs;
  extra scope sentences in the docstring body are invisible to the model.
  `tool_from_fn` compiles schema + validation. `path` docs on `read`,
  `write`, `edit`, `glob`, `grep` say absolute or workspace-relative;
  outside the workspace asks permission. Do not say "in/under the sandbox"
  or "relative to the sandbox" — that taught the model to try `.` and `..`.
- `write` and `edit` stay separate tools, never merged: `write` creates a new
  file or overwrites the whole file (`content` = FULL final contents);
  `edit` changes one exact unique span (insert via anchor:
  `old_text`=anchor, `new_text`=anchor+insertion). A new file is `write`
  with no read. An existing file replaced wholesale is `read` then `write`
  of the full file. Partial changes (add/append/insert, replace X with Y)
  are `read` then `edit` — never `write` with partial content. A new file
  is `write`, not the shell. `PLAN_SYSTEM` says not to create or delete
  files with the shell, not to paste file contents, and, if the user asked
  for a file, to end by telling them to run `/build`. The routing
  rule lives in `SYSTEM`, not in per-tool docstrings.
- `edit` prints a one-shot stdlib `difflib.unified_diff` to stdout with
  `fromfile=f"a/{path} (before)"`, `tofile=f"b/{path} (after)"`,
  `lineterm="\n"`. Diff input is `splitlines()` plus `\n` (`_diff_lines`),
  not `keepends=True`, so a file with no trailing newline cannot fuse a
  `-` line and a `+` line. Printed as `---\nDiff: {path}\n{diff}` with
  `end="---\n" if diff.endswith("\n") else "\n---\n"` so the closing `---`
  always lands on its own line and never fuses with the next block.
  The model gets `Replaced 1 occurrence in {path} (changed A - B)` plus numbered
  lines in the same `N: line` shape as `read`: the full changed span, plus up
  to 5 lines before the first changed line and 5 after the last, clamped to
  the file. A deletion says `deleted at N`. An empty result says `(empty file)`.
  The diff is not sent to the model.
- Validation errors and tool failures return as `role: "tool"` strings. Tool
  code never raises out of the loop. `max_steps` returns a message, never
  raises.
- Search is capped: `glob` lists at most 50 paths, `grep` at most 50
  matches, both append `... and N more — refine pattern` past the cap and
  say `(no matches)` on empty. Both skip dot-dirs, `__pycache__`, and
  `.venv`, and omit `.env` and `.env.*` from results. A missing or
  non-directory root is a tool error. Routing (`glob`, then `grep` with
  `include`, then `read`) lives in `SYSTEM`. A root inside the workspace
  returns workspace-relative paths; a root outside returns absolute
  forward-slash paths. Never `relative_to(SANDBOX)` an outside hit — that
  raised, and the turn learned nothing.
- Plan and build are one session. `mode = {"name": "plan"}` lives in
  `agent.py`; a new session starts in plan. `/plan` and `/build` are
  handled in `__main__.py` before any model call. Plan drops `write` and
  `edit` from `tools=`
  (`active_schemas()`) and denies them at dispatch (`PLAN_DENIED`).
  `TOOLS` stays full. Only `messages[0]` swaps (`SYSTEM` vs
  `SYSTEM + PLAN_SYSTEM`). A new session starts in plan, so `messages[0]`
  is `SYSTEM + " " + PLAN_SYSTEM` at startup, not only after `/plan`.
  `/plan` and `/build` always assign that pair, even when the mode is
  already the one requested. History is not rewritten. `MAX_STEPS` is `16`.
  Plan mode may tell the model to read every `glob` match in one response,
  and it says a user-named file is read directly without a `glob` first.
  No batching sentence in `SYSTEM`. No `PLAN.md`.
- Shell is implemented in `docs/07-shell.md`. One
  function in `tools/shell.py`, resolved once at import. Windows: Git Bash,
  then `pwsh`, then `powershell.exe`. Skip `System32\bash.exe`. Unix: bash,
  then `sh`. No `pwsh` on Unix. No `cmd.exe`. The registered name is `bash`
  or `powershell`, set before `tool_from_fn`. Shipped `PLAN_DENIED` lists
  both names. Permissions are implemented. Never put both in `PLAN_DENIED`
  again. `SYSTEM` names only the loaded winner, `bash` or `powershell`
  (`shell.__name__`), never both. It does
  not name `&&` or a semicolon. `cwd` is `SANDBOX`. Timeout is
  120s, not a parameter. Output is capped at 8000 characters, tail kept. A
  non-zero exit returns `exit {code}` plus output, and that string is
  printed once. A shell command whose text contains `.env` asks. `$VAR`
  and `$env:VAR` do not. No `workdir`,
  no background process, no persistent session. Do not point `cwd` at the
  repo root to bypass `--sandbox`.
- Permissions are implemented in `docs/08-permissions.md`,
  `permissions.py`, the dispatch gate in `agent.py`, and the prompt in
  `__main__.py`. No config file, no shell scanner, no env scrubbing, no
  transport tag. Defaults: `read` / `glob` / `grep` / `edit` allow (`edit`
  gates `write` and `edit`); `shell` allow, except a command whose text
  contains `.env`, which asks; `read` of `*.env` and `*.env.*` asks,
  `*.env.example` allows; `external_directory` asks. Last matching rule
  wins. `*` matches any character, including `/` and a newline. `always` is in-memory
  and exact. A missing prompt denies. Plan keeps `write` / `edit` out of
  the schema. Shell stays in the schema. In plan, a command asks when a
  piece's first word is a content-read, create, or delete (`rm`, `touch`,
  `cat`, and the rest of that list) or the text contains `>`. `ls`, `pwd`,
  `git`, `python`, `echo`, and `find` do not. Do not parse past that. Do
  not force-deny shell in plan. `python -c` can still write. A JSON
  permissions file is deferred, not next. `agent.py` holds
  `ask = {"fn": None}`; `__main__.py` registers the prompt. A denial is
  `Permission denied: {key} {value}` as `role: "tool"`, with no
  `|Tool Used|` line. A plan-mode shell ask that the user denies returns
  `Plan mode: that command was denied. Do not try another shell command to create or change a file. Tell the user to run /build.`
  The prompt still shows the command. The tool string does not. A plan
  denial, a permission denial, and an unknown tool print that tool string.
  Still no `|Tool Used|` line.
- `SYSTEM` states the workspace root, that a path may be absolute, that a
  path the user already named is read with `read` (not `glob` and not the
  shell), and the locate order (`glob` → `grep` → `read`). It names only the
  loaded shell. It says a new file is `write`, not the shell.
  `PLAN_SYSTEM` appends: if the user named a file, read that path; do not
  glob first. It also says not to create or delete files with the shell,
  not to paste file contents, and, if the user asked for a file, to end by
  telling them to run `/build`.
- `exit` / `quit` / `bye` leave before any `chat.completions.create` call.
- Paths may be absolute or workspace-relative. On Windows, `classify`
  rewrites a Git Bash drive path `/d/Pycharm_Projects/...` to
  `D:/Pycharm_Projects/...` before the sandbox check. `/tmp` and `/home`
  do not match. No rewrite on Unix. A path outside the workspace
  triggers `external_directory`: allow runs, ask prompts, deny returns
  `Permission denied: external_directory {path}`. `.env` and `.env.*` ask
  on `read`. `.env.example` does not. A denial is `Permission denied: read
  {path}`.
  Workspace is the launch cwd (`_sandbox_root()`: `Path.cwd().resolve()`,
  `--sandbox path` overrides it, auto-created at startup). The old default
  was the root-level `sandbox/` dir — that was the dev fence so tool tests
  could not overwrite harness source in `src/`. It is now the dev override:
  `uv run python -m minicode --sandbox sandbox`. `sandbox/` is gitignored.
  Startup prints the status block with no usage line. The flag line is
  `Sandbox: {SANDBOX} | Thinking: {on|off} | Effort: {low|medium|high} | Args: {on|off} | Output: {on|off}`.
- `load_dotenv()` runs once in `agent.py`, before any `os.getenv`. No
  `LITELLM_LOG`.
- Servers live in `_SERVERS`: `(id_env, key_env, base)`. The id comes from
  `.env`. The base stays in code. A new server is one tuple plus two env
  lines. Do not hardcode an id. Do not put the catalog in `.env`. The
  record field is `api_key`, and its value is the env name, not the secret.
  Lookup is `os.getenv(record["api_key"])`. `default_id` is
  `os.getenv("GEMINI_MODEL")` once. That is the startup choice. `/models`
  lists `N id` with a blank line above and below. `/models N` or
  `/models <id>` changes `active["id"]` for the session only. A bare integer
  is a number, not an id. `/model` is not a command. It prints
  `Unknown command: /model. Use /models.` and is not sent. Restart restores
  `default_id`. An unset id env skips that server. An empty key on
  `127.0.0.1` or `localhost` becomes `"ollama"`. A missing Gemini key still
  fails. A raised call returns `Model Error:`. No `gemini/` or
  `ollama_chat/` prefix. Gemini's base is
  `https://generativelanguage.googleapis.com/v1beta/openai/`.
  `/connect` is not this layer. It arrives with the catalog (models.dev
  import, variants, a transport tag). The import has no slash yet. `/models`
  is the loaded-list command, not that catalog. Variants are a later
  catalog. Do not pass a catalog variant on the current create call.
  `/effort` is not that. It sets `thinking_level` on Gemini and
  `reasoning_effort` on Ollama for the session. Do not add an
  OpenCode Console free model. Since 18 September 2026 that tier returns
  `403 FreeTierError` outside the official client. Do not fake client
  headers. The later
  tuple is `(id_env, key_env, base, transport)` with tags `chat`,
  `responses`, `anthropic`, `google`. One call site. Not an SDK per brand.
  `/connect` pastes a key or runs a browser login and writes a bearer token
  to a user data dir, mode `0600`, not the project `.env`. Do not write the
  secret into the record. Do not replace `os.getenv`. A key-only command is
  not its own phase. Do not add the tag in the permissions guide. Ollama local
  stays a base URL plus an empty key, not a login.
- REPL prompt is `user >> `. `/thinking` lists `1 off` and `2 on` with a
  blank line above and below. `/thinking N` or `/thinking on|off` changes it
  for the session. Default is `off`. `/thinking off` prints only `Thinking:`.
  `/thinking on` shows the body. `/effort` lists `1 low`, `2 medium`, and
  `3 high` the same way. `/effort N` or `/effort low|medium|high` changes it.
  Default is `low`. `/args` lists `1 off` and `2 on`. Default is `off`,
  which prints only `|Tool Used: `{name}``. `/args on` is the one-liner or
  the left rail. `/output` lists `1 off` and `2 on`. Default is `off`, which
  hides the shell block. The model still gets that output. An edit diff
  still prints. `/help` prints the `COMMANDS` tuple in `__main__.py` and
  nothing else. A bare integer is a number, not a name. All of these are
  handled before any model call. Restart restores every default.
  When display is on, reasoning streams as `Thinking:` then `---`, the text,
  `---` on the next line, and a blank line. Trailing newlines in the summary
  are not printed. A blank line in the middle of the summary is. No `Thought:` closer. A `<thought>` or `<think>`
  span is pulled out of content before it is printed as the answer. No tag
  is kept in history. The Gemini create passes `include_thoughts: true` and
  `thinking_level` from `effort`. Ollama gets `reasoning_effort` from
  `effort`, not the Gemini body. With no summary, no thinking label appears
  and there is no wait line. Answer tokens stream as they arrive. There is
  no `minicode >>` prefix. Tool lines,
  `Model Error:`, max-limit notices, and `[interrupted by user]` stay plain.
  `docs/09-streaming.md` specifies the event
  contract. Reasoning is display-only: never
  append it to history, never use it as `content`. Strip `<thought>` and
  `<think>` before history. Do not read `extra_content` as reasoning; it
  still carries the thought signature. Do not parse the signature. After a
  successful tool run, print `|Tool Used: `{name}`` when `/args` is `off`.
  That is the default. When `/args` is `on`, print
  `|Tool Used: `{name}` ({args})|`. A JSON object with a string value that
  contains a newline instead prints `|Tool Used: `{name}`` and then one `|`
  line per real line, with the key on the first line of that value. No
  trailing `|` on those lines. A short call stays the one-liner. Do not
  re-serialize it.
  A plan denial, a permission denial, and an unknown
  tool print that tool string, not `|Tool Used|`. Status block
  after the answer, wrapped in `---`:
  Model / Mode / Tools Loaded, `Sandbox: {SANDBOX} | Thinking: {name} | Effort: {name} | Args: {name} | Output: {name}`, then
  `{prompt:,} In | {out:,} Out | {session:,} Session | Elapsed: {_elapsed(elapsed)}`.
  `_elapsed` lives in `__main__.py`. Under 60s it keeps one decimal (`45.2s`,
  and `60.0` rolls to `1m`). After that it shows the two largest units from
  `s`, `m`, `h`, `d`, `w`, `y`, and drops a zero remainder. A week is 7 days.
  A year is 365 days. No months. `1433.8` is `23m 54s`. `10` days is `1w 3d`.
  `400` days is `1y 5w`. Context `%` is appended only when `context_window`
  is set.
- `last_usage` resets at the start of each turn. `prompt_tokens` is the last
  call only (overwrite) — that is `In`. `completion_tokens` **sums** across
  steps — that is `Out`. `session_usage` is not cleared. It sums
  `completion_tokens` for the process — that is `Session`. Do not add
  `prompt_tokens` into it. A resent prompt is not new work. Cost display is
  deferred until more models are added; when it lands, pricing makes input
  part of a total. No Tok/s. A wall-clock rate is network wait, not model
  speed, and summed `total_tokens` counts the prompt once per step. An
  aborted stream adds nothing. `docs/09-streaming.md` does not put
  `prompt_tokens` into `Session`.
- A new slash command is a handler in `__main__.py` before any model call,
  one row in `COMMANDS`, and a README commands-table row. `/help` prints
  `COMMANDS` only. Do not write a second help string. Do not generate the
  handlers from the tuple. Add an `AGENTS.md` sentence when the command is
  a new rule.
- Never bare `pip install`. Deps via `uv add`; run with `uv run`.
  `uv.lock` is committed (pins exact versions).
- Streaming, abort, the conditional reasoning labels, and the
  final-answer-only prefix are in the working tree. `KeyboardInterrupt` during
  a model call or a tool call is control flow, not a tool error. `tool_from_fn`
  catches `Exception` only. Do not catch it there. Never read a reasoning
  field to fill an empty `content` or add it to history. A click paste that
  submits every `input()` line, and a Ctrl+C that does not land while httpx
  is blocked in Winsock `recv`, are deferred. The shape is an amendment to
  `docs/09-streaming.md`, not next and not a new guide. Do not add
  `prompt_toolkit`, asyncio, a TUI, or a short read timeout for it.
- Do not commit secrets, session dumps, or transcripts.

## Do not

- Promote a deferred topic (MCP, subagents, compaction, sessions,
  Rich, models.dev import, `/connect`, Windows paste / stuck Ctrl+C …) into
  the current layer without an explicit ask.
- Add a feature without finishing it: unknown tools, escapes, and bad args
  must all behave before the layer is done.
- Send `exit`, secrets, or half-built scaffolding to the model.
- LiteLLM, or one installed SDK per brand. Today the transport is the
  `openai` package. The catalog's transport tag is later. It is not an SDK
  per brand.
