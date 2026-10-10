# 07 — Shell

Do first: `docs/06-plan-build.md`. Layer 5 is done. This layer is not
implemented. Copy it in the next pass. Do not add permissions in that pass.

Registry, loop, `SYSTEM`, and the one `chat.completions.create` site live in
`agent.py`. A new tool is `tools/shell.py` plus one registry line. Do not
grow `__main__.py`. Do not touch `tools/__init__.py`. `tool_from_fn` stays
in `schema_generator.py`. Sandbox stays in `resolve_path.py`.

## What it is

One tool, `shell`. A fresh `powershell.exe` process, `cwd` = `SANDBOX`,
120 seconds, output capped at 8000 characters. The finished output prints
once, then returns to the model. Plan drops `shell` the same way it drops
`write` and `edit`.

## Why this shape

OpenCode's tool is named `bash`. On Windows it looks up Git Bash
(`OPENCODE_GIT_BASH_PATH`). Its Windows docs prefer WSL, not PowerShell.
The permission (`allow` / `ask` / `deny`) is a separate layer.

Pi's tool is also `bash`, in the session directory. Timeout is an optional
parameter with no default. Output keeps the tail. Empty output is
`(no output)`. A non-zero exit still returns the output, then
`Command exited with code N`. A timeout still returns whatever arrived.
The UI streams that output. Abort kills the process tree. Full output can
be written to a temp file. That streaming, abort, and temp file are not
this layer.

Claude Code keeps a persistent shell. That needs a Ctrl+C that leaves a
coherent turn. That layer is later.

MiniCode's machine already has PowerShell. The setup docs are PowerShell.
The tool is `shell`, not `bash`, so the name is not a lie. Git Bash is a
second install. Do not add a lookup for it. A persistent shell is not the
sessions phase. Do not build one.

`cwd` is `SANDBOX`, not a `workdir` argument. OpenCode can run outside the
project because `external_directory` asks first. That gate is the next
layer. A command can still `Set-Location` out. Do not parse the command to
stop that.

`--sandbox sandbox` is the file-tool fence. Shell starts there too. `git`
and `uv run` then do not see the repo. Do not point `cwd` at the repo root
to "fix" that. The product soak launches in the repo, with no `--sandbox`.

## Skeleton

**Keep the loop. One new tool. Plan denies it.**

1. Keep: message flow, the raw assistant dict append, `MAX_STEPS = 16`,
   `PLAN_SYSTEM`, `__main__.py`, `SANDBOX`, `_resolve`, the tool line
   `|Tools Used: \`name\` ({args})|`, status
   `{prompt:,} In | {out:,} Out | Elapsed: {elapsed:.1f}s`. No Tok/s.
2. Add: `src/minicode/tools/shell.py`. Stdlib `subprocess` only. No new dep.
   No `shell=True`. No `-ExecutionPolicy Bypass`.
3. Replace: `PLAN_DENIED` gains `"shell"`. The registry loop gains `shell`.
   `SYSTEM` gains one sentence. Do not smash it onto the locate sentence.
4. Do not edit `PLAN_SYSTEM`. Do not special-case the plan-denied message.
   The existing backstop already says `Plan mode: \`shell\` is disabled`.
5. Do not catch `KeyboardInterrupt`. `tool_from_fn` catches `Exception`
   only. Ctrl+C during the wait still kills the REPL. That is the
   streaming/abort layer.

## Segment 1 — `shell`

File: `src/minicode/tools/shell.py`. Google-style docstring. Only the first
line and the `Args:` entry reach the model. No comments.

```python
import subprocess

from minicode.resolve_path import SANDBOX

CAP = 8000


def _decode(raw: bytes | None) -> str:
    if not raw:
        return ""
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")) or b"\x00" in raw[:200]:
        return raw.decode("utf-16", errors="replace")
    return raw.decode("utf-8", errors="replace")


def _output(out: bytes | None, err: bytes | None) -> str:
    parts = [p for p in (_decode(out).strip("\n"), _decode(err).strip("\n")) if p]
    return "\n".join(parts)


def _cap(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    if len(text) <= CAP:
        return text
    return f"... truncated — narrow the command\n{text[-CAP:]}"


def _show(text: str) -> str:
    print(f"---\nShell:\n{text}", end="---\n" if text.endswith("\n") else "\n---\n")
    return text


def shell(command: str) -> str:
    """Run a PowerShell command in the sandbox for tests and git.

    Args:
        command: PowerShell command. Separate commands with a semicolon. Not bash.
    """
    if not command.strip():
        raise ValueError("Empty command")
    if ".env" in command.lower():
        raise ValueError("Refusing to access .env files")
    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            cwd=SANDBOX,
            capture_output=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        body = _cap(_output(exc.stdout, exc.stderr))
        text = f"{body}\nTimed out after 120s" if body else "Timed out after 120s"
        return _show(text)
    body = _cap(_output(proc.stdout, proc.stderr))
    if not body:
        body = "(no output)"
    return _show(f"exit {proc.returncode}\n{body}")
```

- The command is an argument to `-Command`, not a string glued into
  `cmd.exe`. Do not use `shell=True`.
- PowerShell 5.1 writes UTF-16 to a pipe. Decode that, or the model sees
  spaced letters. Do not pass `text=True`.
- A non-zero exit is not a tool error. Return `exit {code}` plus the
  output. If you raise, the model never sees the test failure. Pi does the
  same: the output comes back, then the code.
- Timeout is 120 seconds inside the function. Not a parameter. A parameter
  the model can set to 1 or to 99999 does not help. Include whatever bytes
  arrived, then `Timed out after 120s`.
- Cap the body, then prefix `exit`. The truncation line must not eat the
  code. Keep the tail. Failures sit at the end. Do not write a temp file
  for the rest. Pi does. This layer tells the model to narrow the command.
- Empty output is `(no output)`. Same idea as `(no matches)` and
  `(empty file)`.
- `.env` in the command text is a string check, the same refusal as
  `_resolve`. It is not a sandbox. `Get-Content .ENV` is caught.
  `$env:GEMINI_API_KEY` is not. The child inherits the process env. Do not
  scrub it. That hole belongs to permissions.
- Do not run the command through `_resolve`. Do not copy `grep`'s skip of
  `.venv`. `uv` needs it.
- Print the same string the model gets, once, when the process returns.
  Streaming is later. A silent tool line is not enough. OpenCode, Pi, and
  Claude Code all show the output. The separator matches `edit`: the
  closing `---` lands on its own line. Unlike the diff, this text is sent
  to the model. The loop still prints `|Tools Used: \`shell\` ({args})|`
  after `run()` returns. Do not print a second copy there.
- An empty command or a `.env` command raises before `_show`. No shell
  block. `tool_from_fn` turns that into `Tool error:`.
- A missing `powershell.exe` is `FileNotFoundError` → `Tool error:`. Do not
  search for `pwsh` or Git Bash.

## Segment 2 — Registry, plan, `SYSTEM`

File: `src/minicode/agent.py`.

Import:

```python
from minicode.tools.shell import shell
```

Replace the denied set. Do not rename it. Do not filter `TOOLS`.

```python
PLAN_DENIED = ("write", "edit", "shell")
```

Leave `PLAN_SYSTEM` as it is. Do not name `shell` in it.

Replace the registry loop:

```python
for _fn in (read, write, edit, glob, grep, shell):
    _schema, _run = tool_from_fn(_fn)
    TOOLS[_fn.__name__] = _run
    SCHEMAS.append(_schema)
```

`SYSTEM` is this string. The new sentence is its own sentence. The locate
line keeps its trailing space so the strings do not smash.

```python
SYSTEM = (
    "You are a concise coding assistant. Use tools when they help. Be brief. "
    "`write` creates a new file, or overwrites an existing file with complete content. "
    "To overwrite, `read` then `write` the full file. "
    "`edit` changes one exact unique span. For add/append/insert or replace X with Y, `read` then `edit`; "
    "add/append means insert while preserving all existing content — never delete or rewrite it; "
    "never `write` with partial content. "
    "Locate with `glob`, confirm with `grep`, then `read` before mutating. "
    "Run tests and git with `shell`. Do not use `shell` to read or search files."
)
```

No batching sentence. A `shell` call that depends on a `write` cannot share
a response. Do not raise `MAX_STEPS`.

Do not touch `__main__.py`. `Tools Loaded` follows `active_names()`. Build
shows `shell`. Plan does not.

## Soak

Product, from the repo. This is the run that can see `git` and `uv`:

```powershell
uv run python -m minicode
```

```text
user >> /plan
user >> run git status
```

Plan must not print a `Shell:` block and must not run the command. A guessed
`shell` call returns `Plan mode: \`shell\` is disabled` as `role: "tool"`.

```text
user >> /build
user >> run git status
```

Build prints one `Shell:` block, then `|Tools Used: \`shell\` ({args})|`,
then the answer. The block starts with `exit 0` or another code, not
`Tool error:`, when the command actually ran.

The fence is still for file tools:

```powershell
uv run python -m minicode --sandbox sandbox
```

A `shell` call there starts in `sandbox/`. `git status` will not describe
the repo. That is not a bug. Do not add a second root.

## Don't add yet

Later, in order, not in the implement pass: permissions (`ask` / `deny`,
`external_directory`), streaming and a Ctrl+C that leaves a coherent turn,
sessions. Background bash is deferred until it hurts. It is not in that
chain. `/connect` stays with the catalog.

Not scheduled. Do not add them as a follow-up: Git Bash detection, a
`pwsh` search, a timeout parameter, a `workdir` parameter, a persistent
shell, env scrubbing, parsing the command, a temp file for full output,
killing a process tree, `-ExecutionPolicy Bypass`, `shell=True`.

## Checkpoint

1. What is the tool named, and why not `bash`?
2. Where does the process start? What does `--sandbox sandbox` do to `git`?
3. What comes back on exit code 1 — a tool error, or what?
4. What is capped, and which end is kept?
5. What does the human see before `|Tools Used|`? Does the model get that
   same text?
6. What stops `shell` in plan — the prompt, or what?
7. Why is Ctrl+C during the wait still fatal?

Answers: (1) `shell`, because the interpreter is PowerShell, not bash;
(2) `SANDBOX` — the fence hides the repo, and `cwd` stays there;
(3) `exit 1` plus the output, printed and returned; (4) the body, at 8000
characters, tail kept, then `exit` is prefixed; (5) one `Shell:` block, and
yes, the model gets that string — unlike `edit`'s diff; (6) `PLAN_DENIED`
hides it from `tools=` and the dispatch backstop refuses a guess;
(7) `KeyboardInterrupt` is a `BaseException`, and this layer does not catch
it.
