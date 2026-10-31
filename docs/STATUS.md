# Status

Layers 0–10 are shipped. Each contract is its feature doc under `docs/`.
Why a choice was made is `DESIGN.md`. What changed by release is
`CHANGELOG.md`.

Startup is plan. `/build` enables `write` and `edit`. The shell stays in both
modes and asks for `.env` text, and in plan for a command that reads, creates,
or deletes. Sessions, titles, `/export`, streaming, and abort are in. No
reasoning is stored. No Tok/s. No cost.

## Next

1. `docs/cache.md` — cache control. Display cache-read tokens when `usage`
   reports them. Do not rewrite history; the prompt prefix stays
   byte-identical (`DESIGN.md` D16). Not a second provider's cache code until
   one is actually needed.

## Deferred

Do not start these. The trigger for each is in `DESIGN.md` ## Deferred. The
order after cache control, for the three that have one, is a diff viewer, then
`AGENTS.md` injection. Cost is not in that chain. Compaction is not next.
`/connect` is not in that chain.

- Diff viewer. `AGENTS.md` injection.
- Compaction, when the context gap hurts on a real codebase.
- Cost display, when more models exist and the record can carry pricing.
- Tests. Still not written. Ad-hoc checks only.
- A JSON permissions file, where a configured `deny` beats `always`. Not next.
- models.dev import, `/connect`, the transport tag, and variants. One phase.
  Not a key-only command, and not an SDK per brand.
- Windows paste and a stuck Ctrl+C. An amendment to `docs/streaming.md`, not a
  new doc and not next. No `prompt_toolkit`, no asyncio, no short read timeout.
- MCP, subagents, skills, LSP, background bash, Rich, a web UI, a JSONL session
  tree, containerization, env scrubbing, LangGraph, LlamaIndex.
- Groq, only when asked: one `_SERVERS` tuple and two env lines. No OpenCode
  Console free model.

## Accepted limits

- `context_window` is unset, so context `%` stays off. Do not invent the number.
- The workspace is a path boundary. A shell command can `cd` out and inherits
  the environment.
- Plan hides `write` and `edit` only. `python -c` can still write.
