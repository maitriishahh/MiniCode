# 00 — Setup

Do first: read `AGENTS.md`. Then do this guide end to end. No agent code yet.

## What you'll build

A working Python environment with the OpenAI client able to reach Gemini.
That is all. Layer 0 used LiteLLM. This guide is the live setup.

## 1. Install uv (Windows PowerShell)

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Close and reopen the terminal, then verify:

```powershell
uv --version
python --version   # 3.13+
```

Python 3.13+: install from [python.org](https://www.python.org/downloads/)
with **"Add Python to PATH"** checked if `python --version` is older.

## 2. Project environment

From the repo root (`pyproject.toml` lives here):

```powershell
uv sync
.venv\Scripts\activate
```

`uv sync` creates `.venv/`. New terminals usually open at the repo root;
PyCharm sometimes restores inside a subfolder — `cd` back to the root first.

Do **not** add a `[build-system]` yet — there is no `../src` package.
`docs/01-loop.md` Segment 1 adds hatchling once those files exist, so
`uv run python -m minicode` works. Until then, do not run the agent.

## 3. Dependencies

```powershell
uv add openai pydantic python-dotenv
```

Nothing else. Never bare `pip install`.

## 4. Environment file

```powershell
Copy-Item .env.example .env
```

Open `.env` and set your key from [AI Studio](https://aistudio.google.com)
(Get API key → Create API key):

```
GEMINI_API_KEY=paste-your-key-here
GEMINI_MODEL=gemini-3.5-flash-lite
OLLAMA_MODEL=
OLLAMA_API_KEY=
```

`.env` is never committed (see `.gitignore`). The model id has no `gemini/`
prefix. The base URL lives on the server tuple, not in `.env`. An empty
`OLLAMA_MODEL` skips that server. Leave `OLLAMA_API_KEY` empty; a loopback
call uses the dummy `"ollama"`. If an old `.env` still has `gemini/` or
`LITELLM_LOG`, delete both or the first call 404s. `load_dotenv()` runs
once in `agent.py`, before any `os.getenv`.

## 5. Verify (one throwaway check, not a project file)

```powershell
uv run python -c "from dotenv import load_dotenv; load_dotenv(); from openai import OpenAI; import os; print(OpenAI(api_key=os.getenv('GEMINI_API_KEY'), base_url='https://generativelanguage.googleapis.com/v1beta/openai/').chat.completions.create(model=os.getenv('GEMINI_MODEL'), messages=[{'role':'user','content':'Say hi in five words.'}]).choices[0].message.content)"
```

**Expected:** a short greeting. `401` → key. `404` → the model id still has
a `gemini/` prefix. Anything else → stop here and fix it before
`docs/01-loop.md`.

## Don't add yet

No tools, no loop, no model registry, no Ollama. Gemini reachable is the
whole milestone.
