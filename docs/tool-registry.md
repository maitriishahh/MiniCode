# Tool registry

**Status:** shipped · **Layer:** 0 · **Files:** `schema_generator.py`, `agent.py`
**Verified:** 2026-10-30

A tool is an ordinary Python function with a Google-style docstring. One
wrapper turns it into the JSON schema the model sees and the callable the loop
runs, so the schema and its validator can never disagree.

## Contract

`tool_from_fn(fn)` returns `(schema, run)`.

| Input | Becomes |
|---|---|
| first docstring line | the tool `description` |
| each `Args:` entry `name: text` | that parameter's `description` |
| a parameter with no `Args:` entry | the parameter name as its description |
| type hint `str` / `int` / `float` / `bool` | `string` / `integer` / `number` / `boolean` |
| any other type | `string` |
| a parameter with no default | listed in `required` |
| a parameter with a default | optional, default carried into the validator |
| `fn.__name__` | the tool name, and the registry key |

`run(raw_json)` validates and calls:

```python
def run(raw_json: str) -> str:
    try:
        args = model.model_validate_json(raw_json)
    except ValidationError as exc:
        return f"Invalid Arguments: {exc}"
    try:
        return str(fn(**args.model_dump()))
    except Exception as exc:
        return f"Tool error: {exc}"
```

Both failure paths return a string. Neither raises. `KeyboardInterrupt` is not
caught: `except Exception` does not match it, which is what lets Ctrl+C abort a
tool.

The registry is built once at import:

```python
for _fn in (read, write, edit, glob, grep, shell):
    _schema, _run = tool_from_fn(_fn)
    TOOLS[_fn.__name__] = _run
    SCHEMAS.append(_schema)
```

A new tool is `tools/<name>.py` plus one name in that tuple.

`active_schemas()` returns every schema except the names in `PLAN_DENIED`
(`write`, `edit`) while plan is active. `active_names()` mirrors it for the
status line.

The `Args:` parser stops at a blank line or at the first line without a colon.
A parameter line is split on the first colon only, so a description may contain
colons.

## Why this shape

The alternative is a hand-written JSON schema per tool and a hand-maintained
`if/elif` dispatch chain. Both drift: the schema says `limit` is a string while
the function takes an int, and the chain grows a branch per tool.

Deriving both from one source means the docstring, the type hint, and the
validator cannot disagree. `pydantic.create_model` gives schema and validation
in one step, which is why it was approved from the first layer rather than
added after a bad-arguments bug.

Only the first docstring line reaches the model. Scope sentences and routing
rules in the docstring body are invisible, which is why the `write` versus
`edit` routing rule lives in `SYSTEM` and not in a tool's docstring.

A `Returns:` block must not be added to a tool docstring. The parser treats
any indented `word: text` line after `Args:` as a parameter, so `Returns: ...`
becomes a phantom parameter named `Returns`.

## Invariants

- The pair is `(schema, run)`. `schema_generator.tool_from_fn`.
- Validation and execution failures both return strings.
- `except Exception` only, never `BaseException`. Ctrl+C must escape.
- The registry key is `fn.__name__`. `shell.__name__` is replaced before
  wrapping, so the key is `bash`, `sh`, or `powershell`, never `shell`.
  `tools/shell.py`.
- `PLAN_DENIED` filters the schema, and the dispatch re-checks it.
  `agent.active_schemas`, `agent.agent`.

## Edge cases

| Input | Result |
|---|---|
| malformed JSON | `Invalid Arguments: ...` |
| a missing required argument | `Invalid Arguments: ...` |
| an argument of the wrong type | `Invalid Arguments: ...` unless pydantic coerces it |
| an unknown key in the arguments | ignored; pydantic's default is `extra="ignore"` |
| a function with no docstring | the function name becomes the description |
| a function returning a non-string | `str()` of the value |
| the tool raises `ValueError` | `Tool error: {message}` |
| the user presses Ctrl+C inside a tool | propagates as `KeyboardInterrupt` |

## Verification

- `uv run python -c "from minicode.agent import TOOLS; print(sorted(TOOLS))"`
  lists `bash` (or `powershell`), `edit`, `glob`, `grep`, `read`, `write`.
- A bad-argument call returns `Invalid Arguments:` and the loop continues.
- A tool that raises returns `Tool error:` and the file is untouched.
- Ctrl+C during a tool returns to `>>> ` instead of crashing.
- The status line's `Tools Loaded` matches `active_names()` in both modes.

## Gaps

- No support for nested objects or arrays in a tool signature. Every tool takes
  strings and integers.
- Extra arguments are silently ignored rather than rejected, so a model typo in
  a key name looks like a successful call with a missing value.

## History

- 2026-09-22  The `.env` error wording changed from "read" to "access" because
  `write` and `edit` share the same resolver.
- 2026-10-21  The shell tool's name is resolved before wrapping, so the model
  never sees a tool called `shell`.
