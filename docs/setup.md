# Setup

**Status:** shipped · **Files:** `pyproject.toml`, `.env.example`
**Verified:** 2026-10-31

What you need installed, and how to prove the model is reachable before you run
anything that writes files. `README.md` has the short version; this doc keeps
the detail and the failure modes.

## Contract

Requirements: Python 3.13 or newer, `uv`, and either a Gemini API key or a
local Ollama server.

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Close and reopen the terminal, then check both:

```powershell
uv --version
python --version
```

From the repository root, which is where `pyproject.toml` lives:

```powershell
uv sync
```

On macOS or Linux use the shell equivalent; `uv sync` is the same command.

The dependencies are `openai`, `pydantic`, and `python-dotenv`. Nothing else is
installed and nothing else should be. `uv add <pkg>` is the only way a
dependency arrives; `uv.lock` is committed and pins exact versions.

`.env` is created from the template and never committed:

```powershell
Copy-Item .env.example .env
```

| Variable | Required | Meaning |
|---|---|---|
| `GEMINI_API_KEY` | for Gemini | the secret; get one at https://aistudio.google.com |
| `GEMINI_MODEL` | for Gemini | the model id, no `gemini/` prefix |
| `OLLAMA_MODEL` | no | a local model id; empty disables the server |
| `OLLAMA_API_KEY` | no | empty for a loopback server |

The base URL is not a variable. It lives on the `_SERVERS` tuple in
`agent.py`. `load_dotenv()` runs once in `agent.py` before any `os.getenv`.

Verify reachability with one throwaway command. This is not a project file and
creates nothing on disk:

```powershell
uv run python -c "from dotenv import load_dotenv; load_dotenv(); from openai import OpenAI; import os; print(OpenAI(api_key=os.getenv('GEMINI_API_KEY'), base_url='https://generativelanguage.googleapis.com/v1beta/openai/').chat.completions.create(model=os.getenv('GEMINI_MODEL'), messages=[{'role':'user','content':'Say hi in five words.'}]).choices[0].message.content)"
```

A short greeting means the key, the id, and the endpoint all agree.

## Why this shape

The Gemini OpenAI-compatible endpoint means one client, one package, and no
provider SDK per brand. That is the whole reason `openai` is the only transport
dependency; the alternative, LiteLLM, was removed on 2026-09-30 because it hid
the request body the harness needs to control.

A missing Gemini key fails at the first call rather than at import, so the REPL
still starts and `/help` still works without credentials. That is deliberate:
the failure is reported as `Model Error: ...` in the turn, not as a crash on
startup.

## Invariants

- `load_dotenv()` runs before the first `os.getenv`. `agent.py`.
- Model ids never carry a provider prefix. A `gemini/` id returns `404`.
- Base URLs stay in code. Only ids and keys come from `.env`.
- An empty `OLLAMA_MODEL` skips that server at import. `agent.MODELS`.
- An empty key on a loopback base becomes `"ollama"`. `agent._client_for`.
- `.env` is gitignored and is never read by a tool without permission.

## Edge cases

| Symptom | Cause |
|---|---|
| `401` / authentication error | `GEMINI_API_KEY` missing or wrong |
| `404` model not found | a `gemini/` prefix, or an id the key cannot see |
| `No module named minicode` | `uv sync` was not run from the repository root |
| `Model Error: ...` with Ollama | server down, or `OLLAMA_MODEL` not pulled |
| `No shell found` | no Git Bash, PowerShell, bash, or sh on the machine |
| empty model list | every id env is empty |

## Verification

- `uv --version` and `python --version` report 3.13 or newer.
- `uv sync` completes and `.venv/` exists.
- `.env` exists, is listed in `.gitignore`, and `git status` does not show it.
- The one-line create prints a short greeting.
- `uv run python -m minicode` starts and prints a status block naming a model.
  `uv run minicode` is the same entry point.

## Gaps

- No setup check that validates `.env` before the first call. A bad key is
  discovered at the first prompt.

## History

- 2026-09-30  Setup retargeted from LiteLLM to the `openai` client. The
  `LITELLM_LOG` variable and the `gemini/` id prefix were removed with it.
- 2026-10-31  A `minicode` console script arrived. `uv run minicode` and
  `python -m minicode` start the same REPL.
