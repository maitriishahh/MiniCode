# MiniCode

A small coding agent for your terminal. It reads and edits files in a workspace,
searches code, runs shell commands, and switches between plan and build modes.
One Python loop over an OpenAI-compatible chat API.

**MiniCode starts in plan mode. Type `/build` to enable file writes.**

## Requirements

- Python 3.13 or newer
- [uv](https://docs.astral.sh/uv/)
- A Gemini API key, or a local Ollama server

On Windows, MiniCode uses Git Bash if it is installed, otherwise PowerShell. On
macOS and Linux it uses bash, then sh. The status line shows the loaded shell
name. Install details and failure modes are in `docs/setup.md`.

## Install

```powershell
git clone https://github.com/maitriishahh/MiniCode.git
cd MiniCode
uv sync
Copy-Item .env.example .env
```

On macOS or Linux, `cp .env.example .env`.

## Configure

Edit `.env`. It is gitignored. Server base URLs are in code, not in this file.

| Variable | Required | Notes |
|---|---|---|
| `GEMINI_API_KEY` | For Gemini | From https://aistudio.google.com |
| `GEMINI_MODEL` | For Gemini | Model id, for example `gemini-3.5-flash-lite`. No `gemini/` prefix. |
| `OLLAMA_MODEL` | No | Local model id. Leave empty to disable Ollama. |
| `OLLAMA_API_KEY` | No | Leave empty for a local server. |

To use only Ollama, leave `GEMINI_MODEL` empty, set `OLLAMA_MODEL`, and start
the local server first.

## Run

```powershell
uv run minicode
uv run minicode --sandbox C:\path\to\project
```

`uv run python -m minicode` is the same entry point.

`--sandbox` accepts a relative or absolute path and creates it if missing.
Without it, the workspace is the directory you launch from. Startup prints
`Type /help for available commands`, then a status block with no usage line.

Ask in plain English. Type `/build` before asking for file changes. Leave with
`exit`, `quit`, `bye`, or Ctrl+C at the prompt.

## Commands

`/help` prints this list and nothing else. Exact output is in
`docs/commands.md`. None of these is sent to the model. Any other input that
starts with `/` prints `Unknown command: {word}. Use /help.` and is not sent.
`/model` is the one named exception: `Unknown command: /model. Use /models.`

| Command | Effect |
|---|---|
| `/plan` | Switch to plan mode. `write` and `edit` are disabled. |
| `/build` | Switch to build mode. All tools are available. |
| `/models` | List loaded models. A number or an id switches for this session. |
| `/new` | Start a new session. Mode, model, thinking, effort, args, and output reset to their defaults. |
| `/sessions` | List saved sessions. A number resumes. `delete` and `rename` are actions. |
| `/export` | Write this session's transcript to a `.txt` in the workspace. |
| `/thinking` | Show or hide reasoning. `1 off`, `2 on`. Default `off`. |
| `/effort` | Set effort. `1 low`, `2 medium`, `3 high`. Default `low`. |
| `/args` | Show or hide tool arguments. `1 off`, `2 on`. Default `off`. |
| `/output` | Show or hide the shell output block. `1 off`, `2 on`. Default `off`. The model still gets the output. |
| `/help` | List commands. |
| `exit` | Leave. `quit` and `bye` do the same. |

`del` and `ren` are aliases. Switching modes keeps the conversation. `/new`
does not.

## Sessions

One JSON file per conversation, under
`~/.local/share/minicode/sessions/<project-key>/`. On Windows that root is
`%USERPROFILE%\.local\share\minicode\sessions`. A different workspace has a
different list. Nothing is written until the first message.

`/sessions` lists newest first. `/sessions N` resumes and restores the model,
mode, display flags, output-token total, and remembered approvals. `/export`
writes the same replay to a text file; `.env` is refused, and a path outside
the workspace asks. Session files stay on your machine. Detail is in
`docs/sessions.md` and `docs/export.md`.

## Tools and permissions

`read`, `write`, `edit`, `glob`, `grep`, and the loaded shell. `write` replaces
a whole file; `edit` changes one exact span and prints a diff. Search is capped
at 50. The shell times out at 120 seconds and keeps the last 8,000 characters. In-workspace edits do not ask. `.env` asks. A path outside the workspace
asks. In plan, a shell command that reads, creates, or deletes asks; `ls` and
`git` do not. Answer `o` once, `a` always (this exact value, this session), or
`d` to deny.

The workspace is a path boundary, not a container. An approved command can
`cd` out, and the shell inherits your environment. Do not run MiniCode on a
repository you do not trust. The rules are in `docs/permissions.md`.

## Status

After each turn, and at startup with no usage line:

```text
---
Model: gemini-3.5-flash-lite | Mode: plan | Tools Loaded: read, glob, grep, bash
Sandbox: C:\path\to\project | Thinking: off | Effort: low | Args: off | Output: off
1,204 In | 48 Out | 96 Session | Elapsed: 2.1s
---
```

`In` is the last call's prompt size. `Out` is output tokens for the turn.
`Session` is output tokens for the conversation: it survives resume and resets
on `/new`. There is no tokens-per-second figure.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `401` or authentication error | Check `GEMINI_API_KEY` in `.env`. |
| `404` model not found | Remove any `gemini/` prefix from `GEMINI_MODEL`. |
| `No module named minicode` | Run `uv sync` from the MiniCode directory. |
| `Model Error: ...` with Ollama | Start Ollama and check that `OLLAMA_MODEL` matches a pulled model. |
| `No shell found` | Install Git Bash or PowerShell on Windows, or bash/sh on Unix. |
| `Max limit reached: 16` | The turn hit the step limit. Ask for a smaller task. |

Ctrl+C during a model call or a tool call returns to `>>> ` when Python is
between chunks. On Windows it does not abort a call blocked in a socket read;
close the terminal tab. A click paste can submit every line as a request. A
grandchild shell process can outlive the call. What is deliberately not built
is listed in `DESIGN.md`. The doc map is `docs/index.md`.

## License

Apache-2.0. See `LICENSE`.
