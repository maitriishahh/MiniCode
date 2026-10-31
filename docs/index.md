# Documentation

The map. Each document is linked here once. The frozen build guides under
`docs/archive/build-guides/` are history; they are not part of this map.

## Using MiniCode

| Doc | What it is |
|---|---|
| [README](../README.md) | Install, commands, and the status line. |
| [Setup](setup.md) | Requirements, `.env`, and how a failed first run looks. |
| [Commands](commands.md) | Every command, and the exact text it prints. |

## The system

| Doc | What it is |
|---|---|
| [Design](../DESIGN.md) | Numbered decisions, what is deferred, and the sources. |
| [Architecture](architecture.md) | Modules, the turn, and what crosses between them. |
| [Loop](loop.md) | Message flow, the 16-step ceiling, and what `agent` returns. |
| [Tool registry](tool-registry.md) | How a function becomes a schema and a validator. |
| [File tools](file-tools.md) | `read`, `write`, and `edit`. |
| [Search](search.md) | `glob` and `grep`, and the 50-result cap. |
| [Models](models.md) | The registry, `/models`, and the one create site. |
| [Workspace](workspace.md) | The launch directory, and how a path is classified. |
| [Modes](modes.md) | Plan and build, one conversation. |
| [Shell](shell.md) | Which shell runs, and what a command returns. |
| [Permissions](permissions.md) | The rule table, the prompt, and plan-mode asks. |
| [Streaming](streaming.md) | The event contract, and what Ctrl+C leaves behind. |
| [Observability](observability.md) | The status block, the tool line, and the display flags. |
| [Sessions](sessions.md) | Where a conversation is stored, and how resume works. |
| [Export](export.md) | `/export`, and what the file does not contain. |

## Working on MiniCode

| Doc | What it is |
|---|---|
| [AGENTS.md](../AGENTS.md) | The rules for a session in this repository. |
| [Contributing](../CONTRIBUTING.md) | How a change lands in one commit. |
| [Style](STYLE.md) | How a document is written. |
| [Status](STATUS.md) | What is next, and what is not. |
| [Changelog](../CHANGELOG.md) | What changed, by release. |
