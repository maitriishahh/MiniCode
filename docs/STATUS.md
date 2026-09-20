# STATUS.md — MiniCode

## Done

- [x] Research pass: Pi design posts, Pi session/compaction docs, OpenCode
  providers/Zen/config/models/agents/permissions docs, LiteLLM function
  calling + Ollama + OpenAI-compatible docs, Ronacher agent notes,
  AgenticRoadmap guide structure.
- [x] Final plan: `HARNESS_RESEARCH_AND_PLAN.md` rewritten (loop, model
  registry, sandbox, plan/build, observability, layers).
- [x] Session files: `AGENTS.md`, this STATUS, `docs/00-setup.md`,
  `docs/01-loop.md`, `.env.example`, `.gitignore`.
- [x] `docs/00-setup.md` — venv, `.env`, LiteLLM reaches Gemini.
- [x] `docs/01-loop.md` / Layer 0: `src/minicode/__main__.py` — clean loop,
  `tool_from_fn`, sandbox, `read`, REPL, tool-executed line, status block
  (model / mode / tools / summed tokens / Tok/s).
- [x] `docs/02-file-tools.md` — Layer 1 guide (`write`, `edit`, one-shot
  unified diff). Not implemented in `__main__.py` yet.

## Next

1. Implement `docs/02-file-tools.md` into `src/minicode/__main__.py`
   (`write`, `edit`, diff print, registry).
2. Then write `docs/03-models.md` (Model registry, `/model`, one local or
   OpenAI-compat endpoint).

## Deferred (do not start)

shell, plan/build swap, permissions, streaming/abort, sessions, cache
control, cost, diff viewer, `AGENTS.md` injection, tests (with
`tool_from_fn`), README.
