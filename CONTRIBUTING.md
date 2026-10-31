# Contributing

A change is finished when the code, the doc, and the changelog say the same
thing. `docs/STYLE.md` is the convention. An agent working in this repository
reads `AGENTS.md` first.

## Setup

`README.md` for install, `docs/setup.md` for the failure modes. Run with
`uv run`. Add a dependency with `uv add`, never `pip install`. `uv.lock` is
committed and pins exact versions.

## Before the code

If the change is a new choice, add a numbered decision to `DESIGN.md`. Do not
edit a decision that is still in force; mark it `superseded by D<n>` and append
the replacement. Name the next piece of work in `docs/STATUS.md` before writing
code. Do not start an item in `DESIGN.md` ## Deferred unless the trigger there
has been met, or the user asked for it.

## In the same commit as the behaviour

1. The feature doc's `## Contract`, for the subsystem you touched.
2. A `CHANGELOG.md` bullet under `[Unreleased]`, one user-visible change, past
   tense. A refactor that changes no behaviour gets no bullet.
3. A `README.md` commands-table row, and any other user-facing command, flag,
   output, or default that changed.
4. `docs/STATUS.md`, only if what is next moved.
5. `docs/index.md`, only if the doc set changed.

A new slash command is a handler in `__main__.py` before any model call, one
row in `COMMANDS`, and one README row. `/help` prints `COMMANDS` only. Do not
write a second help string, and do not generate the handlers from the tuple.

Commit messages are an imperative sentence, with no type prefix.
`Add persistent sessions with resume and titles`, not `feat: sessions`.

## Checking it

`## Verification` in the feature doc is the test suite. Run it when you edit
the doc, then update `Verified:`. If a step cannot be run, say so in the doc
rather than deleting it.

Do not commit `.env`, session dumps, or transcripts. Do not commit secrets.
Contributions are under the Apache-2.0 license in `LICENSE`, unless a
contribution says otherwise.
