# STATUS.md — MiniCode

Current code: layers 0–9 are committed. Layer 9 adds persistent sessions,
live resume, rename, delete, `/new`, background LLM titles, and session-scoped
`always` grants. Startup default is `plan`; `/new` keeps the current settings.
Plan drops `write` / `edit` only. `bash` / `powershell` stay in the list.
Shell asks for `.env` text, and in plan for content-read, create, and delete
verbs. Status line is `In | Out | Session | Elapsed: {_elapsed}`. Cost display
waits until more models are added.

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
  Not `model_dump`. Tool line is `|Tool Used: \`name\`|`. `SYSTEM`
  routes whole-file `write` vs one-span `edit`.
- [x] Observability: startup prints the status block with no usage line.
  The flag line is `Sandbox: {SANDBOX} | Thinking: {name} | Effort: {name} | Args: {name} | Output: {name}`.
- [x] `uv.lock` staged for commit (pins exact versions).
- [x] Dedicated `sandbox/` dir at the project root is the dev override:
  `uv run python -m minicode --sandbox sandbox` (`sandbox/` is gitignored).
  REPL startup + status block show the path.
- [x] Diff separators fixed: `end="---\n" if diff.endswith("\n") else
  "\n---\n"` — closing `---` always lands on its own line.

- [x] Layer 2: OpenAI client, `_SERVERS` registry, `/models`, raw message
  dict. Ids from `.env`. Bases in code. Startup default is `default_id`.
  Status elapsed is `_elapsed`, not raw seconds. No Tok/s. No LiteLLM.
- [x] Layer 3 (`docs/04-workspace.md`): default workspace is the launch cwd
  (`Path.cwd().resolve()` in `resolve_path.py`). `--sandbox path`
  overrides. Dev fence is `uv run python -m minicode --sandbox sandbox`.
- [x] Split under `src/minicode/`: REPL in `__main__.py`, loop in
  `agent.py`, `schema_generator.py`, `resolve_path.py`, `tools/`.
  Status is last prompt (`In`) + summed output tokens (`Out`) + `Session`
  + `_elapsed`. No Tok/s. Tool line is `|Tool Used: \`name\`|`.
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
  gates `write` and `edit`); `shell` allows except `.env` text and plan
  verbs; `external_directory` asks.
  `always` is exact and session-scoped. Plan keeps `write` / `edit` out of
  the schema; `bash` / `powershell` stay in and ask.
- [x] Absolute-path fix: `read` / `write` / `edit` / `glob` / `grep` path
  docs say absolute or workspace-relative; outside asks permission. `glob`
  and `grep` return absolute forward-slash paths for an outside root, and
  keep workspace-relative paths for an inside root. No more
  `relative_to(SANDBOX)` crash on an outside hit.
- [x] `SYSTEM` names the workspace, allows absolute paths, says a
  user-named file is read with `read`, gives the locate order, and names
  only the loaded shell. A new file is `write`, not the shell.
  `PLAN_SYSTEM` adds: if the user named a file, read that path; do not glob
  first. It also says not to create or delete files with the shell, and to
  tell the user to run `/build`.
- [x] Status line adds `Session`: conversation sum of `completion_tokens`.
  `In` and `Out` are unchanged. Prompt tokens are not added.
- [x] Elapsed rolls units via `_elapsed` in `__main__.py`. Under 60s, one
  decimal. Then two largest of `s m h d w y`. Week is 7 days. Year is 365
  days. No months.
- [x] On Windows, `classify` rewrites Git Bash `/d/...` to `D:/...` before
  the sandbox check. `/tmp` and `/home` stay as written. No rewrite on Unix.
- [x] Shell defaults to allow. Ask for `.env` reads, `.env` in a command,
  `external_directory`, and plan-mode content-read / create / delete verbs.
  `.env.example` stays allow. `glob` may list `.env` names. `grep` still
  skips their contents.
- [x] `README.md` — user install, configure, run, commands, tools,
  permissions, status line, troubleshooting, and limitations.
- [x] Plan prompt is loaded at startup, not only on a `/plan` transition.
  `/plan` and `/build` always assign `messages[0]`. `PLAN_SYSTEM` forbids
  pasting file contents and ends a create-or-change request with `/build`.
  A plan denial, a permission denial, and an unknown tool print that tool
  string. Still no `|Tool Used|` line for those.
- [x] A denied plan-mode shell ask returns a short `/build` sentence. The
  command stays in the prompt and is not copied into the tool string.
  The ask remains. Shell is not force-denied.
- [x] `*` matches a newline. A build-mode heredoc is allowed. A plan-mode
  heredoc still asks. A denied ask still returns the short `/build` sentence.
- [x] `docs/09-streaming.md` / Layer 8: streaming and Ctrl+C abort are
  implemented. Reasoning, when the provider sends it, prints inside a
  `Thinking:` / `---` / text / `---` block when `/thinking` is `on`. Default
  is `off`, which prints only `Thinking:`. Answer tokens stream as they
  arrive. There is no `minicode >>` prefix. `/effort` is `low`, `medium`, or
  `high`, default `low`. Gemini sends that as `thinking_level`. Ollama sends
  it as `reasoning_effort`. `<thought>` / `<think>` are
  display-only and are stripped before history.
- [x] `/args` and `/output` default to `off`. `/args off` prints only
  `|Tool Used: `{name}``. `/output off` hides the shell block. The model
  still gets that output. `/help` prints the `COMMANDS` tuple in
  `__main__.py`. A new slash command adds a handler and a row there.
- [x] Layer 9 (`docs/10-sessions.md`): `sessions.py`; session JSON under
  `~/.local/share/minicode/sessions/<project-key>/`; `/new`; live `/sessions`
  with resume, rename, and delete; LLM summary titles in a daemon thread;
  restored settings and `Session`; session-scoped `always`; atomic writes.
  No file at startup. No reasoning in the file.
- [x] `/new` prints the status block. Resume replays the transcript and
  prints the same last line as before, rebuilt from `last_turn`
  (`prompt_tokens`, `completion_tokens`, `Elapsed`). Any unmatched `/...`
  prints `Unknown command: ... Use /help.` and is not sent to the model.

## Open gaps

Known and accepted. These are not the next layer.

- No automated tests for `tool_from_fn`, the tools, or sessions; ad-hoc checks
  only.
- History is unbounded; compaction is deferred until the context gap hurts.
- `context_window` is `None`, so context `%` is off.
- Cache tokens in `usage` are not displayed.
- Sandbox is a path boundary, not a container; shell can `cd` out and
  inherits the process environment.
- Plan hides `write` / `edit` only. Shell stays in the list. Plan asks for
  content-read, create, and delete verbs, not for `ls` or `git`.
- No diff viewer.
- `AGENTS.md` is not injected into the system prompt.
- Cost display is deferred until more models are added.
- Answer tokens stream as they arrive. There is no `minicode >>` prefix.
  Gemini asks for a low thought summary. No `reasoning_effort`. A provider
  that sends no summary shows no thinking block.
- A click or middle-click paste into `input()` submits every newline as a
  request. On Windows, Ctrl+C does not abort a model call while httpx is
  blocked in Winsock `recv`. Both are deferred. The shape is an amendment
  to `docs/09-streaming.md`. Not next.

## Next

1. `docs/11-export.md`: transcript export only. No reasoning capture.

## Deferred (do not start)

A JSON permissions file (OpenCode-shaped rules, loaded at startup; a
configured `deny` beats `always`), cache
control, diff viewer, `AGENTS.md` injection, compaction (context gap
on a real codebase; do not start it), cost (until more models are added;
then pricing on the Model record), tests (still not written),
models.dev import, `/connect` (with that catalog; transport tag on the
tuple, not a client per brand; API key or OAuth; user `0600` auth file,
not project `.env`; not a key-only phase), variants (reasoning effort;
fetched with the catalog, not a create flag), `reasoning_effort` (Gemini
summaries use `include_thoughts` and `thinking_level: low`, not this flag),
Windows paste and a stuck Ctrl+C (amendment to `docs/09-streaming.md`, not
a new guide and not next: after `input()` returns, if the console already
has more lines, do not send them; on interrupt, `FlushConsoleInputBuffer`;
run the stream on a worker and `time.sleep` on the main thread so Ctrl+C
can close the httpx stream; a second Ctrl+C calls `os._exit`. No TUI, no
asyncio, no short read timeout, no `prompt_toolkit`).
