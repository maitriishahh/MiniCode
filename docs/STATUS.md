# STATUS.md — MiniCode

Current code: layers 0–7 are in. Startup default is `plan`. Plan drops
`write` / `edit` only. `bash` / `powershell` stay in the list and ask.
Status line is `In | Out | Session | Elapsed: {_elapsed}`. Next is the
streaming guide. Cost display waits until more models are added.

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
  `__main__.py`. Live status is `In | Out | Session | Elapsed: {_elapsed}`. No Tok/s.
- [x] `docs/02-file-tools.md` / Layer 1: `write` and `edit` in `tools/`.
  Registry in `agent.py`.
- [x] History is the raw assistant message dict from the response JSON.
  Not `model_dump`. Tool line is `|Tools Used: \`name\`|`. `SYSTEM`
  routes whole-file `write` vs one-span `edit`.
- [x] Observability: REPL prints `Sandbox: {SANDBOX}` at startup; status
  block carries a `Sandbox: {SANDBOX}` line.
- [x] `uv.lock` staged for commit (pins exact versions).
- [x] Dedicated `sandbox/` dir at the project root is the dev override:
  `uv run python -m minicode --sandbox sandbox` (`sandbox/` is gitignored).
  REPL startup + status block show the path.
- [x] Diff separators fixed: `end="---\n" if diff.endswith("\n") else
  "\n---\n"` — closing `---` always lands on its own line.

- [x] Layer 2: OpenAI client, `_SERVERS` registry, `/model`, raw message
  dict. Ids from `.env`. Bases in code. Startup default is `default_id`.
  Status elapsed is `_elapsed`, not raw seconds. No Tok/s. No LiteLLM.
- [x] Layer 3 (`docs/04-workspace.md`): default workspace is the launch cwd
  (`Path.cwd().resolve()` in `resolve_path.py`). `--sandbox path`
  overrides. Dev fence is `uv run python -m minicode --sandbox sandbox`.
- [x] Split under `src/minicode/`: REPL in `__main__.py`, loop in
  `agent.py`, `schema_generator.py`, `resolve_path.py`, `tools/`.
  Status is last prompt (`In`) + summed output tokens (`Out`) + `Session`
  + `_elapsed`. No Tok/s. Tool line is `|Tools Used: \`name\`|`.
- [x] `edit` returns a numbered window to the model (changed span, up to 5
  lines before and after). Diff stays stdout-only.
- [x] Layer 4 (`docs/05-search.md`): `glob` and `grep` in `tools/`. Capped
  at 50, `.env*` omitted, non-directory root is a tool error. Registry is
  wired. `SYSTEM` has the locate sentence as its own sentence. Shell is
  layer 6.
- [x] Layer 5 (`docs/06-plan-build.md`): `/plan` and `/build` on one
  session. Startup default is `plan`. Plan drops `write`/`edit` from
  `tools=` and denies them at dispatch. `TOOLS` stays full. History is
  not rewritten. `MAX_STEPS` is `16`. Shell is layer 6.
- [x] Layer 6 (`docs/07-shell.md`): `shell` in `tools/shell.py`. Windows:
  Git Bash, then PowerShell. Unix: bash, then `sh`. Registered name is
  `bash` or `powershell`. This layer denied both in plan. Layer 7 puts
  them back and adds permissions. `cwd` is `SANDBOX`.
- [x] Layer 7 (`docs/08-permissions.md`): `permissions.py`, dispatch gate,
  and the `ask` prompt. `read` / `glob` / `grep` / `edit` allow (`edit`
  gates `write` and `edit`); `shell` asks; `external_directory` asks.
  `always` is in-memory and exact. Plan keeps `write` / `edit` out of the
  schema; `bash` / `powershell` stay in and ask.
- [x] Absolute-path fix: `read` / `write` / `edit` / `glob` / `grep` path
  docs say absolute or workspace-relative; outside asks permission. `glob`
  and `grep` return absolute forward-slash paths for an outside root, and
  keep workspace-relative paths for an inside root. No more
  `relative_to(SANDBOX)` crash on an outside hit.
- [x] `SYSTEM` names the workspace, allows absolute paths, says a
  user-named file is read with `read`, gives the locate order, and names
  only the loaded shell. `PLAN_SYSTEM` adds: if the user named a file, read
  that path; do not glob first.
- [x] Status line adds `Session`: process sum of `completion_tokens`.
  `In` and `Out` are unchanged. Prompt tokens are not added.
- [x] Elapsed rolls units via `_elapsed` in `__main__.py`. Under 60s, one
  decimal. Then two largest of `s m h d w y`. Week is 7 days. Year is 365
  days. No months.
- [x] On Windows, `classify` rewrites Git Bash `/d/...` to `D:/...` before
  the sandbox check. `/tmp` and `/home` stay as written. No rewrite on Unix.
- [x] `README.md` — user install, configure, run, commands, tools,
  permissions, status line, troubleshooting, and limitations.

## Open gaps

Known and accepted. These are not the next layer.

- No tests for `tool_from_fn` or the tools.
- History is unbounded; compaction is deferred until the context gap hurts.
- No streaming/abort. Ctrl+C during a model or shell call ends the REPL.
- `context_window` is `None`, so context `%` is off.
- Cache tokens in `usage` are not displayed.
- Sandbox is a path boundary, not a container; shell can `cd` out and
  inherits the process environment.
- Plan hides `write` / `edit` only; shell stays in the tool list and asks.
- `always` approvals are in-memory only.
- No diff viewer.
- `AGENTS.md` is not injected into the system prompt.
- Cost display is deferred until more models are added.

## Next

1. Write the streaming/abort guide. Do not implement it in that pass.
   Not sessions.

## Deferred (do not start)

streaming/abort, sessions, cache
control, diff viewer, `AGENTS.md` injection, compaction (context gap
on a real codebase; do not start it), cost (until more models are added;
then pricing on the Model record), tests (still not written),
models.dev import, `/connect` (with that catalog; transport tag on the
tuple, not a client per brand; API key or OAuth; user `0600` auth file,
not project `.env`; not a key-only phase), variants (reasoning effort;
fetched with the catalog, not a create flag).
