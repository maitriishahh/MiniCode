# Shell

**Status:** shipped · **Layer:** 5 · **Files:** `tools/shell.py`
**Verified:** 2026-10-30

One tool that runs a command in a fresh child process, with the workspace as its
working directory. Which shell it is — and what the tool is called — is decided
once, at import. The model always speaks the dialect that actually runs.

## Contract

`_resolve()` returns `(argv, dialect, name)` or `None`, and `_RESOLVED` holds it
for the life of the process:

| Platform | Order tried | Registered name |
|---|---|---|
| Windows | `%ProgramFiles%\Git\bin\bash.exe`, `%ProgramFiles(x86)%\...`, `bash.exe` on `PATH`, `pwsh.exe` on `PATH`, `%ProgramFiles%\PowerShell\7\pwsh.exe`, `powershell.exe` on `PATH`, `%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe` | `bash` or `powershell` |
| Unix | `/bin/bash`, `bash` on `PATH`, `/bin/sh`, `sh` on `PATH` | `bash`, including when the binary is `sh` |

A candidate counts only if it is a real file. A `bash.exe` that resolves to
`%SystemRoot%\System32\bash.exe` or `Sysnative\bash.exe` is skipped: that is the
old WSL launcher. `SHELL` is not read on Windows.

Argv:

```text
bash / sh   [binary, "-c", command]
powershell  [binary, "-NoProfile", "-NonInteractive", "-Command", command]
```

`subprocess.run(..., cwd=SANDBOX, capture_output=True, timeout=120)`. No
`shell=True`. The command is one argument, so quoting, `&&`, `;`, and heredocs
are the shell's problem and work as they would in a terminal.

The registered name and the docstring are rewritten after resolution, before the
registry wraps the function:

```python
if _RESOLVED:
    _summary, _arg = _DOCS[_RESOLVED[1]]
    shell.__name__ = _RESOLVED[2]
    shell.__doc__ = f"{_summary}\n\nArgs:\n    command: {_arg}\n"
```

So the model sees `bash`, `sh`'s docstring under the name `bash`, or
`powershell`, and the first docstring line names the chaining style. If nothing
resolved, the name still becomes `powershell` on Windows and `bash` elsewhere,
so the REPL starts; the call returns an error instead.

### Return value

```text
exit {code}
{stdout}
{stderr}
```

- stdout and stderr are concatenated; each loses its leading and trailing
  newlines, and an empty part is dropped.
- Empty output becomes `(no output)`.
- A non-zero exit is not an error. The model sees `exit 1` and the output, so a
  failing test is information rather than a broken tool.
- Output is capped at 8000 characters, tail kept:
  `... truncated — narrow the command` then the last 8000 characters. The cap
  is applied to the body, then `exit {code}` is prepended, so the code is never
  lost to truncation.
- Timeout is 120 seconds, not a parameter. Whatever arrived is returned, then
  `Timed out after 120s` on its own line, with no exit line.
- Decoding is UTF-8 with `errors="replace"`, except when the winner is
  PowerShell and the bytes start with a UTF-16 BOM or contain a NUL in the
  first 200 bytes. Windows PowerShell 5.1 writes UTF-16 to a pipe; `pwsh` and
  bash write UTF-8.

### Display

`output = {"name": "off"}` is owned here and toggled by `/output`. When it is
`on`, `_show` prints the same string the model receives:

```text
---
Shell (bash):
exit 0
...

---
```

The label is the dialect, or `missing` when nothing resolved. When `/output` is
`off`, nothing prints and the model still gets the string. The `|Tool Used:` line
comes from the loop afterwards, not from this tool.

### Failures

| Case | Result |
|---|---|
| empty command | `Tool error: Empty command` |
| no shell resolved | `Tool error: No shell found. Searched: {labels}` |
| the binary disappeared after resolve | `Tool error: ...` from `FileNotFoundError` |
| a command containing `.env` | permission prompt (`docs/permissions.md`), not a refusal here |

`_SEARCHED` records every candidate as it is tried, so the no-shell message
names the paths that were checked.

## Why this shape

**The name is the winner.** A tool called `shell` that sometimes runs PowerShell
is how a model writes bash into PowerShell. Registering `bash` or `powershell`,
and putting the chaining rule in that docstring, makes the tool description
true.

**Git Bash first on Windows, and no `cmd.exe`.** Pi looks for Git Bash and then
`bash` on `PATH`, and errors when neither exists; MiniCode falls through to
PowerShell instead, because a Windows box without bash can still run a
PowerShell command. OpenCode honors `OPENCODE_GIT_BASH_PATH`, auto-detects
otherwise, and falls back to `cmd.exe`; that fallback breaks quoting, and its
detection can pick the WSL launcher through `SHELL` or build a bash path from
`git.exe` as if it were a directory. Neither mistake is copied.

**PowerShell is the fallback, not the sibling.** Claude Code uses Git Bash when
present and PowerShell only when it is absent; on Linux its PowerShell is a
separate opt-in. MiniCode keeps one tool, so the model never has to choose.

**`sh` registers as `bash`.** The docstring says POSIX sh and no bash features,
and the name stays `bash` so history, `PLAN_DENIED`, and the permission key
`shell` do not need a third spelling.

**`cwd` is the workspace, not a parameter.** A `workdir` argument is one more
thing for the model to get wrong, and the workspace is already the boundary for
every other tool. A command can still `cd` out; that is handled by the
permission prompt, not by parsing the command.

**No `-ExecutionPolicy Bypass`.** Inline `-Command` does not need it. Pi's
PowerShell tool passes it; this one does not, and `-NoProfile` plus
`-NonInteractive` keeps a user profile from changing the result.

## Invariants

- Resolve once, at import. Never search again per call. `tools/shell.py`.
- No `cmd.exe`, no `pwsh` on Unix, no `bash.exe` from System32.
- `shell.__name__` is set before `tool_from_fn` runs. `agent.py` builds `TOOLS`
  after importing the module.
- `PLAN_DENIED` names both `bash` and `powershell` even though only one is
  registered, so a guess of either is refused by name.
- `cwd=SANDBOX` always. Nothing re-reads or overrides it.
- A non-zero exit returns a string; it never raises.
- The truncation line goes above the kept tail, and below `exit`.

## Edge cases

| Input | Result |
|---|---|
| `git status` with a clean tree | `exit 0` and the branch summary |
| `python -c "raise SystemExit(3)"` | `exit 3` and the traceback |
| a command that prints nothing | `exit 0` and `(no output)` |
| a command with 20 KB of output | truncation line plus the last 8000 characters |
| a command that runs longer than 120s | partial output plus `Timed out after 120s` |
| a command containing `.env` | permission prompt before anything runs |
| no bash and no PowerShell on Windows | `Tool error: No shell found. Searched: ...` |
| a multi-line command | passed as one argument; bash and PowerShell both accept it |
| Ctrl+C during the wait | `KeyboardInterrupt` escapes the registry and ends the turn |

## Verification

- `uv run python -m minicode`, `/build`, then "run git status": one
  `Shell (bash):` block when `/output` is `on`, one `|Tool Used: \`bash\`` line,
  `exit 0` inside the block.
- `echo hi; exit 4` on bash returns `exit 4` and `hi`.
- `/output off`, repeat: no block, and the answer still quotes the output.
- In plan, `touch notes.txt` asks for permission; deny returns the plan
  sentence, not a shell block.
- The 120-second timeout and the UTF-16 path are not exercised on this machine.
  The timeout needs a two-minute command; the UTF-16 path needs Windows
  PowerShell 5.1 as the winner, and this machine resolves Git Bash.

## Gaps

- The child inherits the whole process environment, including API keys. No
  scrubbing.
- A permitted command can `cd` out of the workspace and write there. The
  boundary is a prompt on the command, not a jail.
- No `workdir`, no background process, no persistent shell. Each call pays
  process startup, and `cd` does not survive to the next call.
- A timeout does not kill grandchildren on Windows, so a stuck child can outlive
  the call.
- Truncation keeps the tail, which is right for test failures and wrong for a
  command that prints its error first.
- The docstring still says "in the sandbox" while `SYSTEM` says workspace and
  allows absolute paths. Wording only; a code pass should align it.

## History

- 2026-10-21  Shell arrived as one resolved tool, with both names denied in
  plan mode.
- 2026-10-23  Permissions put shell back in plan and made it an `ask` instead of
  a denied tool.
- 2026-10-25  The `.env` check inside `shell()` was removed. A command whose
  text contains `.env` now asks through the permission rule, so an approval is
  possible instead of a hard refusal.
- 2026-10-28  The output block became hidden by default; `/output` shows it
  again.
