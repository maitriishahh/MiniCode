# 02 — write + edit + diff print

Do first: `docs/01-loop.md` (loop, sandbox, `read`, REPL). Layer 0 is in
`src/minicode/__main__.py`. This guide grows that same file.

## What you'll build

Layer 1: two more tools, same registry, same loop. `write` creates or
overwrites. `edit` replaces one exact unique span. A successful `edit` prints
a short unified diff to stdout (not a viewer). Still one growing module.
Still no shell.

## Why it matters

`read` without `write`/`edit` is a spectator. These two are the first tools
that change the sandbox. Get uniqueness, escapes, and `.env` denial right
before anything else writes.

## Skeleton

**Keep the loop. Grow the registry.**

1. Keep: `tool_from_fn`, `_resolve`, `read`, `run_agent`, REPL, tool line,
   status block. Do not touch the message flow.
2. Reword `_resolve`'s `.env` error from "read" to "access" — `write`/`edit`
   use it too.
3. Add `write` and `edit` next to `read`. Wire them: `for _fn in (read, write, edit):`.
4. A successful `edit` prints a stdlib `difflib.unified_diff` to stdout, then
   returns a short string to the model. The existing
   `Tool: `{name}` executed` line still prints after the tool returns.

## Segment 1 — `_resolve` error text

The sandbox gate is already correct (cwd, no `..` escape, no `.env*`). Only
the error string is `read`-specific. Replace it:

```python
    if p.name == ".env" or p.name.startswith(".env."):
        raise ValueError("Refusing to access .env files")
```

Keep the rest of `_resolve`. `read` / `write` / `edit` all go through it, so
escapes and `.env` stay tool errors, never tracebacks.

## Segment 2 — `write`

Add this next to `read`. Google-style docstring, no `Returns:` block.

```python
def write(path: str, content: str) -> str:
    """Write text to a file in the sandbox, creating parent directories.

    Args:
        path: Path to the file, relative to the sandbox
        content: Full file contents to write
    """
    target = _resolve(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"Wrote {len(content.encode('utf-8'))} bytes to {path}"
```

New files or full rewrites — same function. Parents are created. Overwrite is
YOLO inside the sandbox (HARNESS §5). Missing `content` is a `ValidationError`
string from `tool_from_fn`, not a crash.

**Expected:** "write hello.txt with hello" → `Tool: `write` executed`, file
on disk, status `Tools:` lists `read,write,edit` once the registry includes
them. `../secret` or `.env` → tool-error string.

## Segment 3 — `edit` + one-shot diff

Exact match only. Line numbers drift; unique text is the stable handle.
`0` or `>1` matches raise — `tool_from_fn` turns that into `Tool error: …`
and the model can retry. Empty `old_text` would match everywhere; reject it.

```python
import difflib

def edit(path: str, old_text: str, new_text: str) -> str:
    """Replace exact unique text in a sandbox file.

    Args:
        path: Path to the file, relative to the sandbox
        old_text: Exact text to find (must match once)
        new_text: Replacement text
    """
    if not old_text:
        raise ValueError("old_text must not be empty")
    target = _resolve(path)
    original = target.read_text(encoding="utf-8", errors="replace")
    n = original.count(old_text)
    if n == 0:
        raise ValueError(f"old_text not found in {path}")
    if n > 1:
        raise ValueError(f"old_text matched {n} times in {path}; must be unique")
    updated = original.replace(old_text, new_text, 1)
    diff = "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            updated.splitlines(keepends=True),
            fromfile=path,
            tofile=path,
        )
    )
    if diff:
        print(diff, end="" if diff.endswith("\n") else "\n")
    target.write_text(updated, encoding="utf-8")
    return f"Replaced 1 occurrence in {path}"
```

Put `import difflib` with the other imports at the top of `__main__.py`.

The diff is for **you** (REPL stdout). The model gets the short return
string. This is not a diff viewer — that stays deferred. `difflib` is
stdlib; do not add a package.

Print the diff **inside** `edit`, before the function returns. Then
`run_agent` prints `Tool: `edit` executed` as it already does for any
successful tool. Do not add a special case in the loop.

**Expected:** unique `old_text` → file changes, a unified diff on stdout,
`Tool: `edit` executed`. Zero matches or two copies of `old_text` →
`Tool error: …` as `role: "tool"` content, file unchanged, model retries.
Missing file → `Tool error:` from the exception.

## Segment 4 — Registry

Replace the one-tool loop:

```python
for _fn in (read, write, edit):
    _schema, _run = tool_from_fn(_fn)
    TOOLS[_fn.__name__] = _run
    SCHEMAS.append(_schema)
```

That is the whole dispatch change. `run_agent` already looks up
`TOOLS.get(call.function.name)`. Status `Tools:` is `','.join(TOOLS)` — it
will show `read,write,edit` with no REPL edits.

Do **not** add `if/elif` on tool names. Do **not** change `SYSTEM`, the
prompt, token summing, or Tok/s.

## Your finished module

Same file as Layer 0, plus `write`, `edit`, `difflib`. Roughly 220–280
lines. Still no `loop.py` / `tools.py` split — the file is not awkward yet.

## Don't add yet

shell, plan/build swap (`/plan` dropping `write`/`edit`), permissions UI,
Rich, streaming, sessions, compaction, cost, diff **viewer**, `/model`.
Plan mode without a restricted tool list is still later — but now there is
something to restrict, which is why this layer comes first.

If the agent can create a file, overwrite it, edit one unique span, fail
cleanly on 0/>1 matches and on escapes/`.env`, and print a short diff —
stop.

## Checkpoint

1. Where do `write` and `edit` get registered, and how does `run_agent` find
   them?
2. What happens on 0 matches? On 2? Does the file change?
3. Who sees the unified diff — the model, the REPL, or both?
4. Why must `old_text` be non-empty?
5. Why does `_resolve` still run for `write`/`edit`?

Answers: (1) `for _fn in (read, write, edit)` → `TOOLS` / `SCHEMAS`;
`run_agent` is unchanged (`TOOLS.get`); (2) `ValueError` → `Tool error: …`,
file untouched; (3) REPL stdout only — the model gets `Replaced 1 occurrence
in {path}`; (4) empty `old_text` matches every position; (5) same sandbox and
`.env` gate as `read`.
