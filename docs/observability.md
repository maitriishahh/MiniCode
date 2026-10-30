# Observability

**Status:** shipped · **Layer:** 7-8 · **Files:** `__main__.py`, `agent.py`
**Verified:** 2026-10-30

MiniCode prints four kinds of output while it works: the reasoning block, the
answer, one line per successful tool call, and a status block after the turn.
This doc owns the format of all of them and the arithmetic behind the token
counts. Every other doc points here instead of restating it.

## Contract

### Status block

`__main__._status` prints it at startup, after `/new`, after a resume, and after
every turn. It is fenced with `---` on its own line above and below:

```text
---
Model: gemini-3.5-flash-lite | Mode: plan | Tools Loaded: read, glob, grep, bash
Sandbox: C:\path\to\project | Thinking: off | Effort: low | Args: off | Output: off
1,204 In | 48 Out | 96 Session | Elapsed: 2.1s
---
```

- Line 1 is `active["id"]`, `mode["name"]`, and `active_names()`, comma-space
  separated. Plan omits `write` and `edit` and nothing else.
- Line 2 is the flags, in that order. `Thinking` comes from `__main__`, the
  other three from `agent` and `tools/shell.py`.
- Line 3 is omitted entirely when `last_turn["Elapsed"]` is `None`. That is the
  case at startup and after `/new`, which is why those prints have no usage
  line.
- No blank line inside the block. Exactly two `---` lines.

### The usage line

`__main__._usage` builds it:

```text
{prompt:,} In | {completion:,} Out | {session:,} Session | Elapsed: {_elapsed}
```

| Field | Source | Rule |
|---|---|---|
| `In` | `last_usage["prompt_tokens"]` | The last model call of the turn only. Overwritten, never summed. A resent prompt is not new work. |
| `Out` | `last_usage["completion_tokens"]` | Summed across the steps of this turn. |
| `Session` | `session_usage["completion_tokens"]` | Conversation lifetime. Summed across turns, saved in the session file, restored on resume. |
| `Elapsed` | wall clock around `agent()` | `time.perf_counter()` in the REPL, formatted by `_elapsed`. |

`prompt_tokens` is never added to `Session`. `last_usage` resets at the start
of `agent()`; `session_usage` resets only on `/new` or deleting the active
session. An aborted stream adds no usage: `_apply_usage` runs only after a
successful `_consume`.

A context percentage is appended only when the model record has a
`context_window`:

```text
1,204 In | 48 Out | 96 Session | Elapsed: 2.1s | 1.2% context
```

Every record carries `context_window: None` today, so the suffix never prints.
The rule is kept because setting a verified window is the whole change needed
to turn it on.

### `_elapsed`

Under 60 seconds keeps one decimal and an `s`: `45.2s`. A formatted `60.0`
rolls to `1m`. At or above 60 seconds it rounds to whole seconds and shows the
two largest units from `y w d h m s`, dropping a zero remainder.

| Input | Output |
|---|---|
| `0.0` | `0.0s` |
| `45.23` | `45.2s` |
| `59.99` | `1m` |
| `1433.8` | `23m 54s` |
| `864000` | `1w 3d` |
| `34560000` | `1y 5w` |

A week is 7 days. A year is 365 days. There is no month unit.

### Tool line

Printed after a tool runs successfully, never before. `agent._tool_line`.

```text
|Tool Used: `read`
|Tool Used: `read` ({...})|
```

`/args off` is the default and produces the first form. `/args on` produces the
second. When any argument value is a string containing a newline, the line
becomes a left rail instead: the header is `|Tool Used: `name`` with no trailing
bar, then one `|` line per real line of the value, with the key prefixed on the
first line of that value and no trailing `|` on any of them.

```text
|Tool Used: `write`
|path: notes.txt
|content: first line
|second line
```

The value is re-read from the JSON, not re-serialized.

A plan denial, a permission denial, a `Tool error:`, an `Invalid Arguments:`,
an `Unknown tool:`, or a model error prints as a plain notice instead. No
`|Tool Used|` line for any of them.

### Reasoning block

Only when the provider sends reasoning and `/thinking` is `on`:

```text
Thinking:
---
the summary text
---

the answer
```

`Thinking:` on its own line, `---` on the next, the text, then `---` on a line
after the last reasoning line, then a blank line. Trailing newlines in the
summary are held back so the closer never sits on the same line as the text; a
blank line in the middle of the summary still prints. There is no `Thought:`
closer.

`/thinking off` prints `Thinking:` and nothing else. With no reasoning from the
provider, no label appears at all.

A reasoning block closes before a tool preamble, before a `|Tool Used|` line, or
before the answer. A reasoning-only reply with null content prints the block,
then `[empty response]`.

`<thought>` and `<think>` spans are pulled out of `content` before it is treated
as answer text, then dropped. They never enter history.

### Notices

| String | When |
|---|---|
| `[interrupted by user]` | Ctrl+C during a model call or a tool call |
| `[empty response]` | the model returned no text and no tool calls |
| `[model error]` | marker written into history when the call raised |
| `Model Error: {exc}` | the raised call, printed once with no fence |
| `Max limit reached: 16. Try smaller request.` | the turn hit `MAX_STEPS` |

A `Model Error:` and a max-limit notice print as plain text, not as an answer
and not inside the status block.

### Shell block and diff

Independent of the status block:

```text
---
Shell (bash):
exit 0
...

---
```

`/output on` shows it. `/output off` is the default and hides it; the model
still receives the same text. The label is the loaded dialect: `bash`, `sh`, or
`powershell`.

An `edit` diff always prints, regardless of `/output`:

```text
---
Diff: path/to/file.py
--- a/path/to/file.py (before)
+++ b/path/to/file.py (after)
@@ ...
---

```

## Why this shape

The status block is the only thing in the REPL that reports cost, so it is one
block, printed in one place, and never duplicated on a per-tool line. Pi and
OpenCode both expose a footer that is rewritten in place; MiniCode prints a new
block per turn because `input()` owns the terminal and a rewrite would fight
the streamed answer.

`In` is the last call and `Out` is the sum, rather than both being sums, because
the prompt is resent on every step of a turn. Summing `In` would count the same
tokens four times in a four-step turn and the number would mean nothing.

There is no tokens-per-second figure. Wall clock is network wait, not model
speed, and the summed `total_tokens` in `usage` counts the prompt once per
step, so any rate derived from it is wrong in two directions at once.

## Invariants

- `last_usage["prompt_tokens"]` is assigned, never added. `agent._apply_usage`.
- `session_usage` is incremented only from `completion_tokens`. Never from
  `prompt_tokens`.
- `session_usage` survives resume and dies on `/new` and on deleting the active
  session. `__main__._reset_current`, `__main__._apply_session`.
- The status block prints exactly one usage line, or none.
- A denial prints through `_tool_note`, never through `_tool_line`.
  `agent.agent`.

## Verification

- Startup: `Type /help for available commands`, then a block with two `---`
  lines and no usage line.
- One prompt: one answer, one status block, one usage line, then `>>> `.
- A tool prompt: exactly one `|Tool Used:` line, printed after the result.
- `/args on` with a multiline `write`: a left rail, no trailing `|`.
- `/output on`, then a shell prompt: a `Shell (bash):` block inside `---`.
- `/output off`: the same prompt shows no shell block, and the model still
  reports the output in its answer.
- `/thinking on` with a reasoning model: `Thinking:` / `---` / text / `---` /
  blank line. `/thinking off`: only `Thinking:`.
- Ctrl+C mid-stream: partial text, `[interrupted by user]`, status block, then
  `>>> `.
- 16 steps: `Max limit reached: 16. Try smaller request.` printed plain.

## Gaps

- Cache-read and cache-write tokens are in `usage` but not displayed. The next
  piece of work is cache control; see `docs/STATUS.md`.
- No cost line. Pricing needs a model record with real numbers, and there is
  one cloud model today.
- Context percentage is dark because `context_window` is `None` everywhere.

## History

- 2026-10-24  `Session` was added to the usage line and elapsed time started
  rolling into units. Before that, the line was `In | Out | Elapsed`.
- 2026-10-24  Tokens per second was considered and rejected. The wall-clock
  rate measures the network.
- 2026-10-28  The tool line dropped its arguments by default; `/args` was added
  to bring them back.
- 2026-10-28  The shell block was hidden by default; `/output` was added to
  bring it back.
