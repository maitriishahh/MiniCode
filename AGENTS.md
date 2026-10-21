# AGENTS.md — MiniCode

A small Python coding harness. Docs first, then the `.py` from the doc.

## Read order (every new session)

1. This file (`AGENTS.md`)
2. `docs/STATUS.md` — what is done, what to write next
3. `HARNESS_RESEARCH_AND_PLAN.md` — decisions (loop, providers, sandbox,
   plan/build, observability)
4. The next build guide listed in STATUS

When a session locks a new convention, write it into `AGENTS.md` in the same
pass. A new session must not need prior chat history.

The next guide is the file named in `docs/STATUS.md`. Write that guide
before any code. Do not implement the next layer in the same pass as
writing it unless the user says implement.

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
  tools/                 # read.py, write.py, edit.py, glob.py, grep.py, shell.py
docs/                    # STATUS + setup + one build guide per layer
.env.example             # copy to .env
```

Do not invent empty package dirs (`llm/`, `core/`, `session/`, `ui/` …).
Imports are `minicode.*`. Do not split further without a reason.

A guide names the file. It does not say "grow `__main__.py`". REPL, slash
commands, and the status print live in `__main__.py`. The loop, `SYSTEM`,
the registry, and the one `chat.completions.create` site live in `agent.py`.
The function is `agent`, not `run_agent`. `tool_from_fn` stays in
`schema_generator.py`. Sandbox stays in `resolve_path.py`. A new tool is
`tools/<name>.py` plus one registry line in `agent.py`. Snippets use
`user >>`, `|Tools Used: \`name\` ({args})|`, and
`{In} | {Out} | Elapsed: {elapsed:.1f}s`.
No Tok/s. Future guides must not say `from litellm import completion`,
`ollama_chat/`, a `gemini/` prefix, `OLLAMA_ID = "qwen3-coder"`,
`api_key_env` as the record key, or that the code still imports LiteLLM.

## Conventions (do not break)

- Growing file: each guide says keep / add / replace. The loop shape in
  `HARNESS_RESEARCH_AND_PLAN.md` §1 is fixed — user appended once in the
  REPL, assistant appended once per reply, one `role: "tool"` per call.
  History stores plain dicts only. The assistant message appended is the raw
  JSON object from the response body (`choices[0].message`), not an SDK
  object and not a rebuilt `tool_calls` list. A Gemini thought signature
  rides in that dict. Do not parse it. A 400 that names `thought_signature`
  is the only reason to touch that append.
- Tool functions use Google-style docstrings. Only the first line becomes the
  model-visible description and `Args:` entries become parameter docs;
  extra scope sentences in the docstring body are invisible to the model.
  `tool_from_fn` compiles schema + validation.
- `write` and `edit` stay separate tools, never merged: `write` creates a new
  file or overwrites the whole file (`content` = FULL final contents);
  `edit` changes one exact unique span (insert via anchor:
  `old_text`=anchor, `new_text`=anchor+insertion). A new file is `write`
  with no read. An existing file replaced wholesale is `read` then `write`
  of the full file. Partial changes (add/append/insert, replace X with Y)
  are `read` then `edit` — never `write` with partial content. The routing
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
  `include`, then `read`) lives in `SYSTEM`.
- Plan and build are one session. `mode = {"name": "build"}` lives in
  `agent.py`. `/plan` and `/build` are handled in `__main__.py` before any
  model call. Plan drops `write` and `edit` from `tools=`
  (`active_schemas()`) and denies them at dispatch (`PLAN_DENIED`).
  `TOOLS` stays full. Only `messages[0]` swaps (`SYSTEM` vs
  `SYSTEM + PLAN_SYSTEM`). History is not rewritten. `MAX_STEPS` is `16`.
  Plan mode may tell the model to read every `glob` match in one response.
  No batching sentence in `SYSTEM`. No `PLAN.md`.
- Shell is implemented in `docs/07-shell.md`. One
  function in `tools/shell.py`, resolved once at import. Windows: Git Bash,
  then `pwsh`, then `powershell.exe`. Skip `System32\bash.exe`. Unix: bash,
  then `sh`. No `pwsh` on Unix. No `cmd.exe`. The registered name is `bash`
  or `powershell`, set before `tool_from_fn`. `PLAN_DENIED` gains both
  names. `SYSTEM` names `bash` or `powershell`, whichever is loaded. It does
  not name `&&` or a semicolon. `cwd` is `SANDBOX`. Timeout is
  120s, not a parameter. Output is capped at 8000 characters, tail kept. A
  non-zero exit returns `exit {code}` plus output, and that string is
  printed once. `.env` in the command text is a tool error. No `workdir`,
  no background process, no persistent session. Do not point `cwd` at the
  repo root to bypass `--sandbox`.
- `exit` / `quit` / `bye` leave before any `chat.completions.create` call.
- Paths resolve inside the sandbox; escapes and `.env` files are tool errors.
  Workspace is the launch cwd (`_sandbox_root()`: `Path.cwd().resolve()`,
  `--sandbox path` overrides it, auto-created at startup). The old default
  was the root-level `sandbox/` dir — that was the dev fence so tool tests
  could not overwrite harness source in `src/`. It is now the dev override:
  `uv run python -m minicode --sandbox sandbox`. `sandbox/` is gitignored.
  REPL prints `Sandbox: {SANDBOX}` once at startup, and the status block
  carries a `Sandbox: {SANDBOX}` line.
- `load_dotenv()` runs once in `agent.py`, before any `os.getenv`. No
  `LITELLM_LOG`.
- Servers live in `_SERVERS`: `(id_env, key_env, base)`. The id comes from
  `.env`. The base stays in code. A new server is one tuple plus two env
  lines. Do not hardcode an id. Do not put the catalog in `.env`. The
  record field is `api_key`, and its value is the env name, not the secret.
  Lookup is `os.getenv(record["api_key"])`. `default_id` is
  `os.getenv("GEMINI_MODEL")` once. That is the startup choice. `/model <id>`
  changes `active["id"]` for the session only. Restart restores
  `default_id`. An unset id env skips that server. An empty key on
  `127.0.0.1` or `localhost` becomes `"ollama"`. A missing Gemini key still
  fails. A raised call returns `Model Error:`. No `gemini/` or
  `ollama_chat/` prefix. Gemini's base is
  `https://generativelanguage.googleapis.com/v1beta/openai/`.
  `/connect` is not this layer. It arrives with the catalog (models.dev
  import, `/models`, variants, a transport tag). Variants are reasoning
  effort. Do not pass them on the current create call. Do not add an
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
- REPL prompt is `user >> `. The answer prints as `minicode >> {answer}`.
  After a successful tool run, print `|Tools Used: `{name}` ({args})|`,
  including in plan. Unknown tools stay silent on stdout. Status block
  after the answer, wrapped in `---`:
  Model / Mode / Tools Loaded, `Sandbox: {SANDBOX}`, then
  `{prompt:,} In | {out:,} Out | Elapsed: {elapsed:.1f}s`. Context `%` is
  appended only when `context_window` is set.
- `last_usage` resets at the start of each turn. `prompt_tokens` is the last
  call only (overwrite) — that is `In`. `completion_tokens` **sums** across
  steps — that is `Out`. No Tok/s. A wall-clock rate is network wait, not
  model speed, and summed `total_tokens` counts the prompt once per step.
- Never bare `pip install`. Deps via `uv add`; run with `uv run`.
  `uv.lock` is committed (pins exact versions).
- Do not commit secrets, session dumps, or transcripts.

## Do not

- Promote a deferred topic (MCP, subagents, compaction, sessions,
  Rich, models.dev import, `/connect` …) into the current layer without an
  explicit ask.
- Add a feature without finishing it: unknown tools, escapes, and bad args
  must all behave before the layer is done.
- Send `exit`, secrets, or half-built scaffolding to the model.
- LiteLLM, or one installed SDK per brand. Today the transport is the
  `openai` package. The catalog's transport tag is later. It is not an SDK
  per brand.
