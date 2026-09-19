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
- Tool functions use Google-style docstrings (first line = description,
  `Args:` = parameter docs). `tool_from_fn` compiles schema + validation.
- Validation errors and tool failures return as `role: "tool"` strings. Tool
  code never raises out of the loop. `max_steps` returns a message, never
  raises.
- `exit` / `quit` leave before any `completion()` call.
- Paths resolve inside the sandbox; escapes and `.env` files are tool errors.
- `load_dotenv()` runs before importing LiteLLM. `LITELLM_LOG=ERROR` in
  `.env` quiets its Gemini sampling notice.
- Default model: `os.getenv("GEMINI_MODEL", "gemini/gemini-3.5-flash-lite")`
  with `api_key=os.getenv("GEMINI_API_KEY")` passed into every call.
- Never bare `pip install`. Deps via `uv add`; run with `uv run`.
- Do not commit secrets, session dumps, or transcripts.

## Do not

- Promote a deferred topic (shell, MCP, subagents, compaction, sessions,
  Rich, models.dev import …) into the current layer without an explicit ask.
- Add a feature without finishing it: unknown tools, escapes, and bad args
  must all behave before the layer is done.
- Send `exit`, secrets, or half-built scaffolding to the model.
