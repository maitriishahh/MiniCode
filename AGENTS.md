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
  agent.py               # loop, SYSTEM, registry
  schema_generator.py    # tool_from_fn
  resolve_path.py        # sandbox root + _resolve
  tools/                 # read.py, write.py, edit.py
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
`user >>`, `|Tools Used: \`name\`|`, and `{In} | {Out} | {elapsed}`.
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
  `old_text`=anchor, `new_text`=anchor+insertion). Partial changes
  (add/append/insert, replace X with Y) are `read` then `edit` — never
  `write` with partial content. The routing rule lives in `SYSTEM`, not in
  per-tool docstrings.
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
- `exit` / `quit` / `bye` leave before any `chat.completions.create` call.
- Paths resolve inside the sandbox; escapes and `.env` files are tool errors.
  Product workspace is the launch cwd, like Pi and OpenCode. The current
  default is the root-level `sandbox/` dir
  (`_sandbox_root()`: `Path(__file__).resolve().parents[2] / "sandbox"`,
  auto-created at startup, `--sandbox path` overrides it). That default is
  the dev fence so tool tests cannot overwrite harness source in `src/`.
  It is not the product rule. Point at a real repo today with
  `--sandbox <that repo>`. Do not flip the default to cwd in the model
  registry layer. `sandbox/` is gitignored. REPL prints `Sandbox: {SANDBOX}`
  once at startup, and the status block carries a `Sandbox: {SANDBOX}` line.
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
- REPL prompt is `user >> `. The answer prints as `minicode >> {answer}`.
  After a successful tool run, print `|Tools Used: `{name}`|`. Unknown tools
  stay silent on stdout. Status block after the answer, wrapped in `---`:
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

- Promote a deferred topic (shell, MCP, subagents, compaction, sessions,
  Rich, models.dev import …) into the current layer without an explicit ask.
- Add a feature without finishing it: unknown tools, escapes, and bad args
  must all behave before the layer is done.
- Send `exit`, secrets, or half-built scaffolding to the model.
- LiteLLM, or one SDK per provider. Transport is the `openai` package.
