# 08 — Permissions

Do first: `docs/07-shell.md`. Layer 6 is done. This layer is implemented in
`permissions.py`, the dispatch gate in `agent.py`, and the prompt in
`__main__.py`. Do not start streaming in this pass. Do not add a config
file, a shell scanner, or env scrubbing.

Registry, loop, `SYSTEM`, and the one `chat.completions.create` site live in
`agent.py`. The ask prompt lives in `__main__.py`. `tool_from_fn` stays in
`schema_generator.py`. Sandbox math stays in `resolve_path.py`. Do not grow
`__main__.py` with the loop. The gate does not live in the tool files; the
post-pass below touches their path docs and `glob` / `grep` output, and it
edits `SYSTEM` / `PLAN_SYSTEM`. That is the only exception.

## What it is

One gate in front of the tools that already exist. Before `run()`, a check
returns `allow`, `ask`, or `deny`. The last matching rule wins. `*` matches
any character, including `/`. `?` matches one. Every other character is
literal. Do not use `pathlib.Path.match`. There `*` does not cross `/`, and
`**` is special. Here `**` is just two stars.

On Windows, compare with `\` turned into `/` and without case. That is the
matcher only. The denial string and the prompt show the value the model
sent, except `external_directory`, which shows the resolved path with
forward slashes.

| Key | What it sees | Default |
|---|---|---|
| `read` | the `path` argument | `allow` |
| `edit` | the `path` argument; covers `write` and `edit` | `allow` |
| `glob` | the glob pattern, not the search root | `allow` |
| `grep` | the regex, not the search root | `allow` |
| `shell` | the raw command; covers `bash` and `powershell` | `ask` |
| `external_directory` | one resolved path outside the sandbox | `ask` |

Rules are that table, in code. No `.minicode/permissions`. No prefix allows.
`shell git * allow` would also allow `git status && rm -rf`. This layer does
not parse the command.

`ask` is a prompt in `__main__.py`. The loop does not import the REPL. A
missing prompt denies.

- `once` — run this call.
- `always` — remember that exact value until the process exits. `git status`
  does not cover `git status --short`. A different file still asks. Nothing
  is written to disk.
- `deny` — the default for an empty answer, a bad answer, EOF, or Ctrl+C on
  that prompt.

A deny is `Permission denied: {key} {value}` with `role: "tool"`. No
`|Tools Used|` line. `always` does not override a `deny`. If no rule
matches, the action is `deny`.

## Why this shape

OpenCode's current permissions page (not the v2 scanner) is the model:
`allow` / `ask` / `deny`, last match wins, `external_directory` as its own
gate. OpenCode defaults edits to `allow` inside the project and asks only
for `external_directory`. Pi's point, already in the research plan, is that
an in-sandbox edit prompt is theater once the sandbox bounds the path. Copy
that. Do not ask on every `write`.

`shell` stays `ask` even though OpenCode allows it. OpenCode can allow it
because a scanner splits the command. This project must not parse the
command. `cd` and `Set-Location` can still leave. The ask is the gate. Do
not claim `external_directory` stops that.

v2's ordered list is the same idea. Do not import the rest: the experimental
scanner, default-allow outside the project, or a durable approval file.
Sessions are later. A saved approval that outlives the process waits with
them.

## Plan mode

`PLAN_DENIED` shrinks to `("write", "edit")`. Those stay out of the schema.
The existing message stays:
`Plan mode: \`write\` is disabled. Propose the change and ask to run /build.`
Same sentence for `edit`. Do not prompt. Do not print `|Tools Used|`.

`bash` and `powershell` stay in the schema in plan. Plan uses the same
`shell` ask as build. A rule denial is `Permission denied: …`, not
"disabled." Do not force-deny shell because the mode is plan.

## Post-pass — absolute paths and outside hits

Implemented after the first permissions pass. File-tool docstrings now say
`path` is absolute or workspace-relative and that outside asks permission;
`read` / `glob` / `grep` no longer say "in/under the sandbox". `SYSTEM`
states the workspace root, allows absolute paths, says a user-named file is
read with `read`, gives `glob` → `grep` → `read`, and names only the loaded
shell. `PLAN_SYSTEM` adds: if the user named a file, read that path; do not
glob first.

`glob` and `grep` also changed. After an outside root is approved, they no
longer call `file.relative_to(SANDBOX)` — that raised for a Desktop hit and
became `Tool error:`, which looked like success. If the root is outside, the
result is the file's absolute path with forward slashes; an inside root stays
workspace-relative. Same cap, same skips. `read` already returns the file.

This is a search-output fix, not a permission-model change. The approved
`Path` still bounds the walk.

## Skeleton

**Keep the loop. One new module. Gate at the existing dispatch.**

1. Keep: message flow, the raw assistant dict append, `MAX_STEPS = 16`,
   `SYSTEM`, `PLAN_SYSTEM`, `TOOLS` full, tool line
   `|Tools Used: \`name\` ({args})|` after a call that actually ran, status
   `{prompt:,} In | {out:,} Out | {session:,} Session | Elapsed: {_elapsed(elapsed)}`. No Tok/s.
2. Add: `src/minicode/permissions.py`. Stdlib only (`re`, `sys`). No new
   dep.
3. Add: `classify`, `approve`, and `clear_approved` in `resolve_path.py`.
   `_resolve` calls `classify`. An external path is still
   `Outside sandbox` unless that exact `Path` is in the per-call approved
   set. The set is not a boolean.
4. Replace: `PLAN_DENIED = ("write", "edit")`. The dispatch gate runs only
   when the name is not in that tuple and the tool is registered.
5. Add: the prompt in `__main__.py`, registered before the `while` loop.
   `agent.py` holds `ask = {"fn": None}`. `__main__.py` sets `fn`. A `None`
   fn denies. Do not import `__main__` from `agent.py`.

## Segment 1 — rules

File: `src/minicode/permissions.py`. No comments.

```python
import re
import sys

RULES = (
    ("read", "*", "allow"),
    ("glob", "*", "allow"),
    ("grep", "*", "allow"),
    ("edit", "*", "allow"),
    ("shell", "*", "ask"),
    ("external_directory", "*", "ask"),
)

ALWAYS: set[tuple[str, str]] = set()
ask = {"fn": None}


def norm(value: str) -> str:
    text = value.replace("\\", "/")
    if sys.platform == "win32":
        return text.casefold()
    return text


def _match(pattern: str, value: str) -> bool:
    parts: list[str] = []
    for ch in pattern:
        if ch == "*":
            parts.append(".*")
        elif ch == "?":
            parts.append(".")
        else:
            parts.append(re.escape(ch))
    return re.fullmatch("".join(parts), value) is not None


def check(key: str, value: str) -> str:
    seen = norm(value)
    action = "deny"
    for rule_key, pattern, effect in RULES:
        if rule_key == key and _match(norm(pattern), seen):
            action = effect
    if action == "ask" and (key, seen) in ALWAYS:
        return "allow"
    return action


def remember(key: str, value: str) -> None:
    ALWAYS.add((key, norm(value)))


def decide(key: str, value: str) -> str:
    action = check(key, value)
    if action != "ask":
        return action
    fn = ask["fn"]
    if fn is None:
        return "deny"
    choice = fn(key, value)
    if choice == "always":
        remember(key, value)
        return "allow"
    if choice == "once":
        return "allow"
    return "deny"
```

`check` walks `RULES` in order. A later match replaces the action. The
`ALWAYS` set is consulted only when the matched action is `ask`, so a
`deny` rule cannot be remembered away. This table has no `deny` row. The
fallback is `deny` for a key that is not in the table.

`decide` is what dispatch calls. `once` and `always` both return `allow`
for this call. Only `always` writes the set.

## Segment 2 — classify, then resolve

File: `src/minicode/resolve_path.py`. Keep `_sandbox_root` and `SANDBOX`.
Replace `_resolve`. `.env` is classified before the sandbox check, so an
outside `.env` is the refuse string, not `Outside sandbox`, and it never
asks.

```python
_approved: set[Path] = set()


def classify(path: str) -> tuple[str, Path]:
    p = (SANDBOX / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
    if p.name == ".env" or p.name.startswith(".env."):
        return "dotenv", p
    if p != SANDBOX and SANDBOX not in p.parents:
        return "external", p
    return "inside", p


def approve(path: Path) -> None:
    _approved.add(path)


def clear_approved() -> None:
    _approved.clear()


def _resolve(path: str) -> Path:
    kind, p = classify(path)
    if kind == "dotenv":
        raise ValueError("Refusing to access .env files")
    if kind == "external" and p not in _approved:
        raise ValueError(f"Outside sandbox: {path}")
    return p
```

`approve` stores the `Path` `classify` returned. Do not approve a string.
Do not set a flag that means "any escape is fine." `glob` and `grep` walk
under the root they resolve. A boolean would let that walk out.

The name check stays case-sensitive, as it is today. Do not widen it.
Shell's own `".env" in command.lower()` stays in `tools/shell.py`. Do not
unify the two strings. Shell says `Refusing to access .env file`. The path
gate says `Refusing to access .env files`.

## Segment 3 — dispatch gate

File: `src/minicode/agent.py`.

Import:

```python
import json

from minicode.permissions import decide
from minicode.resolve_path import SANDBOX, classify, approve, clear_approved
```

`json` is already imported. Do not import it twice. `SANDBOX` is for
`SYSTEM` (the workspace line in the post-pass), not for the gate.

Replace the denied set. Do not rename it. Do not filter `TOOLS`.

```python
PLAN_DENIED = ("write", "edit")
```

Add the key map and the gate next to `active_names`. `write` and `edit`
share `edit`. `bash` and `powershell` share `shell`. A name that is not in
the map is not a permission check. Unknown tools stay on the existing
string.

```python
KEYS = {
    "read": "read",
    "write": "edit",
    "edit": "edit",
    "glob": "glob",
    "grep": "grep",
    "bash": "shell",
    "powershell": "shell",
}


def _value(key: str, parsed: dict) -> str | None:
    if key in ("shell", "glob", "grep"):
        field = "command" if key == "shell" else "pattern"
        raw = parsed.get(field)
        return raw if isinstance(raw, str) else None
    raw = parsed.get("path")
    return raw if isinstance(raw, str) else None


def _permit(name: str, raw: str) -> str | None:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    path = parsed.get("path")
    if isinstance(path, str) and name in ("read", "write", "edit", "glob", "grep"):
        kind, resolved = classify(path)
        if kind == "dotenv":
            return "Refusing to access .env files"
        if kind == "external":
            shown = resolved.as_posix()
            if decide("external_directory", shown) == "deny":
                return f"Permission denied: external_directory {shown}"
            approve(resolved)
    key = KEYS.get(name)
    if key is None:
        return None
    value = _value(key, parsed)
    if value is None:
        return None
    if decide(key, value) == "deny":
        return f"Permission denied: {key} {value}"
    return None
```

A bad JSON body returns `None`. `run()` still returns `Invalid Arguments`.
Do not prompt on it. A missing `path` or `command` also returns `None` for
that check. `tool_from_fn` already reports the missing argument.

`external_directory` is checked first, then the tool key. An outside read
asks once, on the resolved path, because `read` is `allow`. An outside
edit asks once, on `external_directory`, because `edit` is `allow`. That
is how "read this checkout, do not edit it" will be expressible later,
when a `deny` row exists. Do not skip the tool-key check.

Replace the dispatch body. Keep the plan backstop first. Clear the
approved set after every registered call, including a denial that approved
a path and then failed the tool key. Do not clear it before `run()`
returns. `_resolve` has to see the path.

```python
            if mode["name"] == "plan" and name in PLAN_DENIED:
                content = f"Plan mode: `{name}` is disabled. Propose the change and ask to run /build."
            else:
                run = TOOLS.get(name)
                if run:
                    denied = _permit(name, args)
                    try:
                        if denied is not None:
                            content = denied
                        else:
                            content = run(args)
                            print(f"\n|Tools Used: `{name}` ({args})|\n")
                    finally:
                        clear_approved()
                else:
                    content = f"Unknown tool: {name}"
```

`|Tools Used|` prints only when `run()` was called, including when `run()`
returns `Tool error:`. A gate denial does not print it. An unknown name
does not print it. A plan denial does not print it.

Do not catch `KeyboardInterrupt` around `run()`. Ctrl+C during a shell
wait still kills the REPL. That is the streaming layer.

## Segment 4 — the prompt

File: `src/minicode/__main__.py`. Add the function. Register it at the
start of `main()`, before the `while` loop. Do not handle it as a slash
command.

```python
from minicode.permissions import ask as permission_ask


def _permission(key: str, value: str) -> str:
    print(f"\nPermission: {key} | {value}")
    try:
        answer = input("[o]nce / [a]lways / [d]eny: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return "deny"
    if answer in ("o", "once"):
        return "once"
    if answer in ("a", "always"):
        return "always"
    return "deny"
```

```python
    permission_ask["fn"] = _permission
```

Empty and anything other than `o` / `once` / `a` / `always` deny. Ctrl+C
on this prompt denies. It does not exit. Ctrl+C on `user >>` still exits,
as it does today.

The prompt can fire in the middle of a turn, while `agent()` is running.
That is the point. Do not buffer it until the status block.

## Soak

Product, from the repo:

```powershell
uv run python -m minicode
```

This machine registers `bash`. The same checks apply if the winner is
`powershell`. Do not soak with `&&`.

1. In-sandbox `write` runs with no prompt, then prints `|Tools Used|`.
2. `run git status` prints `Permission: shell` and the command. `deny`
   returns `Permission denied: shell git status` as `role: "tool"`, does
   not print a `Shell (` block, and does not print `|Tools Used|`.
   `always` skips the prompt only for that exact command. `git status
   --short` asks again.
3. A path outside the sandbox, such as `C:/Windows/win.ini` on this
   machine, prints `Permission: external_directory` and the resolved
   forward-slash path. `deny` does not call the tool. `once` reads that
   one path. A second outside path asks again.
4. `.env` inside the sandbox, and a `.env` outside it, return
   `Refusing to access .env files`. No prompt. No `|Tools Used|`.
5. `/plan` still hides `write` and `edit`. Tools Loaded does not include
   them. A guessed `write` is still `Plan mode: \`write\` is disabled`.
   A shell call in plan prompts. It is not "disabled." `/build` puts
   `write` and `edit` back. Shell still asks.

The fence is still for file tools:

```powershell
uv run python -m minicode --sandbox sandbox
```

`cwd` stays `SANDBOX`. Do not point it at the repo root. A command can
still `cd` out after the user allows that exact command. Do not parse it.

## Don't add yet

Later, in order, not in the implement pass: streaming and a Ctrl+C that
leaves a coherent turn, sessions. A permissions file and a durable
`always` wait with sessions. Do not write one now. Background bash stays
deferred. `/connect` stays with the catalog. Do not add the transport tag
here.

Not this layer: a shell scanner, prefix allows, `~` expansion, `--auto`,
env scrubbing, network limits, containers, killing a process tree,
symlink policy, `doom_loop`, v2's default-allow outside the sandbox.
`$env:GEMINI_API_KEY` is not an allow/ask/deny rule. Leave it.

## Checkpoint

1. Which key gates `write`? Which key gates `powershell`?
2. Why is an in-sandbox `edit` silent, while `shell` asks?
3. What does `always` store, and what does it not store?
4. What happens if `__main__.py` forgets to set `ask["fn"]`?
5. Why is the approved set a set of `Path`s, not a boolean?
6. In plan, is `bash` in the schema? What does a denied shell call say?
7. What string comes back for `.env` outside the sandbox? Is there a prompt?

Answers: (1) `edit`, and `shell`; (2) the sandbox already bounds the path,
and there is no command scanner, so the ask is the shell gate; (3) the
exact normalized value, in memory, until exit — not a widened glob, not a
file, and not a `deny`; (4) `decide` returns `deny`; (5) a boolean would
let `glob` or `grep` escape past the one path the user allowed; (6) yes,
and `Permission denied: shell …`, not `Plan mode: \`bash\` is disabled`;
(7) `Refusing to access .env files`, and no.
