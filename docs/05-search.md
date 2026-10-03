# 05 — Search: glob + grep, capped

Do first: `docs/04-workspace.md`. Layer 3 is done. This layer is not
implemented yet. Write this guide first, then implement it in `tools/`.

All search phases live in this one doc as segments — not one doc per tool.
Registry and the loop live in `agent.py`. Sandbox stays in
`resolve_path.py`. A new tool is `tools/<name>.py` plus one registry line in
`agent.py`. Do not grow `__main__.py` with tools.

## What it is

Two capped tools, three segments, one layer:

1. `glob` — file-name search under the sandbox, up to 50 paths.
2. `grep` — content search under the sandbox, up to 50 matches as
   `path:line: text`.
3. `include` — a glob filter on `grep` (e.g. `*.py`), same 50-match cap.

Still no shell.

## Why it matters

`read` needs a known path. Since Layer 3 the workspace is the launch cwd,
so real trees are large and the model cannot guess paths. Name search finds
the file, content search finds the text, the filter keeps both cheap. Each
call is bounded, so a broad pattern cannot flood the context — the model
refines and retries instead.

## Skeleton

**Keep the loop. Grow the registry.**

1. Keep: tools, `SYSTEM` routing for `write`/`edit`, message flow,
   `_resolve`, `.env` denial, escape error, tool line, status block
   `{prompt:,} In | {out:,} Out | Elapsed: {elapsed:.1f}s`. No Tok/s.
2. Add: `src/minicode/tools/glob.py` (Segment 1), then
   `src/minicode/tools/grep.py` (Segments 2–3). Stdlib only (`pathlib`,
   `re`). No new deps.
3. Wire them: `for _fn in (read, write, edit, glob, grep):`. Status `Tools
   Loaded:` picks them up with no REPL edits.
4. Extend `SYSTEM` with one routing sentence: locate with `glob`, confirm
   with `grep`, then `read` before mutating.
5. Do not touch `SANDBOX`, the registry record shape, or `__main__.py`.

## Segment 1 — `glob` (file names)

File: `src/minicode/tools/glob.py`. Google-style docstring, no `Returns:`
block. Only the first line reaches the model.

```python
def glob(pattern: str, path: str = ".", limit: int = 50) -> str:
    """List files under the sandbox whose names match a glob pattern.

    Args:
        pattern: Glob pattern, e.g. *.py or test_*
        path: Subtree root, relative to the sandbox
        limit: Maximum paths to return
    """
```

Behavior the guide locks:

- `path` resolves via `_resolve`. Escapes and `.env*` are tool errors,
  never tracebacks. A missing root is a tool error, not a crash.
- `pattern` matches against file names (`Path.match`). Directories are
  walked, not listed — this tool finds files, it does not browse.
- Skip dot-dirs, `__pycache__`, and `.venv`. Results are relative paths
  from the sandbox, one per line, sorted.
- Cap: at most 50 lines (hard-max even if `limit` is larger). Past the cap,
  append one line: `... and N more — refine pattern`. An empty result says
  `(no matches)`.

**Expected:** "find test files" → `|Tools Used: `glob`|` and a short path
list. `../secret` or `.env` → tool-error string the model acknowledges.

## Segment 2 — `grep` (content)

File: `src/minicode/tools/grep.py`. Same docstring rules. `re` search, not
a shell call.

```python
def grep(pattern: str, path: str = ".", limit: int = 50) -> str:
    """Search file contents under the sandbox for a regex pattern.

    Args:
        pattern: Regex pattern to search for
        path: Subtree root, relative to the sandbox
        limit: Maximum matches to return
    """
```

Behavior the guide locks:

- Same root rules as `glob`: `_resolve`, escapes and `.env*` denied, same
  skip list (dot-dirs, `__pycache__`, `.venv`).
- Unreadable and binary-looking files are skipped silently (read with
  `errors="replace"`, skip on `NUL` bytes). A file that cannot be read is
  never a crash — the tool returns what it found.
- Output is `relpath:line: text`, one match per line, capped at 50
  (hard-max). Past the cap, append: `... and N more — refine pattern`.
  An empty result says `(no matches)`.
- Invalid regex is a tool error (`re.error` as a string) so the model can
  retry — same contract as `ValidationError` strings from `tool_from_fn`.

**Expected:** "where is `_sandbox_root` defined" → `|Tools Used: `grep`|`
plus `resolve_path.py:4: def _sandbox_root...`. A bad pattern → tool-error
string, model retries.

## Segment 3 — `include` filter on `grep`

Same file: `src/minicode/tools/grep.py`. No new tool — one more parameter:

```python
def grep(pattern: str, path: str = ".", include: str = "*", limit: int = 50) -> str:
    """Search file contents under the sandbox for a regex pattern.

    Args:
        pattern: Regex pattern to search for
        path: Subtree root, relative to the sandbox
        include: Only search files whose names match this glob, e.g. *.py
        limit: Maximum matches to return
    """
```

- `include` filters file names exactly like Segment 1's `pattern`
  (`Path.match`), before contents are read. Default `*` keeps Segment 2
  behavior. The 50-match cap and truncation line are unchanged.
- Docstring rule still holds: only the first line plus `Args:` entries reach
  the model — the `glob`-then-`grep`-then-`read` routing stays in `SYSTEM`,
  not in per-tool docstrings.

## Segment 4 — Registry + `SYSTEM`

File: `src/minicode/agent.py`. Replace the registry loop:

```python
for _fn in (read, write, edit, glob, grep):
    _schema, _run = tool_from_fn(_fn)
    TOOLS[_fn.__name__] = _run
    SCHEMAS.append(_schema)
```

Extend `SYSTEM` with one sentence (keep the existing routing rule intact):

```
"Locate with `glob`, confirm with `grep`, then `read` before mutating."
```

Do **not** add `if/elif` on tool names. Do not change `In | Out |
Elapsed: {elapsed:.1f}s`. Status `Tools Loaded:` becomes
`read,write,edit,glob,grep` with no REPL edits.

## Your finished modules

`glob` and `grep` live in `tools/`. `SYSTEM` and the registry live in
`agent.py`. Skip lists live in each tool, not in the loop. Do not merge
these back into `__main__.py`.

## Don't add yet

Shell, plan/build swap (`/plan` dropping `write`/`edit`), permissions UI,
Rich, streaming, sessions, compaction, cost, diff **viewer**, recursive
`exclude` rules, case-insensitive flags, context lines (`-C`). If the agent
can name a file, find text, narrow with `include`, fail cleanly on escapes /
`.env` / bad regex, and stay capped — stop.

## Checkpoint

1. Where do `glob` and `grep` get registered, and how does `agent` find
   them?
2. What happens past 50 results — truncated silently, or what?
3. Who skips `__pycache__` / `.venv` — the loop or each tool?
4. What happens on `../` escapes, `.env`, and an invalid regex?
5. When the user says "where is X defined", which tools run in which order —
   and where does that routing rule live?
6. Why is `include` a parameter on `grep` and not a third tool?

Answers: (1) `for _fn in (read, write, edit, glob, grep)` → `TOOLS` /
`SCHEMAS`; `agent` looks up `TOOLS.get(call["function"]["name"])`;
(2) capped at 50 plus `... and N more — refine pattern`, never silent;
(3) each tool — the loop never filters; (4) escapes / `.env` are
`ValueError` → `Tool error: …`, bad regex is `re.error` → tool-error
string, files unchanged; (5) `glob`, then `grep` with `include`, then
`read` — the rule lives in `SYSTEM`, since only the first docstring line
reaches the model; (6) it filters before reading, same cap, no new registry
entry — one finished layer, not three.
