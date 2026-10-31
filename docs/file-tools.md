# File tools

**Status:** shipped · **Layer:** 1 · **Files:** `tools/read.py`, `tools/write.py`, `tools/edit.py`
**Verified:** 2026-10-30

Three tools that read and change files. `read` is a spectator; `write` and
`edit` are the only things in the package that put bytes on disk outside the
shell.

Two tools, not one. `write` replaces a whole file; `edit` changes one exact
span. Merging them into an upsert is the mistake that makes an agent delete
work it did not understand.

## Contract

| Tool | Arguments | Returns |
|---|---|---|
| `read` | `path`, `offset=1`, `limit=2000` | line-numbered text, or `(empty file)` |
| `write` | `path`, `content` | `Wrote {n} bytes to {path}` |
| `edit` | `path`, `old_text`, `new_text` | `Replaced 1 occurrence in {path} ({where})` and a numbered window |

### `read`

`offset` is 1-based: `offset=1` is the first line, omitting it starts at the
top. Files and editors count from 1, so the API matches them.

Output is `{n}: {line}` per line, the same shape `edit` returns. `limit` caps
how much of a huge file enters the context; the default 2000 matches Pi's read
limit. Decoding uses `errors="replace"`, so a binary file returns replacement
characters instead of raising.

### `write`

Creates the file, or overwrites it completely. Parent directories are created.
`content` is the full final file, never a fragment.

Read before overwriting an existing file. A new file needs no read.

### `edit`

`old_text` must occur exactly once. Zero matches and more than one match both
raise `ValueError`, which the registry turns into `Tool error: ...` with the
file untouched.

An empty `old_text` is rejected before the match count; it would match
everywhere.

Insertions use an anchor: `old_text` is the existing text, `new_text` is that
same text plus what you want to insert after it.

The return value names the change and shows the result:

```text
Replaced 1 occurrence in notes.txt (changed 4 - 5)
1: first
2: second
3: third
4: new line
5: old line
```

`where` is `changed {first} - {last}` for a replacement or insertion, and
`deleted at {line}` for a deletion. The numbered body is the changed span plus
up to 5 lines before the first changed line and 5 after the last, clamped to
the file. An empty result is `(empty file)`.

The terminal also gets a one-shot diff, printed by `edit` itself:

```text
---
Diff: notes.txt
--- a/notes.txt (before)
+++ b/notes.txt (after)
@@ -2,2 +2,2 @@
 second
-third
+third, revised
---

```

The diff is for the person at the terminal. The model gets the numbered window,
not the diff. Neither is a diff viewer. The closing `---` always lands on its
own line: `end="---\n" if diff.endswith("\n") else "\n---\n"`. Diff input is
`splitlines()` plus `\n`, not `keepends=True`, so a file with no trailing
newline cannot fuse a `-` line and a `+` line.

## Why this shape

**Exact text, not line numbers.** Lines drift as a file changes. Text that is
unique is a stable handle; a line number is stale before the second edit.

**Unique, not first match.** A silent first-match replace on a string that
appears three times is an unrecoverable mistake. Failing loudly lets the model
widen the span and retry.

**Separate `write` and `edit`.** `write` asserts "this is the whole file";
`edit` asserts "this is one span". One tool that guesses between them removes
the distinction that makes either safe.

**The diff goes to the terminal, the window to the model.** The diff answers
"what did it actually do" for a human, in a form that does not consume context.
The window gives the model enough surrounding text to confirm line numbers for
its next edit without resending the file.

**The routing rule lives in `SYSTEM`.** Only the first docstring line reaches
the model, so "a new file is `write`, a partial change is `read` then `edit`"
cannot live in a tool description.

## Invariants

- `old_text` non-empty; exactly one match; the file is not written on failure.
  `tools/edit.py`.
- `write` content is the full file. There is no partial mode.
- Every tool goes through `_resolve`, so the workspace boundary and the `.env`
  rule apply to all three equally.
- The diff prints before the function returns, so it always appears above the
  tool line.
- Diff input is `splitlines()` plus `\n`, not `keepends=True`, so a file with no
  trailing newline cannot fuse a removed and an added line.
- The diff's closing `---` always lands on its own line.

## Edge cases

| Input | Result |
|---|---|
| `read` missing file | `Tool error: ...` |
| `read` empty file | `(empty file)` |
| `write` with no `content` | `Invalid Arguments: ...` |
| `edit` with 0 matches | `Tool error: old_text not found in {path}` |
| `edit` with 2 matches | `Tool error: old_text found 2 times in {path}` |
| `edit` with empty `old_text` | `Tool error: old_text must not be empty` |
| `edit` deleting the last line | `deleted at {line}`, possibly `(empty file)` |
| a path outside the workspace | permission prompt, then allow or deny |
| a `.env` path | permission prompt; `.env.example` is exempt |
| a file with no trailing newline | diff stays two separate lines |

## Verification

- `read` a file with 3 lines: output is `1: ...` through `3: ...`.
- `write` a new path with a nested parent: the directories exist.
- `edit` a unique string: the file changes, the diff prints, the model window
  shows the span plus context.
- `edit` the same string twice in one file: `Tool error:` and the file is
  unchanged.
- `edit` with `old_text` that does not exist: `Tool error:`.
- Insert with an anchor: the original text is preserved and the new text
  follows it.
- Diff a file with no trailing newline: no fused `-`/`+` pair.

## Gaps

- No diff viewer, no undo, no backup. A wrong `write` is unrecoverable from the
  tool side.
- `edit` is one span per call. Three edits in one file need three calls.
- No line-range replacement; that needs unique anchors instead.
- No binary write. Everything is UTF-8 text.

## History

- 2026-09-21  `write` and `edit` arrived with the one-shot diff.
- 2026-10-04  The `SYSTEM` sentence was split so whole-file overwrite and span
  edits are described separately.
- 2026-10-22  The diff input changed from `keepends=True` to `splitlines()` plus
  `\n` to stop a final line without a newline from fusing with the next diff
  line.
