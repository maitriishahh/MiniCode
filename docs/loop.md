# Loop

**Status:** shipped · **Layer:** 0 · **Files:** `agent.py`, `__main__.py`
**Verified:** 2026-10-30

One request, one tool batch, repeat until the model stops asking for tools.
This doc owns the message flow and the stop conditions. `docs/architecture.md`
owns where the code lives.

## Contract

```text
REPL        append {"role": "user"} once
agent       for step in range(16):
              stream one create
              append the assistant message once
              if no tool_calls: return
              for each call:
                check plan deny, then permission
                run the tool
                append one {"role": "tool"} per call, same tool_call_id
            after 16 steps: return "Max limit reached: 16. Try smaller request."
```

`MAX_STEPS` is 16 and is not a parameter. Sixteen model calls per turn is the
ceiling; a turn that needs more gets the limit message.

### What `agent` returns

| Return | Meaning |
|---|---|
| `""` | the model answered without tool calls; the text was already streamed |
| `None` | the user interrupted the turn |
| `"Model Error: {exc}"` | the client could not be built, or the call raised |
| `"Max limit reached: 16. Try smaller request."` | the step ceiling |

The REPL prints a non-empty return as the answer. An empty return prints
nothing, because the text already went to stdout as it streamed.

### What the model sees when a call fails

Tool failures are strings in a `role: "tool"` message, never exceptions.

| Case | Content |
|---|---|
| arguments fail validation | `Invalid Arguments: {pydantic message}` |
| the tool raised | `Tool error: {exc}` |
| the tool name is not registered | `Unknown tool: {name}` |
| plan mode refused the tool | ``Plan mode: `{name}` is disabled. Propose the change and ask to run /build.`` |
| permissions refused the call | `Permission denied: {key} {value}` |
| a plan-mode shell call was denied | the short `/build` sentence |
| Ctrl+C during the batch | `Interrupted by user.` for every call not yet run |

### Message flow

The REPL appends the user message once, on the first line of a new turn, and
never again. `agent` appends exactly one assistant message per reply.

The assistant message is a plain dict assembled from the streamed
`chunk.to_dict()` deltas. It is never an SDK object, so fields the SDK does not
model survive the round trip. `extra_content` is kept both on the message and
on each tool call; a Gemini thought signature rides there and is not parsed or
invented.

Each tool call becomes:

```python
{"id": ..., "type": "function", "function": {"name": ..., "arguments": ...}}
```

Empty arguments are stored as `{}` so the next request stays valid.

With no text and no tool calls, content becomes `[empty response]` so history
is never a blank assistant turn.

## Why this shape

Prompt, model, tool calls, results, repeat. One node with a self-loop, not a
graph. Pi, Claude Code, Codex, and OpenCode all run this shape; see
`DESIGN.md` D1 for the comparison.

Two alternatives were rejected for concrete reasons:

- **LangGraph** is for real branching, a supervisor routing between distinct
  nodes. On a `while` loop it is abstraction tax with no payoff.
- **LlamaIndex `FunctionAgent`** hides `tool_calls`, the `role: "tool"` message,
  the loop, and the stop condition. Steering, abort, and compaction cannot be
  added through it.

`deepagents` is a capability checklist for later, never a dependency, until the
hand-built loop is fully owned.

## Invariants

- The user message is appended once, by the REPL. `__main__.main`.
- One assistant message per reply, appended before any tool runs.
  `agent.agent`.
- One `role: "tool"` per call, with that call's id. Never batched.
  `agent.agent`.
- Tool code never raises out of the loop. `schema_generator.tool_from_fn` →
  `run`.
- The step limit returns a string. It never raises.
- `last_usage` resets at the start of the turn, not at the start of the process.
- `exit`, `quit`, and `bye` leave before any create call.

## Edge cases

| Input | Result |
|---|---|
| a tool calls another tool | not possible; one batch per step |
| the model returns text and tool calls | both are kept; text streams, then the calls run |
| the model returns nothing at all | `[empty response]` in history, printed once |
| the model repeats a failing call | it sees the same error string again until the step limit |
| Ctrl+C between steps | the turn ends, history stays coherent |

## Verification

- One prompt that needs no tool: one answer, one status block, `>>> `.
- One prompt that needs a tool: exactly one `|Tool Used:` line.
- A bad tool name never reaches a real tool; the model gets `Unknown tool:`.
- A tool that raises returns `Tool error:` and the loop continues.
- `Max limit reached: 16` on a turn that never stops calling tools.
- Ctrl+C mid-stream leaves a usable next turn.

## Gaps

- History is unbounded. Compaction waits for the context gap to hurt on a real
  codebase.
- `MAX_STEPS` is a constant, not a setting.
- No per-step cap on the number of parallel tool calls.

## History

- 2026-09-30  The call site moved from LiteLLM to `openai`. One
  `chat.completions.create` replaced the per-turn completion helper.
- 2026-10-27  Streaming replaced the raw response read. The assistant message
  is now assembled from `chunk.to_dict()` deltas instead of
  `json.loads(raw.text)`.
