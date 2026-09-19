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

## Next

1. `docs/00-setup.md` — create the venv, `.env`, verify LiteLLM reaches
   Gemini. No agent code yet.
2. `docs/01-loop.md` — write `../src` Layer 0: clean loop,
   `tool_from_fn`, sandbox, `read`, REPL + status line.
3. Then write `docs/02-file-tools.md` (`write`, `edit`, diff print).
4. Then write `docs/03-models.md` (Model registry, `/model`, one local or
   OpenAI-compat endpoint).

## Deferred (do not start)

shell, plan/build swap, permissions, streaming/abort, sessions, cache
control, cost, diff viewer, `AGENTS.md` injection, tests (with
`tool_from_fn`), README.
