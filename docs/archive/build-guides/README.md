# Build guides (frozen)

Twelve guides, `00-setup.md` through `11-export.md`, written one per layer while
the harness was being built. They are **history**, not documentation.

- **Frozen.** The text is exactly what shipped on the day it shipped. It is not
  edited, corrected, or brought up to date — a guide that says `/model` or
  `minicode >>` is describing the code at the time, not the code today.
- **Not linked from `docs/index.md`.** The live docs are the reference; these are
  here so the reasoning, the alternatives considered, and the manual checks are
  not lost.
- **Do not copy code out of them.** A snippet here is a snapshot from a past
  commit and may no longer be in `src/`. The live code is the only source.
- **`docs/NN-*.md` references inside them point to this directory.** They were
  written when every guide lived in `docs/`; the table below maps each one to the
  live doc that replaced it.

The convention these guides follow is retired; `docs/STYLE.md` is the current
one. What survived from them is in `CHANGELOG.md` (what changed, by release) and
in each live doc's `## Why this shape` and `## History` sections.

## Where each guide's content went

| Guide | Title when frozen | Live doc |
|---|---|---|
| `00-setup.md` | Setup | `docs/setup.md` |
| `01-loop.md` | Loop + sandbox + read + status | `docs/loop.md`, `docs/workspace.md`, `docs/observability.md` |
| `02-file-tools.md` | write + edit + diff print | `docs/file-tools.md` |
| `03-models.md` | Model registry + `/models` | `docs/models.md` |
| `04-workspace.md` | Workspace flip to launch cwd | `docs/workspace.md` |
| `05-search.md` | Search: glob + grep, capped | `docs/search.md` |
| `06-plan-build.md` | Plan/build swap (tool-list swap) | `docs/modes.md` |
| `07-shell.md` | Shell | `docs/shell.md` |
| `08-permissions.md` | Permissions | `docs/permissions.md` |
| `09-streaming.md` | Streaming and abort | `docs/streaming.md` |
| `10-sessions.md` | Sessions | `docs/sessions.md` |
| `11-export.md` | Export | `docs/export.md` |
