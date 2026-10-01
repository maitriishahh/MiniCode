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
- [x] `docs/00-setup.md` — venv, `.env`, Gemini reachable. Guide now
  targets the OpenAI client.
- [x] `docs/01-loop.md` / Layer 0: loop in `agent.py`, REPL in
  `__main__.py`. Status is `In | Out | Elapsed: {elapsed:.1f}s`. No Tok/s.
- [x] `docs/02-file-tools.md` / Layer 1: `write` and `edit` in `tools/`.
  Registry in `agent.py`.
- [x] History is the raw assistant message dict from the response JSON.
  Not `model_dump`. Tool line is `|Tools Used: \`name\`|`. `SYSTEM`
  routes whole-file `write` vs one-span `edit`.
- [x] Observability: REPL prints `Sandbox: {SANDBOX}` at startup; status
  block carries a `Sandbox: {SANDBOX}` line.
- [x] `uv.lock` staged for commit (pins exact versions).
- [x] Dedicated `sandbox/` dir at the project root: `_sandbox_root()`
  (`Path(__file__).resolve().parents[2] / "sandbox"`, auto-created,
  `--sandbox path` overrides). This is the **dev fence**, not the product
  workspace: tool tests must not overwrite harness source in `src/`.
  Product intent (Pi/OpenCode) is the launch cwd. A real repo today is
  `--sandbox <that repo>`. `sandbox/` is gitignored; REPL startup + status
  block show the path.
- [x] Diff separators fixed: `end="---\n" if diff.endswith("\n") else
  "\n---\n"` — closing `---` always lands on its own line.

- [x] Layer 2: OpenAI client, `_SERVERS` registry, `/model`, raw message
  dict. Ids from `.env`. Bases in code. Startup default is `default_id`.
  Status elapsed is `Elapsed: {elapsed:.1f}s`. No Tok/s. No LiteLLM.
- [x] Split under `src/minicode/`: REPL in `__main__.py`, loop in
  `agent.py`, `schema_generator.py`, `resolve_path.py`, `tools/`.
  Status is last prompt (`In`) + summed output tokens (`Out`) + elapsed
  seconds. No Tok/s. Tool line is `|Tools Used: \`name\`|`.
- [x] `edit` returns a numbered window to the model (changed span, up to 5
  lines before and after). Diff stays stdout-only.

## Next

1. `docs/04-workspace.md` is written, not implemented. Implement it next
   into `src/minicode/resolve_path.py` only: default workspace becomes the
   launch cwd, `--sandbox path` stays as the override. Dev fence is
   `uv run python -m minicode --sandbox sandbox`. Do not touch the
   registry. Then update `AGENTS.md` + `HARNESS_RESEARCH_AND_PLAN.md` §5
   in that same pass.
2. Then write the search-tool guide (`grep` or `find`, capped). Not a
   shell. Do not implement it in the workspace pass.

## Deferred (do not start)

shell, plan/build swap, permissions, streaming/abort, sessions, cache
control, cost, diff viewer, `AGENTS.md` injection, tests (with
`tool_from_fn`), README, models.dev import, `/connect`, variants.
