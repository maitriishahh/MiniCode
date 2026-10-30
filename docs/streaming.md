# Streaming

**Status:** shipped · **Layer:** 7 · **Files:** `agent.py`, `__main__.py`
**Verified:** 2026-10-30

The model call streams. Reasoning prints as it arrives; the answer prints as it
arrives; tool calls are merged into one assistant message per step. Ctrl+C
during a model call or a tool call ends the turn with history the next request
can still send.

## Event contract

`agent(messages, on_event=None) -> str | None`. `on_event` is called with
`(kind, piece)`; `text` also carries a `final` keyword that the REPL ignores.

| Event | When | `piece` |
|---|---|---|
| `thinking` | the first non-blank reasoning text of a step | `""` |
| `reasoning` | each reasoning delta, including a thought span lifted out of `content` | the text |
| `reasoning_end` | the reasoning block closes, a tool call arrives, or the step ends | `""` |
| `text` | answer text, streamed as it arrives | the text |

`agent` emits no wait line before the call. `thinking` is lazy: no reasoning
means no event and no label. A provider that sends reasoning only inside
`<thought>` or `<think>` gets the same events, emitted as the tags close.

`agent` returns:

| Return | Meaning |
|---|---|
| `""` | the answer was already streamed, including `[empty response]` |
| `None` | the user interrupted |
| `"Model Error: {exc}"` | the call raised; a marker is in history |
| `"Max limit reached: 16. Try smaller request."` | the step ceiling |

The REPL prints the returned string as a plain notice when it is non-empty, and
prints `[interrupted by user]` when it is `None`. It never reprints streamed
text.

### Chunks

`_create(client, **kwargs)` is the only `chat.completions.create` site; the
agent passes `stream=True` and `stream_options={"include_usage": True}`.

Each chunk goes through `chunk.to_dict()`, then:

| Part | Handling |
|---|---|
| `usage` | kept as the step's last usage object; a usage chunk has `choices=[]` and is otherwise ignored |
| `delta.extra_content` | kept on the step and later on the assistant message |
| `delta.reasoning_content` or `delta.reasoning` | emitted as `reasoning`, never stored |
| `delta.content` | fed to the consume buffer, which splits out inline thought tags |
| `delta.tool_calls` | merged into the step's call list |

Usage is added once per step from the last object seen, never summed per chunk:
providers repeat cumulative usage on every chunk. `_apply_usage` overwrites
`In` and adds `Out` and `Session`; an aborted or failed stream adds nothing
(`docs/observability.md`).

Empty content is not displayed, but is still scanned for `extra_content`,
because a Gemini thought signature can ride on an empty part.

### Inline thought tags

`_consume` keeps a small buffer so a tag split across chunks is not printed.
`_tag_suffix` holds back a trailing partial tag (`<tho`), and the next delta
completes it. Text before an opening tag is emitted as answer text; text inside
is emitted as `reasoning`; the closing tag closes the block. `held` is flushed
before a tool call and at the end of the step. The tags themselves never reach
history or `content`.

### Tool-call merge

`_merge_call` merges deltas into one call per step: by `index` when present,
otherwise by `id`, otherwise into the last call when neither arrives. Name and
argument fragments are concatenated. The newest `extra_content` on a call wins.
`index` is dropped. `type` defaults to `function`, `arguments` to `"{}"`, and a
missing id is filled with `uuid.uuid4()`.

`_assistant` then builds the stored message:

```python
{"role": "assistant", "content": text or None, "tool_calls": [...], "extra_content": ...}
```

`content` stays `None` when the step was only tool calls. A step with no text
and no calls stores `[empty response]`, so history never holds a blank
assistant turn.

### Abort and error

| Case | History | Screen | Return |
|---|---|---|---|
| Ctrl+C mid-stream | partial text + `[interrupted by user]`; incomplete calls and reasoning dropped | partial text, then `[interrupted by user]` | `None` |
| exception mid-stream | partial text + `[model error]` | partial text, then `Model Error: ...` | the notice |
| Ctrl+C during a tool | assistant kept; finished results kept; missing ids get `Interrupted by user.` | `[interrupted by user]` | `None` |
| Ctrl+C at `>>> ` | none | exits | — |
| Ctrl+C at the permission prompt | that call is denied | prompt only | turn continues |

`_marked(text, marker)` is `text.rstrip() + "\n\n" + marker`, or the marker
alone when there is no text. Partial text is emitted only if it did not already
stream, so nothing prints twice. Every tool call id in an aborted batch gets a
`role: "tool"` message, because an unanswered id makes the next request 400.

`KeyboardInterrupt` is control flow, not a tool error. `tool_from_fn` catches
`Exception` only, so the interrupt leaves the tool and is handled in `agent`.

## Why this shape

**Iterate the stream, do not use the SDK accumulator.**
`client.chat.completions.stream()` assumes `tool_calls[].index`. Gemini may
omit it, so the accumulator can lose a call. A plain `for chunk in stream` plus
an explicit merge is small enough to own.

**`to_dict()`, not attribute access.** The dict keeps `extra_content`, which
carries the Gemini thought signature. Parsing the SDK object would drop fields
the SDK does not model, and a dropped function-call signature 400s the next
request. The signature is stored and sent back, never read.

**Reasoning is display-only.** It is not `content`, it is not history, and it
does not fill an empty answer. A reasoning-only reply stores `[empty response]`
so the next request stays valid. Displaying it is a reading aid, not state.

**Stream everything, prefix nothing.** The answer has no `minicode >>` prefix
because it is written into a live terminal: a prefix would need a cursor
rewrite to survive, and an ANSI rewrite is worse than no prefix. The status
block after the turn already frames the output.

**The markers exist because of a 400.** Claude Code keeps work that finished
and marks the rest interrupted; OpenCode's empty aborted assistant and an
assistant `tool_calls` with no matching result both 400 the next request. The
two invariants — no empty assistant message, no unanswered call id — come
straight from those failures.

**Ctrl+C is caught in `agent`, not lower.** The tool and the registry must not
decide what an interrupt means. `agent` knows whether an assistant message was
appended and which ids still need a result.

## Invariants

- One create site. `agent._create`.
- Reasoning is never appended to history and never becomes `content`.
  `agent._consume`, `agent._assistant`.
- `extra_content` survives the merge on the message and on each call.
  `agent._consume`, `agent._merge_call`, `agent._assistant`.
- No empty assistant message and no unanswered tool id after an abort or an
  error. `agent.agent`.
- Usage is applied once per completed step, never per chunk.
- Streamed text is not printed a second time from the return value.
- `appended` is set once the assistant dict is in history; the abort path uses
  it to decide between `None` and `""`.

## Edge cases

| Input | Result |
|---|---|
| chunk with `choices=[]` and usage | usage kept, nothing displayed |
| reasoning delta, `/thinking off` | `Thinking:` prints, the body does not |
| no reasoning at all | no label, answer streams |
| tag split across two chunks | held until complete, never printed as text |
| reasoning then a tool call | `reasoning_end` before the tool line |
| reasoning-only reply, content null | block prints, then `[empty response]` |
| mid-stream Ctrl+C after the answer finished | `None`, marker printed by the REPL, no duplicate text |
| tool raises `KeyboardInterrupt` | remaining ids filled, turn ends |
| model raises before any chunk | `[model error]` in history, `Model Error:` printed |

## Verification

- A no-tool reply streams once, then the status block. No `minicode >>`.
- `/thinking on` with a reasoning model: `Thinking:` / `---` / text / `---` /
  blank line, then the answer. No `Thought:` closer.
- `/thinking off`: `Thinking:` only, then the answer.
- A reasoning reply with a tool call closes the block before `|Tool Used:`.
- Ctrl+C mid-stream: partial text, `[interrupted by user]`, status, `>>> `, and
  the next prompt is accepted.
- Ctrl+C during a tool: the same, and the file the tool was writing is not
  half-applied by `edit` or `write`.
- A Gemini tool turn followed by a second turn does not 400 on
  `thought_signature`.
- An empty completion prints `[empty response]` once.
- Ctrl+C while `httpx` is blocked in a Windows `recv` is not exercised here; it
  is a known limitation, not a passing check.

## Gaps

- Ctrl+C does not land while `httpx` is blocked in Winsock `recv`
  (cpython#85609). The SDK default timeout is 600s with two retries, so a dead
  call can sit for a long time. Closing the terminal is the escape. The planned
  shape — worker thread, short `time.sleep` in the main thread, close the
  stream from the handler, `FlushConsoleInputBuffer`, second Ctrl+C calls
  `os._exit` — is recorded in `DESIGN.md` as deferred, not built.
- Pasted multi-line input is submitted line by line. Bracketed paste is not on
  and is unreliable in PyCharm and ConPTY.
- Partial shell output is lost on abort; the timeout path keeps it.
- Ctrl+C kills the direct child only. A grandchild can survive.
- No retry policy beyond the SDK. A model error is a notice and a marker.
- No automated tests. Every check above is manual.

## History

- 2026-10-27  The turn moved from a raw response body to a stream, with
  reasoning events and a final-answer prefix. Gemini thought summaries were
  shown and kept out of the answer.
- 2026-10-27  Inline `<thought>` / `<think>` splitting became incremental rather
  than one pass after the step, so a tag crossing a chunk boundary stopped
  leaking into the answer.
- 2026-10-28  Answers began streaming as they arrive, the thinking block gained
  its `---` fences, and the `minicode >>` prefix was removed.
