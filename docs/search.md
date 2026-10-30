# Search

**Status:** shipped · **Layer:** 3 · **Files:** `tools/glob.py`, `tools/grep.py`
**Verified:** 2026-10-30

`read` needs a path. `glob` finds the path, `grep` finds the line, `read` opens
it. Both searches are capped, so a broad pattern cannot flood the context; the
model narrows and retries instead.

## Contract

| Tool | Arguments | Returns |
|---|---|---|
| `glob` | `pattern`, `path="."`, `limit=50` | one path per line, sorted |
| `grep` | `pattern`, `path="."`, `include="*"`, `limit=50` | `{path}:{line}: {text}` per match |

Both resolve `path` through `_resolve` and require a directory:

```text
Tool error: Not a directory: {path}
```

`glob` matches `pattern` against file names only (`Path.match`). Directories are
walked, never listed, so the tool finds files and does not browse. `grep`
matches `pattern` as a regular expression against each line, using `search`, so
a line matches if the pattern occurs anywhere in it. `include` is a name filter
applied before the file is opened.

Output is one entry per line, in forward-slash form whether or not the host is
Windows:

```text
docs/search.md
src/minicode/tools/grep.py:12: _resolve(path)
```

An inside root returns workspace-relative paths. An outside root, after the
permission prompt allows it, returns absolute forward-slash paths. `glob` sorts
its paths; `grep` sorts `(path, line, text)` tuples.

### Caps

`limit` is clamped to `0..50`, so a larger argument cannot raise the ceiling and
a negative one cannot slice from the end. Past the cap, one extra line is
appended:

```text
... and N more — refine pattern
```

An empty result is `(no matches)`, never an empty string. On a search with
hits, `limit=0` returns only the `... and N more` line.

### Skips

| Skipped | By |
|---|---|
| directories starting with `.` | both |
| `__pycache__`, `.venv` | both |
| `.env` and `.env.*` file contents | `grep` always |
| files that cannot be opened | `grep` |
| files containing a NUL byte | `grep` |

`glob` never reads contents, so it lists a `.env` name whenever the pattern
matches it — the name is not the secret. The `.env` skip that survives is on
contents: `grep` will not report a line from one, and `read` asks permission
(`docs/permissions.md`).

Both walks are complete before the cap is applied. The cap bounds the output,
not the work.

## Why this shape

**Capped, not trimmed.** A search that silently returns the first thousand
paths teaches the model that the tree is small. The truncation line states that
more exists and says what to do about it, so the next call is narrower.

**`include` is a parameter, not a third tool.** Filtering names before opening
files is one comparison, and splitting it into a tool would add a registry
entry, a schema, and a round trip for it.

**Regex in-process, not a shell call.** `grep` on a shell would need the shell
tool to be loaded, the shell to be permitted, and the output to survive the
8000-character cap. It also would not respect the workspace boundary. `re`
does none of that.

**The locate order lives in `SYSTEM`.** Only the first docstring line and the
`Args:` entries reach the model (`docs/tool-registry.md`), so
`glob` → `grep` with `include` → `read` cannot be taught from a tool
description. It is one sentence in `SYSTEM` in `agent.py`.

**Names are public, contents are not.** Since permissions landed, `.env` names
can be listed and only the contents are gated. `grep` skips them entirely rather
than prompting per file, because a search over a secret is rarely what the user
meant.

## Invariants

- The 50 ceiling is a hard maximum. `tools/glob.py`, `tools/grep.py`.
- The truncation line is `... and N more — refine pattern`, with that dash.
- An empty result is `(no matches)`, never `""`.
- `relative_to(SANDBOX)` is only applied when the root is inside the workspace.
  An outside hit is printed absolute, because the old unconditional call raised
  and the turn only saw a tool error.
- Skip lists live in each tool, not in the loop or in `SYSTEM`.
- A missing or non-directory root is `ValueError`, which the registry returns as
  `Tool error:`.
- An invalid regex raises `re.error` out of `grep` — `re.PatternError` is the
  same class on Python 3.13 — and comes back as `Tool error: ...`.

## Edge cases

| Input | Result |
|---|---|
| `glob` on a non-directory `path` | `Tool error: Not a directory: {path}` |
| `glob` with a pattern that matches nothing | `(no matches)` |
| `glob` with `limit=100` | 50 paths, then `... and N more — refine pattern` |
| `glob` with `limit=0` and hits | no paths, one `... and N more` line |
| `grep` with an invalid regex | `Tool error: ...` from `re.error`, files untouched |
| `grep` pattern containing `\n` | never matches; matching is line by line |
| `grep` on a binary file | skipped on the NUL byte, no error |
| `grep` on an unreadable file | skipped silently |
| `path` outside the workspace | permission prompt; deny returns `Permission denied: external_directory {path}` |
| `path` that does not exist | `Tool error: ...` from `_resolve` |

## Verification

- `glob` for `*.py` in `src/minicode/tools` lists seven files, workspace-relative.
- `glob` with `limit=1` shows one path plus `... and 6 more — refine pattern`.
- `grep` for `_sandbox_root` with `include=*.py` returns two hits in
  `src/minicode/resolve_path.py`, the first being
  `src/minicode/resolve_path.py:7: def _sandbox_root() -> Path:`.
- `grep` for a pattern that exists only in `.env` returns `(no matches)`.
- `grep` with `[` as the pattern returns `Tool error:`.
- Both tools on `.` never descend into `.venv`.
- An outside root returns absolute paths with forward slashes.

## Gaps

- No case-insensitive flag, no context lines, no exclude glob, no multiline
  mode.
- The cap counts matches, not files, so one chatty file can fill all 50.
- `grep` reads each candidate file whole into memory. A very large file in a
  narrow search still costs its full size.
- Neither tool has a timeout. The walk finishes before any cap applies.
- The `pattern in ("*", ".*", ".env*")` branch in `glob` is redundant:
  `Path.match` already matches those patterns, so the branch never changes the
  result. Harmless, but it reads like a rule that is not there.

## History

- 2026-10-04  `glob` and `grep` arrived with the cap and the truncation line.
- 2026-10-05  `grep` gained `include`. The same commit fixed `glob` returning
  early and the truncation wording.
- 2026-10-23  An outside root stopped raising: paths became absolute and the
  `relative_to` call was made conditional.
- 2026-10-25  `.env` reads became a permission ask instead of a hard refusal, so
  `glob` started listing `.env` names. `grep` still skips their contents.
