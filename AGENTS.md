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

A minimal coding agent: hand-written tool loop over LiteLLM, `read` / `write`
/ `edit` inside a sandbox, plan and build as separate modes, a small model
registry, and a REPL status line. Few features, each finished.

## Stack (only these)

| Role | Choice |
|---|---|
| LLM transport | LiteLLM Python SDK, one `completion()` call |
| Validation | `pydantic` (`create_model` in `tool_from_fn`) |
| Env | `python-dotenv`, `.env` from `.env.example` (never commit `.env`) |
| Python | ≥3.13, managed with **uv** |

Not in the project: LangGraph, LangChain, deepagents, LlamaIndex, Rich /
Textual (yet), pi-agent-core (read-only reference).

## Layout

```
src/minicode/    # the harness; starts as one growing module
docs/            # STATUS + setup + one build guide per layer
.env.example     # copy to .env
```

Do not invent empty package dirs (`llm/`, `core/`, `session/`, `ui/` …).
Split `src/minicode` only when the file is awkward — same functions.

## Conventions (do not break)

- Growing file: each guide says keep / add / replace. The loop shape in
  `HARNESS_RESEARCH_AND_PLAN.md` §1 is fixed — user appended once in the
  REPL, assistant appended once per reply, one `role: "tool"` per call.
  History stores plain dicts only: the assistant message is appended as
  `msg.model_dump(exclude_none=True)`, never the raw LiteLLM `Message`
  object (raw objects trigger Pydantic `PydanticSerializationUnexpectedValue`
  warnings on the next `completion()` when `tool_calls` are present).
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
  `lineterm="\n"`, printed as `---\nDiff: {path}\n{diff}` with
  `end="---\n" if diff.endswith("\n") else "\n---\n"` so the closing `---`
  always lands on its own line and never fuses with the next block.
  The model only gets `Replaced 1 occurrence in {path}`.
- Validation errors and tool failures return as `role: "tool"` strings. Tool
  code never raises out of the loop. `max_steps` returns a message, never
  raises.
- `exit` / `quit` leave before any `completion()` call.
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
- `load_dotenv()` runs before importing LiteLLM. `LITELLM_LOG=ERROR` in
  `.env` quiets its Gemini sampling notice.
- Model id: `os.getenv("GEMINI_MODEL")` with no Python default — `.env`
  supplies it (`GEMINI_MODEL=gemini/gemini-3.5-flash-lite`). Pass
  `api_key=os.getenv("GEMINI_API_KEY")` into every `completion()` call.
- REPL prompt is `minicode >> `. After a successful tool run, print
  `---\nTools Used: `{name}`\n---`. Unknown tools stay silent on stdout.
  The model answer prints wrapped in `---` separators. Status block after the
  answer: Model / Mode / Tools Loaded, then `{tokens:,} Tokens | {tok/s:.4f} Tok/s`
- `last_usage` resets to 0 at the start of each `run_agent` turn and
  **sums** `resp.usage.total_tokens` across steps. Status block after the
  answer: Model / Mode / Tools, then `{tokens:,} Tokens | {tok/s:.4f} Tok/s`
  (Tok/s = turn tokens / wall clock of `run_agent`, `0.0` if elapsed is 0).
- Never bare `pip install`. Deps via `uv add`; run with `uv run`.
  `uv.lock` is committed (pins exact versions).
- Do not commit secrets, session dumps, or transcripts.

## Do not

- Promote a deferred topic (shell, MCP, subagents, compaction, sessions,
  Rich, models.dev import …) into the current layer without an explicit ask.
- Add a feature without finishing it: unknown tools, escapes, and bad args
  must all behave before the layer is done.
- Send `exit`, secrets, or half-built scaffolding to the model.
