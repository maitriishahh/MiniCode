# 09 — Streaming and abort

Do first: `docs/08-permissions.md`. Layer 7 is done. This guide is not
implemented. Implement this file next. Do not start sessions in that pass.

Registry, loop, `SYSTEM`, and the one `chat.completions.create` site stay in
`agent.py`. The REPL, the status block, and the permission prompt stay in
`__main__.py`. `tool_from_fn` stays in `schema_generator.py`. Sandbox stays
in `resolve_path.py`. Shell stays in `tools/shell.py`. Do not add a module.
Do not grow `__main__.py` with the loop.

Today the create site is `client.with_raw_response.chat.completions.create`.
The assistant message appended is `choices[0].message` from that JSON. A
Gemini thought signature rides in that dict. Do not parse it. Streaming has
no raw message, so the implement pass rebuilds that dict from chunks. That
is the only change to the raw-append rule.

## What it is

Text arrives as it is generated. Ctrl+C during a model call or a tool call
returns to `user >>` with a history the next request can send. Today that
Ctrl+C ends the REPL.

`agent(messages, on_text=None) -> str | None`.

| Event | History | Screen | Returns |
|---|---|---|---|
| Ctrl+C at `user >>` | none | exit | n/a |
| Ctrl+C at the permission prompt | denial tool result | no exit | continues |
| Ctrl+C mid-stream | partial text plus `[interrupted by user]`; incomplete tool calls dropped | `[interrupted by user]` | `None` |
| Ctrl+C during a tool | assistant calls kept; completed results kept; missing ids get `Interrupted by user.` | `[interrupted by user]` | `None` |
| API or model error | partial text plus `[model error]` if no final answer was appended | `Model Error: ...` | the notice |
| Empty completion | `[empty response]` | that marker, once | `""` |
| Normal answer | assistant message | already streamed | `""` |

If Ctrl+C lands after the final assistant entry was appended, return `""`
and print no marker.

Partial text is `text.rstrip() + "\n\n[interrupted by user]"` when it has
non-whitespace. Otherwise the marker alone. Keep `extra_content` if a chunk
already carried it. Do not invent a signature.

Invariants: no empty assistant message, no partial tool call in history, no
assistant `tool_calls` without one result per id, no consecutive user
messages caused by an abort or an error.

## Why this shape

OpenAI's stream is a sequence of `ChatCompletionChunk`s. `stream=True` on
the existing create returns a `Stream`. Iterate it. Do not call
`client.chat.completions.stream()`. That accumulator assumes
`tool_calls[].index`. Gemini may omit the index. Do not write an SSE
parser. Do not add async.

`chunk.to_dict()` keeps `extra_content` on the delta and on each tool call.
A Gemini thought signature rides there. Send it back. Do not parse it. A
text-only signature is optional: dropping one may worsen the next reply and
does not 400. A function-call signature in the current turn is not optional.
A 400 that names `thought_signature` means a completed call lost its
signature. Inspect the merge. Do not substitute a dummy.

Gemini may send a whole tool call in one chunk, may put a text-only
signature on an empty content part, and repeats cumulative usage on every
chunk. Read to the end. Ignore empty content for display. Keep the last
usage object in a step. Add `completion_tokens` once. Do not sum chunk
usage. A usage chunk has `choices=[]`. Read usage before indexing choices.

Ollama's OpenAI-compatible endpoint accepts
`stream_options={"include_usage": True}`. Same create site. No second
client.

Claude Code keeps the work that finished and marks the rest interrupted.
OpenCode's empty aborted assistant and an assistant `tool_calls` with no
matching tool result 400 the next request. That is why the marker exists
and why every id gets a result.

`~~Thinking...` is a wait line printed before the create returns. It is not
model reasoning. A blocked `python calculator.py` looks like the model is
thinking. Remove it. The first text delta is the progress. A tool's own
print is the progress during a tool. Do not put a wait line back.

A Qwen thinking model can finish with `content` null after the tools
already ran. The REPL then prints `minicode >>` and nothing else. That is
an empty completion, not a dropped reply. Emit `[empty response]` once. Do
not read `reasoning`, `reasoning_content`, or a thought signature to fill
it.

`In` still overwrites with the last call's `prompt_tokens`. `Out` and
`Session` still add only `completion_tokens`. An aborted or failed stream
adds nothing. A completed model step before a tool abort still counts. Do
not add `prompt_tokens` into `Session`. A resent prompt is not new work.
Cost display stays deferred until more models are added.

## Skeleton

**Keep the loop. Stream the one create. Catch Ctrl+C in `agent`.**

1. Keep: tools, `SYSTEM`, `PLAN_SYSTEM`, modes, permissions, the tool line,
   the status block, `In | Out | Session | Elapsed`. No Tok/s. Plan still
   drops `write` / `edit` and still returns the short `/build` sentence on
   a denied shell ask. `*` still matches a newline. Do not rewrite those.
2. Replace: the `with_raw_response` create becomes
   `chat.completions.create(..., stream=True, stream_options={"include_usage": True})`.
   One site. Remove `print("~~Thinking...")`.
3. Add: merge helpers in `agent.py`. Build a plain dict. Preserve
   `extra_content`. Drop `index`.
4. Add: `on_text` in the REPL. Print `minicode >>` once, on the first
   non-empty delta. Do not print the answer again at the end.
5. Add: abort handling in `agent`. `KeyboardInterrupt` is control flow, not
   a tool error. `tool_from_fn` catches `Exception` only, so Ctrl+C still
   leaves `run()`. Catch it in `agent`, not in `shell.py` and not in
   `tool_from_fn`.
6. Do not change `shell.py`. Timeout stays 120 seconds. No background
   process. No process tree. A GUI that does not exit still blocks until
   the timeout or until Ctrl+C. After this layer, that Ctrl+C aborts the
   step and returns to `user >>`. It does not end the REPL.

## Segment 1 — stream and usage

File: `src/minicode/agent.py`.

```python
stream = client.chat.completions.create(
    model=record["id"],
    messages=messages,
    tools=active_schemas(),
    stream=True,
    stream_options={"include_usage": True},
)
```

Iterate `stream`. Call `chunk.to_dict()`. A chunk with no choices is usage
only. Remember that usage object. Do not index `choices[0]` on it.

For a content string that is non-empty, append it and call `on_text` with
that piece. Ignore empty content. A signature may ride on that empty part.
Keep the chunk's `extra_content` if present. Do not display it.

After the stream ends, if this step produced no text and no tool calls,
the content is `[empty response]`. Emit that string through `on_text` once.

Apply the remembered usage the way the loop already does: overwrite
`prompt_tokens`, add `completion_tokens` once to the turn and to the
session. If the stream raised or was aborted before a usage chunk, add
nothing for that step.

## Segment 2 — tool-call merge

Same file. One assistant dict per model step, not one per chunk.

- Merge a tool-call delta by `index` when the index is present.
- Otherwise merge by `id` when the id was already seen.
- Otherwise append. A new `id` or a new `function.name` with no open call
  starts a call.
- Append `function.name` fragments and `function.arguments` fragments.
  Do not replace an arguments string with a later fragment. Concatenate.
- Copy `extra_content` from the tool-call delta onto that call when present.
  Do not merge two signatures. The latest one on that call wins. Do not
  parse it.
- Drop `index` from the stored call. Default `type` to `"function"`.
  Default `arguments` to `"{}"`. If the provider omitted `id`, synthesize
  one with `uuid.uuid4()`. Never use a fixed `call_0`.
- Final `content` is the accumulated string, or `None` when there was no
  text. Store a plain dict: `role`, `content`, `tool_calls` if any,
  `extra_content` if any. Nothing else.

Append that dict once, when the stream finishes cleanly and the step has
text or tool calls. Set a flag so a Ctrl+C after that append does not add
a second marker.

## Segment 3 — abort

Same file. Wrap the stream. Wrap the tool loop.

Ctrl+C mid-stream, before the assistant dict is appended: if the buffer has
non-whitespace, append `text.rstrip() + "\n\n[interrupted by user]"`.
Otherwise append the marker alone. Keep message-level `extra_content` if one
arrived. Drop incomplete tool calls. They are not in history. Return `None`.

Ctrl+C during tools: the assistant dict is already appended. Keep every
tool result already appended. For each `tool_call_id` that has no result,
append `Interrupted by user.` in call order. Do not append another assistant
message. Return `None`.

Append a finished tool result before `_tool_note` and before
`|Tools Used: \`name\` ({args})|`. A `write` of a long file prints the whole
argument. Ctrl+C during that print must not drop a result that already
succeeded. The plan denial, the permission denial, and the unknown-tool
string still print, and they still do not print `|Tools Used|`. The print
moves to after the append. The strings do not change.

API or model error before a final assistant append: if the buffer has
non-whitespace, append it plus `\n\n[model error]`. Otherwise append
`[model error]`. Return `Model Error: {exc}`. Do not leave the history
ending on the user message. Gemini can reject the next turn when two user
messages are adjacent.

`max_steps` still returns `Max limit reached: {MAX_STEPS}. Try smaller request.`
It does not raise.

Ctrl+C at `user >>` still exits. That handler is already in `__main__.py`.
Do not change it. Ctrl+C on the permission prompt still denies that call
and the loop continues. Do not change `_permission`.

`shell.py` stays. `subprocess.run` kills the direct child on timeout. On
Ctrl+C it raises `KeyboardInterrupt`, which `run()` does not catch. `agent`
catches that, fills missing ids, and returns `None`. The child that was the
direct process is dead. Grandchildren can survive. That remains a gap. Do
not kill a process tree in this layer.

A `python calculator.py` that opens a window still blocks until the window
closes, the 120-second timeout, or Ctrl+C. Do not add a background flag
because a GUI does not exit. The escape is Ctrl+C, and it must return to
`user >>`.

## Segment 4 — REPL

File: `src/minicode/__main__.py`.

```python
def on_text(piece: str) -> None:
    ...
answer = agent(messages, on_text)
```

On the first non-empty piece, print a newline, `minicode >> `, and the
piece, with no extra newline. Later pieces print as they are. After the
call returns, finish the streamed line with one newline if any piece was
printed.

- `None`: if the marker was not already streamed, print `[interrupted by user]`.
- A non-empty return: print it. That is `Model Error: ...` or the max-step
  notice. Do not prefix it with a second `minicode >>` if `on_text` already
  started the line. Finish the line, then print the notice.
- `""`: print nothing more. The answer already streamed, including
  `[empty response]` when that was the whole reply.

Remove `print(f"\nminicode >> {answer}\n")`. The status block still prints
after a normal completion, an abort, an error, and an empty completion.
`In`, `Out`, `Session`, and `_elapsed` do not change. No Tok/s. No context
`%` unless `context_window` is set.

`/plan`, `/build`, `/model`, and `exit` stay before any create. They are
not sent to the model.

## Soak

From the launch dir, with the dev fence:

```powershell
uv run python -m minicode --sandbox sandbox
```

- A text reply streams after `minicode >>`. The status block follows. The
  answer is not printed twice. No `~~Thinking...`.
- A tool turn prints the tool line after the result is in history. Plan
  still denies `write` / `edit` with the existing sentence and no
  `|Tools Used|` line.
- A multi-step turn streams each text piece and does not reprint the final
  answer.
- A Gemini tool turn, then a second turn, does not 400 on
  `thought_signature`. If it does, the merge dropped `extra_content`. Do
  not parse the signature and do not invent one.
- Ctrl+C mid-stream prints `[interrupted by user]`, prints the status
  block, and returns to `user >>`. The next message is accepted.
- Ctrl+C during `python -c "import time; time.sleep(30)"` does the same.
  The sleep does not have to finish.
- Ctrl+C on the permission prompt denies that call and does not exit.
- Ctrl+C at `user >>` exits.
- `/plan` still proposes and says `/build`. `/build` still writes. A
  denied plan-mode shell ask still returns the short `/build` sentence.
- An empty completion prints `[empty response]` once, then the status
  block.
- `python calculator.py` may open a window and block. Ctrl+C returns to
  `user >>`. Do not add a background shell to make the window survive.

Ollama, if it is up, uses the same create site. Do not add a second client
for it.

## Open gaps at this layer

- Ctrl+C kills the direct shell child only. A grandchild can survive.
- Partial shell output is lost on abort. The timeout path still returns
  whatever bytes arrived. Abort does not.
- An aborted stream adds no usage. The status block still prints.
- No sessions or resume. The coherent history lives in this process only.
- No atomic write. A `write` that is interrupted inside the tool is the
  tool's problem. This layer only keeps the history coherent.
- No retry. A model error is a notice and a marker, not another create.
- No tests.

## Don't add yet

Later, in order, not in the implement pass: sessions/resume, cache control,
diff viewer, `AGENTS.md` injection. Cost display waits until more models
are added. Compaction waits until the context gap hurts.

Not this layer: async, a background shell, a process tree, a persistent
shell, Rich, a test suite, reading `reasoning_content`, a Tok/s line,
summing `prompt_tokens` into `Session`, a second create site, an SSE
parser, `client.chat.completions.stream()`.

## Checkpoint

1. Why is `client.chat.completions.stream()` forbidden?
2. Where does a Gemini thought signature live after this layer, and what
   code parses it?
3. A stream chunk has `choices=[]`. What is it, and what must the loop not
   do with it?
4. Ctrl+C mid-stream: what is appended, and what is dropped?
5. Ctrl+C during the second of three tool calls: which results are kept,
   and what fills the gap?
6. Why does `[empty response]` exist, and why is a reasoning field not
   copied into `content`?
7. What does `agent` return for a normal streamed answer, and why does the
   REPL not print `minicode >> {answer}`?
8. Why does a Tk window still block, and what is the escape?
