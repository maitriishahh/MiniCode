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

File: `src/minicode/agent.py`. Add `import uuid` with the other imports.
Paste these helpers above `agent`. A chunk with no choices is usage only.
Do not index `choices[0]` on it. Ignore empty content for display. A
signature may ride on that empty part. Keep `extra_content`. Do not parse
it. If the step produced no text and no tool calls, `_assistant` stores
`[empty response]` and `agent` emits it through `on_text` once. If the
stream raised or was aborted before a usage chunk, add nothing for that
step.

```python
def _apply_usage(usage: dict | None) -> None:
    if not usage:
        return
    last_usage["prompt_tokens"] = usage.get("prompt_tokens") or 0
    step_out = usage.get("completion_tokens") or 0
    last_usage["completion_tokens"] += step_out
    session_usage["completion_tokens"] += step_out


def _consume(stream, on_text) -> tuple[str, list, object, dict | None]:
    text = ""
    calls: list = []
    by_index: dict = {}
    by_id: dict = {}
    extra = None
    usage = None
    for chunk in stream:
        data = chunk.to_dict()
        if data.get("usage"):
            usage = data["usage"]
        choices = data.get("choices") or []
        if not choices:
            continue
        delta = choices[0].get("delta") or {}
        if delta.get("extra_content") is not None:
            extra = delta["extra_content"]
        piece = delta.get("content")
        if isinstance(piece, str) and piece:
            text += piece
            if on_text:
                on_text(piece)
        for item in delta.get("tool_calls") or []:
            _merge_call(calls, by_index, by_id, item)
    return text, calls, extra, usage
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
print. Remove `~~Thinking...`. `appended` is set after the assistant dict
is in history. A Ctrl+C in the tool loop still returns `None` and fills
missing ids. If a later edit needs "interrupt after the final append,
return `""`", that flag is the check. Do not delete it.

```python
def agent(messages: list, on_text=None) -> str | None:
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
        text = ""
        calls: list = []
        extra = None
        appended = False
        try:
            stream = client.chat.completions.create(
                model=record["id"],
                messages=messages,
                tools=active_schemas(),
                stream=True,
                stream_options={"include_usage": True},
            )
            text, calls, extra, usage = _consume(stream, on_text)
            _apply_usage(usage)
        except KeyboardInterrupt:
            messages.append({
                "role": "assistant",
                "content": _marked(text, "[interrupted by user]"),
                **({"extra_content": extra} if extra is not None else {}),
            })
            return None
        except Exception as exc:
            messages.append({
                "role": "assistant",
                "content": _marked(text, "[model error]"),
                **({"extra_content": extra} if extra is not None else {}),
            })
            return f"Model Error: {exc}"
        msg = _assistant(text, calls, extra)
        if msg["content"] == "[empty response]" and on_text:
            on_text("[empty response]")
        messages.append(msg)
        appended = True
        if not calls:
            return ""
        done: set[str] = set()
        try:
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
                    print(f"\n|Tools Used: `{name}` ({args})|\n")
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

File: `src/minicode/__main__.py`. Replace the `agent(messages)` call and
delete `print(f"\nminicode >> {answer}\n")`. The status block stays. `""`
prints nothing more. The answer already streamed, including
`[empty response]` when that was the whole reply.

```python
started = False

def on_text(piece: str) -> None:
    nonlocal started
    if not piece:
        return
    if not started:
        print(f"\nminicode >> {piece}", end="")
        started = True
    else:
        print(piece, end="")

answer = agent(messages, on_text)
if started:
    print()
if answer is None and not started:
    print("\n[interrupted by user]\n")
elif answer:
    if started:
        print(answer)
    else:
        print(f"\nminicode >> {answer}\n")
```

`In`, `Out`, `Session`, and `_elapsed` do not change. No Tok/s. No context
`%` unless `context_window` is set. `/plan`, `/build`, `/model`, and `exit`
stay before any create. They are not sent to the model.

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
