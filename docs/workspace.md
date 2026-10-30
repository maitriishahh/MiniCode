# Workspace

**Status:** shipped · **Layer:** 3 · **Files:** `resolve_path.py`
**Verified:** 2026-10-30

The workspace is the directory MiniCode was launched in, or the path given to
`--sandbox`. It is the root that relative paths resolve against and the
boundary that decides when a path counts as outside it. It is a path boundary,
not a container.

## Contract

`SANDBOX` is resolved once at import:

```python
def _sandbox_root() -> Path:
    if "--sandbox" in sys.argv:
        i = sys.argv.index("--sandbox")
        if i + 1 < len(sys.argv):
            return Path(sys.argv[i + 1]).resolve()
    return Path.cwd().resolve()

SANDBOX = _sandbox_root()
SANDBOX.mkdir(parents=True, exist_ok=True)
```

The directory is created if missing. On the default it already exists, so the
call is a no-op.

Every tool path goes through `classify`, which returns `(kind, resolved_path)`:

| Kind | When |
|---|---|
| `dotenv` | the final name is `.env` or starts with `.env.`, except `.env.example` |
| `external` | the resolved path is not the workspace and the workspace is not one of its parents |
| `inside` | everything else |

`_resolve(path)` then raises unless the path is allowed:

```text
Refusing to access .env files
Outside sandbox: {path}
```

Both are `ValueError`, so the registry returns them as `Tool error:` and the
file is untouched.

A relative path is resolved against `SANDBOX`. An absolute path is resolved and
then checked. `resolve()` follows symlinks, so a link that points outside the
workspace classifies as `external`.

On Windows, a Git Bash drive path is rewritten before the check:
`/d/projects/app` becomes `D:/projects/app`. `/tmp` and `/home` do not match
that pattern and stay as written. On Unix no rewrite happens.

The permission gate covers the two denied kinds. `agent._permit` calls
`classify`, asks `permissions.decide`, and on allow calls
`resolve_path.approve(path)`. `_resolve` accepts an approved path once; the
loop calls `clear_approved()` in a `finally` after every tool, so an approval
never outlives the call that earned it.

## Why this shape

**cwd, like Pi and OpenCode.** A coding agent that cannot read the repository
you launched it in is a demo. The launch directory is the least surprising
root, and `--sandbox` covers the case where you want a different one.

The previous default was a repository-local `sandbox/` directory, chosen while
the harness was being built so tool experiments could not overwrite `src/`.
That fence still exists as the development override:

```powershell
uv run python -m minicode --sandbox sandbox
```

It is no longer the product default, and `sandbox/` is gitignored.

**Absolute paths are allowed, outside ones ask.** A silent rejection teaches
the model to keep guessing. A prompt keeps the operation possible while making
the boundary visible. `.env` asks for the same reason: reading a secret is
sometimes exactly what the user wants, and never what an accident should get.

**No drive-letter guessing on Unix.** The `/d/...` rewrite is Windows-only
because on Unix `/tmp` and `/home` are real paths and rewriting them would
break them.

## Invariants

- `SANDBOX` is resolved once, at import, from `sys.argv` and cwd. Nothing
  re-reads it. `resolve_path._sandbox_root`.
- Every file tool resolves through `_resolve`. No tool touches a path directly.
- `.env.example` is never treated as a secret. `resolve_path.classify`.
- An approval is single-use and cleared in a `finally`. `agent.agent`.
- A path outside the workspace is a prompt, not a hard error.
- `--sandbox` accepts relative or absolute and is resolved before use.

## Edge cases

| Input | Result |
|---|---|
| `notes.txt` | `inside`, `<SANDBOX>/notes.txt` |
| `../secret` | `external` |
| `C:/elsewhere/x` | `external` |
| `/d/projects/x` on Windows | rewritten to `D:/projects/x`, then classified |
| `/tmp/x` on Windows | left as written, then classified |
| `.env` | `dotenv`, asks on read |
| `.env.local` | `dotenv`, asks |
| `.env.example` | `inside`, allows |
| a symlink pointing outside | `external` |
| `--sandbox` with a missing dir | created at startup |
| `--sandbox` with no value | ignored; cwd is used |

## Verification

- Launch from the repository root with no flag: `Sandbox:` is that root and a
  `read` of `pyproject.toml` works.
- Relaunch with `--sandbox sandbox`: `Sandbox:` ends in `sandbox`, and the same
  `read` returns a tool error because the file is outside.
- Under either root, `../` and `.env` are refused or prompted, never a
  traceback.
- On Windows, a Git Bash-style `/d/...` path to a real file resolves instead of
  being treated as relative.

## Gaps

- The workspace is a path boundary, not a container. An approved shell command
  can `cd` out of it, and the shell inherits the process environment.
- No env scrubbing for the shell.
- No symlink policy beyond `resolve()` following them.
- No way to add a second allowed root for a session.

## History

- 2026-10-01  The default root flipped from the repository-local `sandbox/`
  directory to the launch cwd. `--sandbox` kept the old behaviour as the
  development override.
- 2026-10-25  Git Bash drive paths started being rewritten before the sandbox
  check, because `/d/...` was resolving as a relative path.
