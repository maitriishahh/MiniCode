# 07 — Shell

Do first: `docs/06-plan-build.md`. Layer 5 is done. This layer is
implemented in `tools/shell.py` and `agent.py`. Do not add permissions
from this file.

Registry, loop, `SYSTEM`, and the one `chat.completions.create` site live in
`agent.py`. A new tool is `tools/shell.py` plus one registry line. Do not
grow `__main__.py`. Do not touch `tools/__init__.py`. `tool_from_fn` stays
in `schema_generator.py`. Sandbox stays in `resolve_path.py`.

## What it is

One tool, resolved once at import. Windows prefers Git Bash, then
PowerShell. Unix prefers bash, then `sh`. The registered name matches the
winner: `bash` or `powershell`. A fresh process, `cwd` = `SANDBOX`, 120
seconds, output capped at 8000 characters. The finished output prints once,
then returns to the model. Plan drops both names.

## Why this shape

Pi's main tool is `bash`. On Windows it looks for Git Bash, then `bash.exe`
on `PATH`, and errors if neither exists. It does not fall through to
PowerShell. PowerShell is a second tool you opt into, Windows-only, so the
model sees the name. On Unix the order is `/bin/bash`, `bash` on `PATH`,
then `sh`. Output keeps the tail. A non-zero exit still returns the output.
Streaming, abort, and the temp file for the rest of the output are not this
layer.

OpenCode's tool is `bash`. On Windows it honors `OPENCODE_GIT_BASH_PATH`,
otherwise it auto-detects, and the fallback is `cmd.exe`. That path is
buggy: `SHELL` can point at the WSL launcher, and a `bash.exe` path built
from `git.exe` misses. Do not copy either mistake. A request to tell the
model which dialect it got was closed.

Claude Code uses Git Bash when it is present and PowerShell only when it is
absent. On Linux, PowerShell is a separate opt-in that needs `pwsh`. It is
not the fallback for a missing bash. Its persistent shell needs a Ctrl+C
that leaves a coherent turn. That layer is later.

MiniCode keeps one function. The name the model sees is the winner, because
a static `shell` that sometimes runs PowerShell is how the model speaks
bash into the wrong interpreter. `PLAN_DENIED` lists both names so plan
blocks a guess of either. `SYSTEM` names `bash` or `powershell`, not the
dialect. `&&` and the semicolon stay in the first docstring line. The first
docstring line does, and only that line plus `Args:` reach the model.

`cwd` is `SANDBOX`, not a `workdir` argument. OpenCode can run outside the
project because `external_directory` asks first. That gate is the next
layer. A command can still `cd` or `Set-Location` out. Do not parse the
command to stop that.

`--sandbox sandbox` is the file-tool fence. The process starts there too.
`git` and `uv run` then do not see the repo. Do not point `cwd` at the repo
root to "fix" that. The product soak launches in the repo, with no
`--sandbox`.

## Skeleton

**Keep the loop. One new tool. Plan denies both names.**

1. Keep: message flow, the raw assistant dict append, `MAX_STEPS = 16`,
   `PLAN_SYSTEM`, `__main__.py`, `SANDBOX`, `_resolve`, the tool line
   `|Tools Used: \`name\` ({args})|`, status
   `{prompt:,} In | {out:,} Out | Elapsed: {elapsed:.1f}s`. No Tok/s.
2. Add: `src/minicode/tools/shell.py`. Stdlib only (`os`, `shutil`,
   `subprocess`, `sys`, `pathlib`). No new dep. No `shell=True`. No
   `-ExecutionPolicy Bypass`. No `cmd.exe`.
3. Replace: `PLAN_DENIED` gains `"bash"` and `"powershell"`. The registry
   loop gains `shell`. `tool_from_fn` reads `__name__`, which this module
   sets before the loop runs. `SYSTEM` gains one sentence. Do not smash it
   onto the locate sentence. Name `bash` or `powershell`. Do not name `&&`
   or a semicolon.
4. Do not edit `PLAN_SYSTEM`. Do not special-case the plan-denied message.
   The existing backstop already says `Plan mode: \`bash\` is disabled`.
5. Do not catch `KeyboardInterrupt`. `tool_from_fn` catches `Exception`
   only. Ctrl+C during the wait still kills the REPL. That is the
   streaming/abort layer.
6. Do not raise at import if nothing is found. The call returns a tool
   error that lists what was searched.

## Segment 1 — resolve, then run

File: `src/minicode/tools/shell.py`. No comments. The docstring is assigned
at the bottom, after resolve, so `tool_from_fn` sees the winner.

```python
import os
import shutil
import subprocess
import sys
from pathlib import Path

from minicode.resolve_path import SANDBOX

CAP = 8000
_SEARCHED: list[str] = []


def _file(path: str | None) -> str | None:
    if path and Path(path).is_file():
        return str(Path(path))
    return None


def _wsl_shim(path: str) -> bool:
    system = os.environ.get("SystemRoot", r"C:\Windows")
    resolved = os.path.normcase(str(Path(path).resolve()))
    for folder in ("System32", "Sysnative"):
        shim = os.path.normcase(str(Path(system) / folder / "bash.exe"))
        if resolved == shim:
            return True
    return False


def _try(path: str | None, label: str) -> str | None:
    _SEARCHED.append(label)
    return _file(path)


def _win_bash() -> str | None:
    for key in ("ProgramFiles", "ProgramFiles(x86)"):
        root = os.environ.get(key)
        if not root:
            continue
        found = _try(str(Path(root) / "Git" / "bin" / "bash.exe"), f"{key}\\Git\\bin\\bash.exe")
        if found:
            return found
    which = shutil.which("bash.exe")
    _SEARCHED.append(f"bash.exe on PATH ({which or 'missing'})")
    if which and _file(which) and not _wsl_shim(which):
        return which
    return None


def _win_powershell() -> str | None:
    which = shutil.which("pwsh.exe")
    found = _try(which, f"pwsh.exe on PATH ({which or 'missing'})")
    if found:
        return found
    root = os.environ.get("ProgramFiles")
    if root:
        found = _try(
            str(Path(root) / "PowerShell" / "7" / "pwsh.exe"),
            "ProgramFiles\\PowerShell\\7\\pwsh.exe",
        )
        if found:
            return found
    which = shutil.which("powershell.exe")
    found = _try(which, f"powershell.exe on PATH ({which or 'missing'})")
    if found:
        return found
    system = os.environ.get("SystemRoot", r"C:\Windows")
    return _try(
        str(Path(system) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"),
        "System32\\WindowsPowerShell\\v1.0\\powershell.exe",
    )


def _unix() -> tuple[str, str] | None:
    for path, label, dialect in (
        ("/bin/bash", "/bin/bash", "bash"),
        (shutil.which("bash"), "bash on PATH", "bash"),
        ("/bin/sh", "/bin/sh", "sh"),
        (shutil.which("sh"), "sh on PATH", "sh"),
    ):
        found = _try(path, f"{label} ({path or 'missing'})")
        if found:
            return found, dialect
    return None


def _resolve() -> tuple[list[str], str, str] | None:
    if sys.platform == "win32":
        bash = _win_bash()
        if bash:
            return [bash, "-c"], "bash", "bash"
        ps = _win_powershell()
        if ps:
            return [ps, "-NoProfile", "-NonInteractive", "-Command"], "powershell", "powershell"
        return None
    found = _unix()
    if not found:
        return None
    binary, dialect = found
    return [binary, "-c"], dialect, "bash"


_RESOLVED = _resolve()

_DOCS = {
    "bash": (
        "Run a bash command in the sandbox for tests and git. Chain with &&.",
        "Bash command. Chain with &&.",
    ),
    "sh": (
        "Run a POSIX sh command in the sandbox for tests and git. No bash features.",
        "POSIX sh command. Chain with &&. No bash features.",
    ),
    "powershell": (
        "Run a PowerShell command in the sandbox for tests and git. Separate commands with a semicolon.",
        "PowerShell command. Separate commands with a semicolon.",
    ),
}


def _decode(raw: bytes | None) -> str:
    if not raw:
        return ""
    powershell = _RESOLVED is not None and _RESOLVED[1] == "powershell"
    if powershell and (raw.startswith((b"\xff\xfe", b"\xfe\xff")) or b"\x00" in raw[:200]):
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
    label = _RESOLVED[1] if _RESOLVED else "missing"
    print(
        f"---\nShell ({label}):\n{text}",
        end="---\n" if text.endswith("\n") else "\n---\n",
    )
    return text


def shell(command: str) -> str:
    if not command.strip():
        raise ValueError("Empty command")
    if ".env" in command.lower():
        raise ValueError("Refusing to access .env files")
    if _RESOLVED is None:
        raise ValueError("No shell found. Searched: " + "; ".join(_SEARCHED))
    argv, _dialect, _name = _RESOLVED
    try:
        proc = subprocess.run(
            [*argv, command],
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


if _RESOLVED:
    _summary, _arg = _DOCS[_RESOLVED[1]]
    shell.__name__ = _RESOLVED[2]
    shell.__doc__ = f"{_summary}\n\nArgs:\n    command: {_arg}\n"
else:
    shell.__name__ = "powershell" if sys.platform == "win32" else "bash"
    shell.__doc__ = (
        "Run a shell command in the sandbox for tests and git.\n\n"
        "Args:\n"
        "    command: Command for the shell named above.\n"
    )
```

- Resolve once. Do not search again per call. `sys.platform == "win32"`
  selects the Windows chain. Everything else, including macOS and WSL, uses
  the Unix chain. WSL is Linux from Python's point of view. Do not detect it
  to force PowerShell.
- A candidate counts only if `Path.is_file()`. A Windows Store alias can
  make `shutil.which` return a path that is not a real exe. Do not
  special-case that.
- Windows order: `%ProgramFiles%\Git\bin\bash.exe`, then
  `%ProgramFiles(x86)%\Git\bin\bash.exe`, then `bash.exe` on `PATH` unless
  the resolved path is `%SystemRoot%\System32\bash.exe` or
  `Sysnative\bash.exe`. That file is the old WSL launcher. Pi special-cases
  it. Skip it. Then `pwsh.exe` on `PATH`, then
  `%ProgramFiles%\PowerShell\7\pwsh.exe`, then `powershell.exe` on `PATH`,
  then the System32 Windows PowerShell path.
- Do not read `SHELL` on Windows. OpenCode's desktop bug is trusting it and
  launching WSL bash, which does not inherit the Windows env. Do not build a
  bash path from `git.exe`. OpenCode's join treats `git.exe` as a directory
  and misses. Do not search `sh.exe` on `PATH`. Git's `sh.exe` is the same
  install as `bash.exe`, so the first hit already covers it.
- Unix order: `/bin/bash`, `bash` on `PATH`, `/bin/sh`, `sh` on `PATH`. No
  `pwsh` on Unix. `/bin/sh` is the fallback, and it is present. A PowerShell
  hit there would change the dialect for no gain. That is Claude Code's
  opt-in, not this chain.
- No `cmd.exe`. OpenCode falls through to it and the quoting breaks.
- The registered name is `bash` for bash and for sh. It is `powershell` for
  either PowerShell. Set `__name__` and `__doc__` at import, before
  `tool_from_fn`. The first line is one line: bash says chain with `&&`, sh
  says POSIX sh and no bash features, PowerShell says separate commands with
  a semicolon. If nothing resolved, still register one name (`powershell` on
  Windows, `bash` elsewhere) so the REPL starts. The call raises. Do not
  raise at import.
- Argv is `[binary, "-c", command]` or
  `[binary, "-NoProfile", "-NonInteractive", "-Command", command]`. The
  command is one argument. Do not use `shell=True`. Do not add
  `-ExecutionPolicy Bypass`. Inline `-Command` does not need it. Pi's
  PowerShell tool passes Bypass. This one does not.
- UTF-16 decode runs only when the winner is PowerShell. Windows PowerShell
  5.1 writes UTF-16 to a pipe. `pwsh` and bash write UTF-8. Do not pass
  `text=True`.
- A non-zero exit is not a tool error. Return `exit {code}` plus the
  output. If you raise, the model never sees the test failure.
- Timeout is 120 seconds inside the function. Not a parameter. Include
  whatever bytes arrived, then `Timed out after 120s`.
- Cap the body, then prefix `exit`. The truncation line must not eat the
  code. Keep the tail. Do not write a temp file for the rest.
- Empty output is `(no output)`.
- `.env` in the command text is a string check, the same refusal as
  `_resolve`. It is not a sandbox. `cat .env` and `Get-Content .ENV` are
  caught. `$env:GEMINI_API_KEY` is not. The child inherits the process env.
  Do not scrub it. That hole belongs to permissions.
- Do not run the command through `_resolve`. Do not copy `grep`'s skip of
  `.venv`. `uv` needs it.
- Print the same string the model gets, once, when the process returns.
  The header is `Shell (bash):`, `Shell (sh):`, or `Shell (powershell):`.
  Streaming is later. The separator matches `edit`: the closing `---` lands
  on its own line. Unlike the diff, this text is sent to the model. The
  loop still prints `|Tools Used: \`bash\` ({args})|` or
  `|Tools Used: \`powershell\` ({args})|` after `run()` returns. Do not
  print a second copy there.
- An empty command, a `.env` command, or a missing shell raises before
  `_show`. No shell block. `tool_from_fn` turns that into `Tool error:`.
- A binary that disappears after resolve is `FileNotFoundError` →
  `Tool error:`. Do not resolve again.

## Segment 2 — Registry, plan, `SYSTEM`

File: `src/minicode/agent.py`.

Import:

```python
from minicode.tools.shell import shell
```

Replace the denied set. Do not rename it. Do not filter `TOOLS`. Both names
stay in the tuple even though only one is registered.

```python
PLAN_DENIED = ("write", "edit", "bash", "powershell")
```

Leave `PLAN_SYSTEM` as it is. Do not name either tool in it.

Replace the registry loop. `__name__` is already `bash` or `powershell`.

```python
for _fn in (read, write, edit, glob, grep, shell):
    _schema, _run = tool_from_fn(_fn)
    TOOLS[_fn.__name__] = _run
    SCHEMAS.append(_schema)
```

`SYSTEM` is this string. The new sentence is its own sentence. The locate
line keeps its trailing space so the strings do not smash. Name both
tools. Do not write `&&` or a semicolon here. The docstring carries the
dialect. The sentence stays true whichever name was registered.

```python
SYSTEM = (
    "You are a concise coding assistant. Use tools when they help. Be brief. "
    "`write` creates a new file, or overwrites an existing file with complete content. "
    "To overwrite, `read` then `write` the full file. "
    "`edit` changes one exact unique span. For add/append/insert or replace X with Y, `read` then `edit`; "
    "add/append means insert while preserving all existing content — never delete or rewrite it; "
    "never `write` with partial content. "
    "Locate with `glob`, confirm with `grep`, then `read` before mutating. "
    "Run tests and git with `bash` or `powershell`, whichever is in the tool list. Do not use it to read or search files."
)
```

No batching sentence. A shell call that depends on a `write` cannot share a
response. Do not raise `MAX_STEPS`.

Do not touch `__main__.py`. `Tools Loaded` follows `active_names()`. Build
shows `bash` or `powershell`, not both. Plan shows neither.

## Soak

Product, from the repo. This is the run that can see `git` and `uv`:

```powershell
uv run python -m minicode
```

This machine has Git, so the winner is `bash` and the header is
`Shell (bash):`. `git status` is the command because it works in both
dialects. Do not soak with `&&`.

```text
user >> /plan
user >> run git status
```

Plan must not print a `Shell (` block and must not run the command. Tools
Loaded does not include `bash` or `powershell`. A guessed call of either
name returns `Plan mode: \`bash\` is disabled` or the powershell twin, as
`role: "tool"`.

```text
user >> /build
user >> run git status
```

Build prints one `Shell (bash):` block, then
`|Tools Used: \`bash\` ({args})|`, then the answer. The block starts with
`exit 0` or another code, not `Tool error:`, when the command actually ran.

The fence is still for file tools:

```powershell
uv run python -m minicode --sandbox sandbox
```

The process starts in `sandbox/`. `git status` still describes the parent
repo, because git walks up to `.git`. That is not a file-tool escape. Do
not point `cwd` at the repo root to change it. Do not add a second root.

The Unix branch is the same `-c` call with a different binary. It cannot be
proved from this Windows machine. Do not add a CI job for it.

## Don't add yet

Later, in order, not in the implement pass: permissions (`ask` / `deny`,
`external_directory`), streaming and a Ctrl+C that leaves a coherent turn,
sessions. Background bash is deferred until it hurts. It is not in that
chain. `/connect` stays with the catalog.

Not scheduled. Do not add them as a follow-up: a shell-path env, `cmd.exe`,
reading `SHELL` on Windows, `System32\bash.exe`, a path derived from
`git.exe`, `pwsh` on Unix, registering `bash` and `powershell` at the same
time, a timeout parameter, a `workdir` parameter, a persistent shell, env
scrubbing, parsing the command, a temp file for full output, killing a
process tree, `-ExecutionPolicy Bypass`, `shell=True`.

## Checkpoint

1. Which name is registered on this machine, and which name on a Unix box
   with no bash?
2. Why is `System32\bash.exe` skipped?
3. Where does the process start? What does `--sandbox sandbox` do to `git`?
4. What comes back on exit code 1 — a tool error, or what?
5. What does the human see before `|Tools Used|`? Does the model get that
   same text?
6. What stops a guessed `powershell` in plan when the winner was `bash`?
7. Why must `SYSTEM` not say `&&`?

Answers: (1) `bash` here, because Git Bash wins; `bash` on Unix too when
the winner is `sh` — the docstring says POSIX sh; (2) it is the old WSL
launcher, and OpenCode's bug is launching it; (3) `SANDBOX` — the fence
hides the repo, and `cwd` stays there; (4) `exit 1` plus the output,
printed and returned; (5) one `Shell (bash):` block, and yes, the model
gets that string — unlike `edit`'s diff; (6) both names are in
`PLAN_DENIED`, so the dispatch backstop refuses the guess even though that
name was not registered; (7) the winner may be PowerShell, and the dialect
lives in the first docstring line, which is the only tool description the
model sees.
