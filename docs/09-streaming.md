# 09 — Streaming and abort

Do first: `docs/08-permissions.md`. Layer 7 is done. Streaming, abort, the
conditional reasoning blocks, and streamed answers with no `minicode >>` prefix
are implemented. Sessions are in `docs/10-sessions.md`, not this layer.

Registry, loop, `SYSTEM`, and the one `chat.completions.create` site stay in
`agent.py`. The REPL, the status block, and the permission prompt stay in
`__main__.py`. `tool_from_fn` stays in `schema_generator.py`. Sandbox stays
in `resolve_path.py`. Shell stays in `tools/shell.py`. Do not add a module.
Do not grow `__main__.py` with the loop.

The create site is `_create(...)`, which calls
`chat.completions.create(..., stream=True, ...)` for the agent. The assistant
message is rebuilt from `chunk.to_dict()`, not
from a raw response body. A Gemini thought signature rides in that dict. Do
not parse it. Preserve `extra_content`.

## What it is

Reasoning arrives as it is generated. Content is buffered for the whole
model step, because the REPL cannot know whether a step will end with a tool
call until the stream finishes. A no-tool step is the final answer and prints
as the tokens arrive. A tool-call step streams its preamble the same way,
then prints the tool line. Reasoning still streams live inside a `---` block. Ctrl+C during a model call or a tool
call returns to `user >>` with a history the next request can send.

`agent(messages, on_event=None) -> str | None`.

`agent` does not emit a wait line before the create. `_consume` emits
`thinking` on the first non-empty `reasoning_content` or `reasoning` delta,
then `reasoning` for each piece, then `reasoning_end` when that field ends.
A `<thought>` or `<think>` span is split once after the step and shown the
same way.
Content is accumulated, not emitted. Those tags are stripped before the
buffer. After the step, `agent` emits `text(final=True)` for the no-tool
answer (or `[empty response]`) and `text(final=False)` for a tool preamble or
abort/error partial text. The REPL prints `Thinking:` and the reasoning only
when reasoning exists, between `---` lines. There is no `minicode >>` prefix
and no `Thought:` closer. Reasoning is display-only: it never enters history and never
fills `content`.

| Event | History | Screen | Returns |
|---|---|---|---|
| Ctrl+C at `user >>` | none | exit | n/a |
| Ctrl+C at the permission prompt | denial tool result | no exit | continues |
| Ctrl+C mid-stream | partial text plus `[interrupted by user]`; incomplete tool calls and reasoning dropped | partial text without prefix, then `[interrupted by user]` | `None` |
| Ctrl+C during a tool | assistant calls kept; completed results kept; missing ids get `Interrupted by user.` | `[interrupted by user]` | `None` |
| API or model error | partial text plus `[model error]` if no final answer was appended; reasoning not stored | partial text without prefix, then `Model Error: ...` | the notice |
| Empty completion | `[empty response]` | `[empty response]`, once | `""` |
| Reasoning only, content null | `[empty response]`; reasoning not stored | reasoning block, then `[empty response]` | `""` |
| Normal answer | assistant message | streamed as the tokens arrive | `""` |

If Ctrl+C lands after the final assistant entry was appended, return `""`
and print no marker.

Partial text is `text.rstrip() + "\n\n[interrupted by user]"` when it has
non-whitespace. Otherwise the marker alone. Keep `extra_content` if a chunk
already carried it. Do not invent a signature. The partial text is displayed
without reprinting text that already streamed.

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

Reasoning is optional. A delta may carry `reasoning_content` (Qwen/DeepSeek
shape) or `reasoning`. Display either as it arrives. Gemini's OpenAI layer
does not use those names. It may inline a summary as `<thought>...</thought>`
inside `content` when the create asks for it. The Gemini base passes
`extra_body={"extra_body": {"google": {"thinking_config": {"include_thoughts": True, "thinking_level": "low"}}}}`.
No `reasoning_effort`. Ollama does not get that body.
Split `<thought>` or `<think>` out of `content` before those characters are
printed as the answer. Show the inside in the thinking block. Keep the rest
as the answer. Do not read `extra_content` as reasoning; it carries the thought
signature. Do not parse it. If the provider sends no reasoning, `Thinking:`
does not appear; the buffered answer prints normally with its prefix.

The final-only prefix is the reason content is buffered. A first content
delta cannot be labelled final while a later delta may still carry a tool
call. Do not write a provisional prefix and erase it, do not move the cursor
back, and do not add a second create just to learn that the step is final.
Reasoning has no such problem: it is display-only and streams live. The cost
is that the final answer appears when the step ends, not token by token.
Tool-step preambles have the same cost and print once without a prefix.

Ollama's OpenAI-compatible endpoint accepts
`stream_options={"include_usage": True}`. Same create site. No second
client.

Claude Code keeps the work that finished and marks the rest interrupted.
OpenCode's empty aborted assistant and an assistant `tool_calls` with no
matching tool result 400 the next request. That is why the marker exists
and why every id gets a result.

`Thinking:` is the header. It is emitted lazily on the first reasoning
delta, not before the create. When `/thinking` is `on`, the body follows
under a `---` line and closes with `---` on the next line, then a blank
line. Trailing newlines in the summary are not printed. A blank line in
the middle of the summary is. When `/thinking` is `off`, only `Thinking:`
prints. Default is `off`. Do not print a `Thought:`
closer. Do not emit `Thinking:` when there is no reasoning content. A tool's
own print is still the progress during a tool.

A Qwen thinking model can finish with `content` null after the tools
already ran. The REPL then prints `[empty response]`. That is
an empty completion, not a dropped reply. Emit `[empty response]` once.
Reasoning may be displayed, but do not copy `reasoning`, `reasoning_content`,
a `<thought>` / `<think>` span, or a thought signature into `content` or
history.

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
2. Replace: the unconditional wait-line header. Emit `thinking` lazily on the
   first non-empty reasoning delta inside `_consume`, then `reasoning` for
   each delta and `reasoning_end` when the block closes. Do not emit
   `thinking` before
   `chat.completions.create(..., stream=True, stream_options={"include_usage": True})`.
   One site. The REPL renders the header in the event handler; do not print
   it from `agent`.
3. Add: merge helpers in `agent.py`. Build a plain dict. Preserve
   `extra_content`. Drop `index`. Read `reasoning_content` or `reasoning`
   for display only. Split `<thought>` and `<think>` out of `content`. Never
   append either to history.
4. Add: `on_event` in the REPL. It renders `thinking`, `reasoning`,
   `reasoning_end`, and `text`. Answer tokens stream as they arrive. A
   thinking block is `Thinking:` / `---` / text / `---` when display is on.
   `/thinking` defaults to `off`. `/effort` defaults to `low`. There is no `minicode >>`
   prefix. Do not print streamed text again from the returned value.
5. Add: abort handling in `agent`. `KeyboardInterrupt` is control flow, not
   a tool error. `tool_from_fn` catches `Exception` only, so Ctrl+C still
   leaves `run()`. Catch it in `agent`, not in `shell.py` and not in
   `tool_from_fn`. Keep partial text in mutable step state so the abort/error
   path can append it and display it without a prefix.
6. Do not change `shell.py`. Timeout stays 120 seconds. No background
   process. No process tree. A GUI that does not exit still blocks until
   the timeout or until Ctrl+C. After this layer, that Ctrl+C aborts the
   step and returns to `user >>`. It does not end the REPL.

## Segment 1 — stream and usage

File: `src/minicode/agent.py`. Add `import uuid` with the other imports.
Paste these helpers above `agent`. A chunk with no choices is usage only.
Do not index `choices[0]` on it. Ignore empty content for display. A
signature may ride on that empty part. Keep `extra_content`. Do not parse
it. Read `reasoning_content` or `reasoning` as they arrive. After the
step, `_split_thought` pulls one `<thought>` or `<think>` span out of the
buffered content. Emit `thinking` only when reasoning text exists. If the
step produced no text and no tool
calls, `_assistant` stores `[empty response]` and `agent` emits it as a
final text event once. If the stream raised or was aborted before a usage
chunk, add nothing for that step.

The step state is mutable on purpose. When the stream raises, `_consume`
does not return, so a local `text`, `calls`, or `extra` would be lost before
`agent` can append the partial marker or close the reasoning block.

```python
def _gemini_extra(base: str) -> dict | None:
    if "generativelanguage.googleapis.com" not in base:
        return None
    return {
        "extra_body": {
            "google": {
                "thinking_config": {
                    "include_thoughts": True,
                }
            }
        }
    }

def _split_thought(text: str) -> tuple[str, str]:
    lower = text.lower()
    for open_tag, close_tag in (("<thought>", "</thought>"), ("<think>", "</think>")):
        start = lower.find(open_tag)
        end = lower.find(close_tag)
        if start != -1 and end > start:
            inside = text[start + len(open_tag):end]
            rest = text[:start] + text[end + len(close_tag):]
            return inside, rest
    return "", text

def _apply_usage(usage: dict | None) -> None:
    if not usage:
        return
    last_usage["prompt_tokens"] = usage.get("prompt_tokens") or 0
    step_out = usage.get("completion_tokens") or 0
    last_usage["completion_tokens"] += step_out
    session_usage["completion_tokens"] += step_out


def _consume(stream, on_event, state: dict) -> None:
    state["text"] = ""
    state["calls"] = []
    state["extra"] = None
    state["usage"] = None
    by_index: dict = {}
    by_id: dict = {}
    reasoning = False

    def emit(kind: str, piece: str = "") -> None:
        if on_event:
            on_event(kind, piece)

    for chunk in stream:
        data = chunk.to_dict()
        if data.get("usage"):
            state["usage"] = data["usage"]
        choices = data.get("choices") or []
        if not choices:
            continue
        delta = choices[0].get("delta") or {}
        if delta.get("extra_content") is not None:
            state["extra"] = delta["extra_content"]
        think = delta.get("reasoning_content") or delta.get("reasoning")
        if isinstance(think, str) and think:
            if not reasoning:
                emit("thinking")
                reasoning = True
            emit("reasoning", think)
        piece = delta.get("content")
        if isinstance(piece, str) and piece:
            state["text"] += piece
        for item in delta.get("tool_calls") or []:
            _merge_call(state["calls"], by_index, by_id, item)
    if reasoning:
        emit("reasoning_end")
    thought, answer = _split_thought(state["text"])
    if thought.strip():
        emit("thinking")
        emit("reasoning", thought.strip())
        emit("reasoning_end")
    if answer != state["text"]:
        state["text"] = answer.strip()
```

## Segment 2 — tool-call merge

Same file. One assistant dict per model step, not one per chunk. Merge by
`index` when it is present, otherwise by `id`, otherwise append. Concatenate
name and argument fragments. The latest `extra_content` on that call wins.
Drop `index`. Default `type` to `"function"` and `arguments` to `"{}"`.
Synthesize an id with `uuid.uuid4()` only when the provider omitted it.
Never use a fixed `call_0`.

```python
def _merge_call(calls: list, by_index: dict, by_id: dict, delta: dict) -> None:
    fn = delta.get("function") or {}
    index = delta.get("index")
    call_id = delta.get("id")
    name = fn.get("name") or ""
    arguments = fn.get("arguments") or ""
    target = None
    if index is not None and index in by_index:
        target = by_index[index]
    elif isinstance(call_id, str) and call_id in by_id:
        target = by_id[call_id]
    elif calls and not call_id and not name:
        target = calls[-1]
    if target is None:
        fresh = call_id if isinstance(call_id, str) and call_id else str(uuid.uuid4())
        target = {
            "id": fresh,
            "type": delta.get("type") or "function",
            "function": {"name": "", "arguments": ""},
        }
        calls.append(target)
        by_id[fresh] = target
    if index is not None:
        by_index[index] = target
    if isinstance(call_id, str) and call_id:
        by_id[call_id] = target
        target["id"] = call_id
    if name:
        target["function"]["name"] += name
    if arguments:
        target["function"]["arguments"] += arguments
    if delta.get("extra_content") is not None:
        target["extra_content"] = delta["extra_content"]


def _assistant(text: str, calls: list, extra) -> dict:
    msg: dict = {"role": "assistant", "content": text or None}
    if calls:
        stored = []
        for call in calls:
            item = {
                "id": call["id"],
                "type": call.get("type") or "function",
                "function": {
                    "name": call["function"]["name"],
                    "arguments": call["function"]["arguments"] or "{}",
                },
            }
            if "extra_content" in call:
                item["extra_content"] = call["extra_content"]
            stored.append(item)
        msg["tool_calls"] = stored
    if extra is not None:
        msg["extra_content"] = extra
    if not text and not calls:
        msg["content"] = "[empty response]"
    return msg


def _marked(text: str, marker: str) -> str:
    body = text.rstrip()
    return f"{body}\n\n{marker}" if body else marker
```

## Segment 3 — abort

Same file. Replace `agent`. Keep `_permit`, the plan denial string, the
short shell denial, and `_tool_note`. Append the tool result before either
print. Do not emit `thinking` before the create; `_consume` owns that event
now. Emit `reasoning_end` on abort and model error so an open block closes.
Partial text lives in step state so the abort/error path can append it and
display it without a prefix.

After a step, append the assistant dict before printing model text. A step
with no calls is final: emit `text(final=True)` with `msg["content"]` and
return `""`. A step with calls emits its text as `text(final=False)` before
the tool lines. Put that preamble print inside the tool try. A Ctrl+C while
it prints must still fill every tool id with `Interrupted by user.`
`appended` is set after the assistant dict is in history. A Ctrl+C in the
tool loop still returns `None` and fills missing ids. If a later edit needs
"interrupt after the final append, return `""`", that flag is the check.
Do not delete it.

```python
def agent(messages: list, on_event=None) -> str | None:
    last_usage["prompt_tokens"] = 0
    last_usage["completion_tokens"] = 0
    record = MODELS[active["id"]]
    api_key = os.getenv(record["api_key"])
    base = record["api_base"]
    if not api_key and base.startswith(("http://127.0.0.1", "http://localhost")):
        api_key = "ollama"
    try:
        client = OpenAI(api_key=api_key, base_url=base)
    except Exception as exc:
        return f"Model Error: {exc}"
    for step in range(MAX_STEPS):
        state = {"text": "", "calls": [], "extra": None, "usage": None}
        appended = False
        try:
            create = {
                "model": record["id"],
                "messages": messages,
                "tools": active_schemas(),
                "stream": True,
                "stream_options": {"include_usage": True},
            }
            extra = _gemini_extra(base)
            if extra:
                create["extra_body"] = extra
            stream = client.chat.completions.create(**create)
            _consume(stream, on_event, state)
            _apply_usage(state["usage"])
        except KeyboardInterrupt:
            if on_event:
                on_event("reasoning_end")
            messages.append({
                "role": "assistant",
                "content": _marked(state["text"], "[interrupted by user]"),
                **({"extra_content": state["extra"]} if state["extra"] is not None else {}),
            })
            if state["text"] and on_event:
                on_event("text", state["text"])
            return None
        except Exception as exc:
            if on_event:
                on_event("reasoning_end")
            messages.append({
                "role": "assistant",
                "content": _marked(state["text"], "[model error]"),
                **({"extra_content": state["extra"]} if state["extra"] is not None else {}),
            })
            if state["text"] and on_event:
                on_event("text", state["text"])
            return f"Model Error: {exc}"
        msg = _assistant(state["text"], state["calls"], state["extra"])
        messages.append(msg)
        appended = True
        if not state["calls"]:
            if on_event:
                on_event("text", msg["content"], final=True)
            return ""
        done: set[str] = set()
        try:
            if state["text"] and on_event:
                on_event("text", state["text"])
            for call in msg["tool_calls"]:
                name = call["function"]["name"]
                args = call["function"]["arguments"]
                if mode["name"] == "plan" and name in PLAN_DENIED:
                    content = f"Plan mode: `{name}` is disabled. Propose the change and ask to run /build."
                    note = True
                    ran = False
                else:
                    run = TOOLS.get(name)
                    if run:
                        denied = _permit(name, args)
                        try:
                            if denied is not None:
                                content = denied
                                note = True
                                ran = False
                            else:
                                content = run(args)
                                note = False
                                ran = True
                        finally:
                            clear_approved()
                    else:
                        content = f"Unknown tool: {name}"
                        note = True
                        ran = False
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": content})
                done.add(call["id"])
                if note:
                    _tool_note(content)
                elif ran:
                    print(f"\n{_tool_line(name, args)}\n")
        except KeyboardInterrupt:
            for call in msg["tool_calls"]:
                if call["id"] not in done:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": "Interrupted by user.",
                    })
            return None
        _ = appended
    return f"Max limit reached: {MAX_STEPS}. Try smaller request."
```

`max_steps` still returns that notice. It does not raise. Ctrl+C at
`user >>` still exits. Do not change that handler. Ctrl+C on the permission
prompt still denies that call. Do not change `_permission`. `shell.py`
stays. `subprocess.run` kills the direct child on timeout. On Ctrl+C it
raises `KeyboardInterrupt`, which `run()` does not catch. `agent` catches
that, fills missing ids, and returns `None`. Grandchildren can survive. Do
not kill a process tree in this layer. A `python calculator.py` that opens
a window still blocks until the window closes, the 120-second timeout, or
Ctrl+C. Do not add a background flag. The escape is Ctrl+C, and it must
return to `user >>`.

## Segment 4 — REPL

File: `src/minicode/__main__.py`. Replace the `agent(messages)` call. The
status block stays. `""` prints nothing more. `agent` already streamed the
answer, including `[empty response]` when that was the whole reply and
nothing was streamed. Print the interrupt marker when `answer is None`, even
after partial text. A non-empty `answer` is a `Model Error:` or max-limit
notice, not the answer: print it as a plain notice. Do not reprint streamed
text.

```python
reasoning = False
wrote = False
held_nl = ""

def on_event(kind: str, piece: str = "", final: bool = False) -> None:
    nonlocal reasoning, wrote, held_nl
    show = thinking["name"] == "on"
    if kind == "thinking":
        held_nl = ""
        if show:
            print("\nThinking:\n---", flush=True)
        else:
            print("\nThinking:", flush=True)
        reasoning = True
        wrote = True
    elif kind == "reasoning":
        if show:
            text = held_nl + piece
            held_nl = ""
            end = len(text)
            while end and text[end - 1] == "\n":
                end -= 1
            if end < len(text):
                held_nl = text[end:]
                text = text[:end]
            if text:
                print(text, end="", flush=True)
        reasoning = True
        wrote = True
    elif kind == "reasoning_end":
        if reasoning and show:
            held_nl = ""
            print("\n---\n", flush=True)
        held_nl = ""
        reasoning = False
    elif kind == "text":
        print(piece, end="", flush=True)
        wrote = True

answer = agent(messages, on_event)
if wrote:
    print()
if answer is None:
    print("\n[interrupted by user]\n")
elif answer:
    print(f"\n{answer}\n")
```

`In`, `Out`, `Session`, and `_elapsed` do not change. No Tok/s. No context
`%` unless `context_window` is set. Slash commands and `exit` stay before
any create. They are not sent to the model. `/help` prints the `COMMANDS`
tuple. A new slash command adds a handler and a `COMMANDS` row in the same
pass.

## Soak

From the launch dir, with the dev fence:

```powershell
uv run python -m minicode --sandbox sandbox
```

- A no-reasoning text reply shows no thinking block. The answer streams,
  then the status block. The answer is not printed twice.
- `/thinking on`: a reasoning reply prints `Thinking:`, `---`, the reasoning,
  `---` on the next line after the last reasoning line, a blank line, then
  streams the answer. Trailing newlines in the summary are not printed. A
  blank line in the middle of the summary is. `/thinking off` prints only
  `Thinking:`. No `Thought:` line. No `minicode >>` prefix.
- A reasoning reply with a tool call closes the block before the tool
  preamble or `|Tool Used|`; the next model step starts a new block.
- A reasoning-only reply with null content prints the reasoning block, then
  `[empty response]`, and keeps reasoning out of history.
- A tool turn streams its preamble, then the tool line after the result is
  in history. Plan still denies `write` / `edit` with the existing sentence
  and no `|Tool Used|` line.
- A multi-step turn streams each step's text. Already streamed text is not
  reprinted.
- A Gemini tool turn, then a second turn, does not 400 on
  `thought_signature`. If it does, the merge dropped `extra_content`. Do
  not parse the signature and do not invent one.
- Ctrl+C mid-stream prints any partial text without a prefix, then
  `[interrupted by user]`, the status block, and returns to `user >>`. The
  next message is accepted.
- Ctrl+C during reasoning stops the block, prints
  `[interrupted by user]`, prints the status block, and returns to
  `user >>`.
- Ctrl+C while a tool preamble prints still fills every tool id with
  `Interrupted by user.` and returns to `user >>`.
- Ctrl+C during `python -c "import time; time.sleep(30)"` does the same.
  The sleep does not have to finish.
- Ctrl+C on the permission prompt denies that call and does not exit.
- Ctrl+C at `user >>` exits.
- `/plan` still proposes and says `/build`. `/build` still writes. A
  denied plan-mode shell ask still returns the short `/build` sentence.
- An empty completion prints `[empty response]` once, then the
  status block.
- A `Model Error:` or max-limit notice prints as a plain notice.
- `python calculator.py` may open a window and block. Ctrl+C returns to
  `user >>`. Do not add a background shell to make the window survive.

Ollama, if it is up, uses the same create site. Do not add a second client
for it.

## Open gaps at this layer

- Ctrl+C kills the direct shell child only. A grandchild can survive.
- Partial shell output is lost on abort. The timeout path still returns
  whatever bytes arrived. Abort does not.
- An aborted stream adds no usage. The status block still prints.
- Sessions and resume live in `docs/10-sessions.md`.
- No atomic write. A `write` that is interrupted inside the tool is the
  tool's problem. This layer only keeps the history coherent.
- No retry. A model error is a notice and a marker, not another create.
- Answer tokens stream as they arrive. There is no `minicode >>` prefix.
  A tool preamble streams the same way, then the tool line.
- A provider that sends no reasoning shows no thinking block and no wait
  line. The first visible output is the answer as it streams.
- Gemini asks for a low summary (`include_thoughts`, `thinking_level: low`).
  No `reasoning_effort`. Ollama does not get that body.
- No tests.
- `input()` is cooked console input. A click or middle-click paste
  (PyCharm middle-click, Windows Terminal right-click, mintty middle-click)
  injects newlines, and each non-empty line is a user message and a model
  call. Bracketed paste is not on. On Windows it is not reliable anyway: it
  needs `ENABLE_VIRTUAL_TERMINAL_INPUT`, and PyCharm classic and ConPTY
  often drop `ESC[200~`.
- Ctrl+C during a stream that is back in Python between chunks returns to
  `user >>`. Ctrl+C while httpx is blocked in Winsock `recv` does not.
  CPython does not raise `KeyboardInterrupt` until that read returns
  (cpython#85609). `time.sleep` and a console read do check. Ctrl+Break is
  the same once Python has a handler. The client uses the SDK default
  timeout of 600s and two retries, so a dead call can sit for about half an
  hour. Closing the terminal tab is the escape today. A short read timeout
  is not the fix: it also kills a slow thinking gap, and the SDK retries it.

## Don't add yet

Sessions/resume are implemented in `docs/10-sessions.md`. Later, in order:
transcript export, cache control, diff viewer, `AGENTS.md` injection. Cost
display waits until more models
are added. Compaction waits until the context gap hurts. Windows paste and
a stuck model read wait too. That one is an amendment to this guide, not a
new file and not next.

When that amendment is written, the shape is fixed. After `input()` returns,
if the console already has more lines waiting (`PeekConsoleInput` /
`msvcrt.kbhit`), read them and do not send. On interrupt,
`FlushConsoleInputBuffer` before the next `input()`. Do not rely on
bracketed paste in PyCharm. Run the stream on a worker thread. The main
thread waits in short `time.sleep` calls, which Ctrl+C breaks on Windows.
On interrupt, close the httpx stream from the main thread so the worker's
`recv` fails, then keep the history cleanup this guide already specifies. A
second Ctrl+C in the console handler calls `os._exit` if the close did not
unblock. That handler runs on another thread. No `prompt_toolkit`, no Rich,
no Textual, no asyncio, no client/server split, and no short read timeout
used as cancel. OpenCode aborts with Escape via `session.interrupt` because
the TUI is not the thread blocked in the provider socket. Pi aborts with
Escape via `ctx.abort()`, then an outside kill. Claude Code aborts the fetch
with an `AbortController`. Those are the comparison. They are not the
implementation.

Not this layer: async, a background shell, a process tree, a persistent
shell, Rich, a test suite, using `reasoning_content` or a `<thought>` /
`<think>` span as assistant content or history, `reasoning_effort`,
a Tok/s line, summing `prompt_tokens` into `Session`, a second create site,
an SSE parser, `client.chat.completions.stream()`, an ANSI cursor rewrite to
put a prefix on already-streamed text, a second create just to learn that a
step is final.

## Checkpoint

1. Why is `client.chat.completions.stream()` forbidden?
2. Where does a Gemini thought signature live after this layer, and what
   code parses it?
3. A stream chunk has `choices=[]`. What is it, and what must the loop not
   do with it?
4. Ctrl+C mid-stream: what is appended, and what is dropped?
5. Ctrl+C during the second of three tool calls: which results are kept,
   and what fills the gap?
6. Why does `[empty response]` exist, and why is a reasoning field never
   copied into `content` or history even when it is displayed?
7. Why do answer tokens stream, and why is there no `minicode >>` prefix?
8. Why does a `Model Error:` notice stay a plain notice?
9. Why does a Tk window still block, and what is the escape?
