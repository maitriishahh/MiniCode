# Documentation style

This file is the convention. Read it before writing or changing any document in
this repository. If a document and this file disagree, this file wins until one
of them is fixed.

## What a MiniCode doc is

A document describes what the system does **now**, why it is shaped that way,
and how to check that it still is. It is a record, not an instruction manual for
a past session.

The build guides under `docs/archive/build-guides/` are the exception. They are
frozen history. Do not edit them, do not link them from `docs/index.md`, and do
not copy code out of them.

## Audiences

| Reader | Files |
|---|---|
| Someone installing and running MiniCode | `README.md`, `docs/setup.md` |
| Someone changing the code | `DESIGN.md`, `docs/architecture.md`, one feature doc per subsystem |
| An agent working in this repository | `AGENTS.md`, `docs/STATUS.md`, this file |
| Someone asking what changed | `CHANGELOG.md` |

## One fact, one owner

A fact lives in exactly one file. Anywhere else it may appear only as a
one-line pointer to the owner.

| Fact | Owner |
|---|---|
| Install, first run, requirements | `README.md`, `docs/setup.md` |
| Turn loop, step limit, message flow | `docs/loop.md` |
| Module map, imports, callback edges | `docs/architecture.md` |
| Docstring-to-schema contract | `docs/tool-registry.md` |
| `read` / `write` / `edit` | `docs/file-tools.md` |
| `glob` / `grep` | `docs/search.md` |
| Shell resolution and execution | `docs/shell.md` |
| Model registry, `_create`, `/models` | `docs/models.md` |
| Workspace root, path classification | `docs/workspace.md` |
| Plan and build modes | `docs/modes.md` |
| Permission keys, rules, prompt | `docs/permissions.md` |
| Streaming and abort | `docs/streaming.md` |
| Status block, tool line, display flags | `docs/observability.md` |
| Session file schema and paths | `docs/sessions.md` |
| `/export` | `docs/export.md` |
| Command list and exact output | `docs/commands.md` |
| Why a decision was made | `DESIGN.md` |
| What changed, by release | `CHANGELOG.md` |
| What is next and what is deferred | `docs/STATUS.md`, `DESIGN.md` |

## Template

```markdown
# <Feature>

**Status:** shipped · **Layer:** <n> · **Files:** `<path>`, `<path>`
**Verified:** <YYYY-MM-DD>

One paragraph. What this is, present tense, no history.

## Contract

Behaviour that must not change. Exact strings, exact defaults. Tables.

## Why this shape

The decision, the alternative it beat, named (OpenCode / Pi / Claude Code /
Aider), and the mechanism that makes the difference.

## Invariants

- One bullet per thing that breaks if it changes. Name the file and function.

## Edge cases

| Input | Result |

## Verification

The manual checks that prove the contract still holds. Run them when you edit
the doc, then update `Verified:`.

## Gaps

- Known limitation, and the trigger that would make it worth fixing.

## History

Only when a shipped choice changed. Oldest first. `YYYY-MM-DD  what, and what
it replaced.`
```

`Status:` is `shipped` or `partial`. Planned work never gets a doc; it lives in
`docs/STATUS.md` until it ships.

## Rules

1. **A doc may only describe behaviour that exists in `src/` today.** Planned
   behaviour belongs in `docs/STATUS.md` or `DESIGN.md`. This rule exists
   because it is the one that was broken: the archived guides print
   `minicode >>` and `user >>` prompts that the code stopped emitting.
2. **Present tense for behaviour, past tense only under `## History`.**
3. **No build instructions.** No `Segment N`, `What you'll build`, `Checkpoint`,
   `Do first`, `Don't add yet`, or "paste this into". Those are tutorial
   devices, and they rot the moment the code moves.
4. **Code blocks are excerpts of real code.** If a line is not in `src/`, it
   does not go in a code block. A proposed function goes under `## Gaps` as
   prose or in `DESIGN.md`.
5. **Name the symbol.** Every behavioural claim points at where it lives:
   `agent._create`, `permissions.decide`, `sessions.save`.
6. **Exact strings go in `## Contract`,** verbatim including punctuation and
   backticks. `Permission denied: {key} {value}`, not "a permission error".
7. **Prohibitions live in `AGENTS.md`,** never in a feature doc. A feature doc
   states what happens; `AGENTS.md` states what must not be built.
8. **Dates appear only** in `## History`, `CHANGELOG.md`, and `Verified:`.
9. **A shipped decision is never edited.** To change one, add a numbered entry
   to `DESIGN.md` and mark the old one `Superseded by D<n>`. The old entry keeps
   its original conclusion.
10. **`docs/<feature>.md` ≤ 250 lines, `docs/STATUS.md` ≤ 60.** Longer means it
    is two docs, or the doc is carrying history that belongs in `CHANGELOG.md`.

## Files, headings, links

- Lowercase, hyphenated, one topic per file. No numeric prefixes: numbers encode
  a reading order, and these docs are reference, not a course.
- `docs/index.md` is the only map. Every doc is linked there exactly once.
- `##` headings in the order given by the template. `###` for sub-topics.
- Relative links only. No absolute GitHub URLs for in-repo files.
- A rename updates every inbound link in the same commit. `docs/` cross
  references run over seventy deep; there is no "fix links later".
- Reference an anchor as `docs/streaming.md#event-contract`. Anchor text must
  match a real heading, lowercased, spaces to hyphens.

## One commit, one truth

A commit that changes behaviour updates, in that same commit:

1. the affected feature doc's `## Contract`;
2. a `CHANGELOG.md` bullet under `[Unreleased]`;
3. `README.md` if a user-facing command, flag, output, or default changed;
4. `docs/STATUS.md` only if the layer state or the next item moved;
5. `docs/index.md` only if the doc set changed.

Commit messages stay in the existing style: an imperative sentence, no type
prefix. `Add persistent sessions with resume and titles`, not `feat: sessions`.

## Changelog

- [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) headings:
  `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`.
- Version headings are `## [x.y.z] - YYYY-MM-DD`. Unreleased work accumulates
  under `## [Unreleased]`.
- A bullet is one user-visible change, in past tense, naming the thing.
- Internal refactors that change no behaviour do not get a bullet.
- Compare links are added when a version is tagged. Until then the headings
  stand alone, so no link dangles.

## Decisions

`DESIGN.md` holds numbered decisions `D1`, `D2`, … Each has a status line, the
decision, the alternative it beat, and the consequence.

- Append. Never renumber.
- A decision that is replaced gets `**Status:** superseded by D<n>` and keeps
  its text. The replacement says what it supersedes.
- A decision that is still in force is `**Status:** active`.
- `docs/STATUS.md` names the next piece of work. `DESIGN.md ## Deferred` names
  everything deliberately not being built, each with the trigger that would
  promote it.

## Verification discipline

`## Verification` replaces the old `## Soak` sections. It is the closest thing
this repository has to a test suite, and it is the only reason to trust a doc.

- Run the list when you edit the doc. Not later.
- Update `Verified:` with the date you ran it.
- If a step cannot be run (no key, no Ollama, no second OS), say so in the doc
  rather than deleting the step. An untested step is information.
