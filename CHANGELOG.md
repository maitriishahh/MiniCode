# Changelog

All notable changes to MiniCode are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Entries are grouped by release and then by type; within a release the order is
the order the work landed.

## [Unreleased]

### Added

- `CHANGELOG.md`, `docs/STYLE.md`, and the Apache-2.0 `LICENSE`.
- Developer documentation: `DESIGN.md`, `docs/architecture.md`,
  `docs/observability.md`, `docs/commands.md`, and one reference doc per
  feature.

### Changed

- Documentation rewritten from per-layer build guides into developer docs that
  describe the shipped system. The build guides are archived unchanged under
  `docs/archive/build-guides/`.
- `HARNESS_RESEARCH_AND_PLAN.md` renamed to `DESIGN.md`. Decisions are numbered.
  The reliability rules and the source list are unchanged.

## [0.1.0] - 2026-10-30

First usable release. Everything below is the accumulated result of layers 0
through 10.

### Added

- **Agent loop.** One hand-written synchronous loop over the `openai` client.
  A turn runs up to 16 model steps. The REPL appends the user message once; the
  loop appends one assistant message per reply and one `role: "tool"` message
  per call.
- **Tool registry.** `tool_from_fn` turns an ordinary function with a
  Google-style docstring and type hints into a JSON schema plus a
  `pydantic.create_model` validator. Bad arguments from the model come back as
  tool output, not exceptions.
- **File tools.** `read` (line-numbered, `offset`/`limit`), `write` (create or
  full rewrite), and `edit` (one exact unique span, with an insert-only form).
- **Search tools.** `glob` and `grep`, both capped at 50 results, both skipping
  dot-directories, `__pycache__`, `.venv`, and `.env` contents.
- **Shell tool.** One function resolved at import. Windows prefers Git Bash,
  then PowerShell; Unix prefers `bash`, then `sh`. The registered tool name is
  the winner, so the model never speaks bash into PowerShell.
- **Model registry.** `_SERVERS` tuples, ids from `.env`, base URLs in code,
  `/models` to list and switch. Gemini and Ollama out of the box.
- **Workspace.** The launch directory by default, `--sandbox path` to override,
  auto-created at startup. Paths may be absolute or workspace-relative.
- **Plan and build modes.** One conversation, two tool lists. Plan drops
  `write` and `edit` from the schema and refuses them at dispatch; build offers
  everything.
- **Permissions.** `allow` / `ask` / `deny` rules, last match wins, `*` matches
  any character including `/` and newlines. A prompt offers `once` / `always` /
  `deny`; `always` is exact and session-scoped.
- **Streaming.** Answer tokens stream as they arrive. Model reasoning prints
  inside a `Thinking:` / `---` block when the provider sends it and `/thinking`
  is `on`.
- **Abort.** Ctrl+C during a model call, a tool call, or a permission prompt
  returns to the prompt with a coherent history.
- **Display commands.** `/thinking`, `/effort`, `/args`, `/output`, `/help`.
- **Persistent sessions.** One JSON file per conversation under the user data
  directory, keyed by workspace. `/sessions` lists, resumes, renames, and
  deletes; `/new` starts a clean one.
- **Session titles.** A background daemon thread asks the active model for a
  2-5 word title after the first message. A local fallback is used if the call
  fails or is slow.
- **Export.** `/export` writes the conversation as plain text, with a default
  filename derived from the session title.
- **Status block.** Model, mode, loaded tools, sandbox, display flags, and
  `In | Out | Session | Elapsed` after every turn, at startup, and on resume.
- **Documentation.** `README.md` as the user guide, `AGENTS.md` as the working
  convention, `HARNESS_RESEARCH_AND_PLAN.md` as the design record, and one
  build guide per layer under `docs/`.

### Changed

- Transport moved from LiteLLM to the `openai` package with one
  `chat.completions.create` site. Server selection is a base URL, not a
  provider prefix.
- Model ids lost their `gemini/` and `ollama_chat/` prefixes.
- `/model` was renamed to `/models`.
- Startup default mode became `plan`; `/new` resets to `plan`.
- The default workspace moved from a repository-local `sandbox/` directory to
  the launch directory. `sandbox/` survives as the development fence:
  `uv run python -m minicode --sandbox sandbox`.
- Status line gained `Session` (conversation-lifetime output tokens) and lost
  any notion of tokens per second.
- Elapsed time rolls into the two largest of `s`, `m`, `h`, `d`, `w`, `y`
  instead of printing raw seconds.
- The tool line became `|Tool Used: \`name\`` and hides arguments by default.
- Shell output is hidden by default; the model still receives it.
- Model reasoning is display-only: `<thought>` and `<think>` spans are stripped
  before anything reaches history.
- The `Thought:` closer was removed; the thinking block closes with `---`.
- Session timestamps became local `DD-MM-YYYY HH:MM` strings, and `/sessions`
  sorts newest first by id.
- `/plan` and `/build` always rewrite the system prompt, even when the requested
  mode is already active.
- Layer 6 denied both shell tools in plan mode. Layer 7 put them back and
  restricted them with rules instead, because a tool-list deny is not a
  substitute for a permission check.

### Fixed

- A bad tool call, an unknown tool, a missing file, or a validation error
  returns a string to the model instead of raising out of the loop.
- `max_steps` returns an actionable message instead of raising.
- `glob` and `grep` no longer crash on a root outside the workspace. An outside
  root returns absolute forward-slash paths; an inside root stays relative.
- On Windows, Git Bash drive paths such as `/d/projects/app` are rewritten to
  `D:/projects/app` before the workspace check.
- The `edit` diff no longer fuses its closing `---` with the following output.
- A denied plan-mode shell prompt returns a short sentence telling the user to
  run `/build`, instead of echoing the command.
- Session creation timestamps, the sessions root path, and the status line
  restored by resume.
- A resumed session replays its transcript and rebuilds the last status line
  from the saved turn.
- Any unmatched `/...` input prints `Unknown command: ... Use /help.` instead of
  being sent to the model.
- The plan prompt is loaded at startup, not only after a `/plan` transition.
- The `/help` summary for `/new` said current settings are kept. The handler
  has always reset every setting to its startup default; the text now says so.
