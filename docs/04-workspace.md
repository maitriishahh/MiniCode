# 04 — Workspace flip to launch cwd

Do first: `docs/03-models.md`. Layer 2 is done. This layer is implemented
in `resolve_path.py`.

Registry, loop, `SYSTEM`, and the one `chat.completions.create` site live in
`agent.py`. `/model` and the status print live in `__main__.py`.
`tool_from_fn` stays in `schema_generator.py`. Sandbox stays in
`resolve_path.py`. Do not grow `__main__.py` with the root.

## What it is

One change: the default workspace is the launch directory. `--sandbox
path` stays as the override. That is the product rule (Pi, OpenCode): cwd,
or `--sandbox path`. The old default was the dev fence — the root-level
`sandbox/` dir — so tool tests could not overwrite harness source in `src/`.
That fence is still available for dev via
`uv run python -m minicode --sandbox sandbox`.

## Why it matters

`read` of a known path cannot do real work until the workspace is the repo
you launched in. Every later layer (search, shell, plan/build, permissions)
assumes cwd. The override is what keeps harness development safe after the
flip: point at the fence when you want it, point at a real repo otherwise.

## Skeleton

**Keep the loop. Keep the registry. Move the root.**

1. Keep: tools, `SYSTEM`, message flow, `_resolve`, `.env` denial, escape
   error, startup `Sandbox: {SANDBOX}` print, status block
   `{prompt:,} In | {out:,} Out | {session:,} Session | Elapsed: {_elapsed(elapsed)}`. No Tok/s.
2. Replace: `_sandbox_root()` in `src/minicode/resolve_path.py` — default
   becomes `Path.cwd().resolve()`. `--sandbox path` still wins.
3. Keep: `SANDBOX = _sandbox_root()` plus
   `SANDBOX.mkdir(parents=True, exist_ok=True)`. On cwd that call is a
   no-op. On an override it creates the dir.
4. Do not touch `agent.py` or `__main__.py` in this layer.

## Segment 1 — Root

File: `src/minicode/resolve_path.py`. Replace `_sandbox_root`. Keep the rest
of the file.

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

Keep `_resolve` exactly as it is: relative paths resolve against `SANDBOX`,
absolute paths resolve and are then checked, escapes are
`ValueError(f"Outside sandbox: {path}")`, `.env` files stay
`ValueError("Refusing to access .env files")`. Both stay tool errors, never
tracebacks.

## Segment 2 — Commands

From the directory you want the agent to work in (product):

```powershell
uv run python -m minicode
```

Startup prints `Sandbox: {SANDBOX}` where `{SANDBOX}` is that cwd. That is
the check that the flip worked.

To preserve the old root-level `sandbox/` fence for harness development,
from the repo root:

```powershell
uv run python -m minicode --sandbox sandbox
```

Startup prints `Sandbox: <repo-root>\sandbox`. Tool tests land in the fence
again and cannot overwrite `src/`. `sandbox/` stays gitignored — do not
commit it, do not delete it. It is now the dev override, not the default.

To point at a real repo without leaving the harness checkout:

```powershell
uv run python -m minicode --sandbox <that repo>
```

`--sandbox` accepts a relative or absolute path; it is resolved before use.
Missing override dirs are created. No other flags change in this layer.

**Expected:** launch in the repo root with no flag → `Sandbox:` is the root
and `read` sees `pyproject.toml`. Relaunch with `--sandbox sandbox` →
`Sandbox:` ends in `sandbox` and `read` of `pyproject.toml` fails as a tool
error (it is outside the fence). `../` escapes and `.env` still fail as tool
errors under either root.

## Your finished modules

`resolve_path.py` holds `_sandbox_root`, `SANDBOX`, and `_resolve`.
`agent.py` holds the loop and registry. `__main__.py` holds the REPL,
`/model`, and the status block. Still no new package dirs. Still no shell,
no search, no permissions change.

## Don't add yet

Search tool (next guide, capped `grep` or `find` — not a shell), shell,
plan/build swap, allow/ask/deny, `external_directory` gate, streaming,
sessions, compaction, cost, diff viewer. If the flip works and the fence is
still one flag away — stop.

## Checkpoint

1. Which file changes in this layer, and which two files must not?
2. What is the new default root, and what still overrides it?
3. What command preserves the root-level `sandbox/` fence for dev?
4. What happens to `../` escapes and `.env` under the new root?
5. Why must this layer not change the registry or add a tool?

Answers: (1) `src/minicode/resolve_path.py` only — `agent.py` and
`__main__.py` stay untouched; (2) `Path.cwd().resolve()`; `--sandbox path`
still wins; (3) `uv run python -m minicode --sandbox sandbox` from the repo
root; (4) same as before — `ValueError` strings returned as `role: "tool"`
content, files unchanged; (5) the flip is a root change, not a model or tool
change — one finished layer at a time.
