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
- [x] `docs/02-file-tools.md` / Layer 1: `write`, `edit`, one-shot
  unified diff — implemented in `__main__.py`.
- [x] Hardening pass on the loop: assistant history stored as
  `msg.model_dump(exclude_none=True)` dicts (fixes Pydantic
  `PydanticSerializationUnexpectedValue` warnings on tool-call turns);
  `SYSTEM` routes `write` (whole-file create/overwrite) vs `edit`
  (one exact unique span, `read` first for partial changes; add/append
  preserves existing content); diff headers `a/{path} (before)` /
  `b/{path} (after)` printed as `---\nDiff: {path}\n{diff}---`;
  per-tool `---\nTools Used: \`name\`\n---` line and `---`-wrapped answer.
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

- [x] `docs/03-models.md` — Layer 2 guide (model record, `/model`, Gemini
  + one `ollama_chat/` entry). Not implemented in `__main__.py` yet.

## Next

1. Implement `docs/03-models.md` into `src/minicode/__main__.py`
   (registry, `/model`, active-record `completion()` kwargs). Do not
   change `SANDBOX` in that pass.
2. Then flip the default workspace from the dev `sandbox/` fence to the
   launch cwd (product behavior, Pi/OpenCode). Keep `--sandbox path`.
3. Then one capped search tool (`grep` or `find`). Not a shell.

## Deferred (do not start)

shell, plan/build swap, permissions, streaming/abort, sessions, cache
control, cost, diff viewer, `AGENTS.md` injection, tests (with
`tool_from_fn`), README, models.dev import, `/connect`, variants.
