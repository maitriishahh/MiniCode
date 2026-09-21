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
4. Extend `SYSTEM` with the routing rule: `write` = whole-file
   create/overwrite, `edit` = one exact unique span, `read`-before-partial
   change. Keep `write` and `edit` separate — never merge them into one
   upsert tool. (Only the first docstring line reaches the model, so the
   routing rule must live in `SYSTEM`, not in per-tool docstrings.)
5. A successful `edit` prints a stdlib `difflib.unified_diff` to stdout, then
   returns a short string to the model. The existing
   `---\nTools Used: `{name}`\n---` line still prints after the tool returns.

## Segment 1 — `_resolve` error text

The sandbox gate is already correct (cwd, no `..` escape, no `.env*`). Only
the error string is `read`-specific. Replace it:

```python
    if p.name == ".env" or p.name.startswith(".env."):
        raise ValueError("Refusing to access .env files")
```

Keep the rest of `_resolve`. `read` / `write` / `edit` all go through it, so
escapes and `.env` stay tool errors, never tracebacks.

## Segment 2 — `write` + `SYSTEM` routing rule

Add this next to `read`. Google-style docstring, no `Returns:` block.
Only the first line reaches the model — the add/append/insert routing rule
goes in `SYSTEM` (step 4 of the Skeleton), not here.

```python
SYSTEM = ("You are a concise coding assistant. Use tools when they help. Be brief. "
  "Read before mutating. `write` creates or overwrites whole files with complete content; "
  "`edit` changes one exact unique span. For add/append/insert or replace X with Y, `read` then `edit`; "
  "never `write` with partial content.")

def write(path: str, content: str) -> str:
    """Create a new file or overwrite an entire existing file with complete content.

    Args:
        path: Path to the file
        content: FULL final file contents — replaces everything
    """
    target = _resolve(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"Wrote {len(content.encode('utf-8'))} bytes to {path}"
```

New files or full rewrites — same function. Parents are created. Overwrite is
YOLO inside the sandbox (HARNESS §5). Missing `content` is a `ValidationError`
string from `tool_from_fn`, not a crash. `write` is never used for partial
changes: "add X to the file" means `read` then `edit`, not `write`.

**Expected:** "write hello.txt with hello" → `---\nTools Used: `write`\n---`,
file on disk, status `Tools Loaded:` lists `read,write,edit` once the registry
includes them. `../secret` or `.env` → tool-error string.

## Segment 3 — `edit` + one-shot diff

Exact match only. Line numbers drift; unique text is the stable handle.
`0` or `>1` matches raise — `tool_from_fn` turns that into `Tool error: …`
and the model can retry. Empty `old_text` would match everywhere; reject it.

```python
import difflib

def edit(path: str, old_text: str, new_text: str) -> str:
    """Replace one exact unique span in an existing file.
    Use for any partial change: replacements, insertions (old_text=anchor, new_text=anchor+insertion), deletions.
    Read the file first for exact text. Never rewrite the whole file; use `write` instead.

    Args:
        path: Path to the file
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
        raise ValueError(f"old_text found {n} times in {path}")
    updated = original.replace(old_text, new_text, 1)
    diff = "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            updated.splitlines(keepends=True),
            fromfile=f"a/{path} (before)",
            tofile=f"b/{path} (after)",
            lineterm="\n",
        )
    )
    if diff:
        print(f"---\nDiff: {path}\n{diff}", end="---\n" if diff.endswith("\n") else "\n---\n")
    target.write_text(updated, encoding="utf-8")
    return f"Replaced 1 occurrence in {path}"
```

Put `import difflib` with the other imports at the top of `__main__.py`.

The diff is for **you** (REPL stdout). The model gets the short return
string. This is not a diff viewer — that stays deferred. `difflib` is
stdlib; do not add a package.

Print the diff **inside** `edit`, before the function returns. Then
`run_agent` prints `---\nTools Used: `edit`\n---` as it already does for any
successful tool. Do not add a special case in the loop.

**Expected:** unique `old_text` → file changes, a `---\nDiff: {path}` block
with `a/{path} (before)` / `b/{path} (after)` headers on stdout,
`---\nTools Used: `edit`\n---`. Zero matches or two copies of `old_text` →
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
`TOOLS.get(call.function.name)`. Status `Tools Loaded:` is `', '.join(TOOLS)` —
it will show `read,write,edit` with no REPL edits.

Do **not** add `if/elif` on tool names. Do **not** merge `write` and `edit`.
Do not change token summing or Tok/s. The only prompt change in this layer is
the `SYSTEM` routing rule from Segment 2.

## Your finished module

Same file as Layer 0, plus `SYSTEM` routing rule, `write`, `edit`,
`difflib`. Roughly 230–280 lines. Still no `loop.py` / `tools.py` split —
the file is not awkward yet.

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
6. When the user says "add X to the file", which tool runs — and why never
   `write` with partial content? Where does that routing rule live?

Answers: (1) `for _fn in (read, write, edit)` → `TOOLS` / `SCHEMAS`;
`run_agent` is unchanged (`TOOLS.get`); (2) `ValueError` → `Tool error: …`,
file untouched; (3) REPL stdout only — the model gets `Replaced 1 occurrence
in {path}`; (4) empty `old_text` matches every position; (5) same sandbox and
`.env` gate as `read`; (6) `read` then `edit` (insert via anchor), because
`write` replaces the whole file — the rule lives in `SYSTEM`, since only the
first docstring line reaches the model.
