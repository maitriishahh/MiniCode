# Models

**Status:** shipped · **Layer:** 2 · **Files:** `agent.py`, `__main__.py`
**Verified:** 2026-10-30

A model is a record, not a string. The record carries the server, the
environment variable that holds the key, and the numbers the status line would
need. One record is active at a time, and `/models` changes which one.

## Contract

`_SERVERS` is a tuple of `(id_env, key_env, base)`:

| id env | key env | base |
|---|---|---|
| `GEMINI_MODEL` | `GEMINI_API_KEY` | `https://generativelanguage.googleapis.com/v1beta/openai/` |
| `OLLAMA_MODEL` | `OLLAMA_API_KEY` | `http://127.0.0.1:11434/v1` |

A server whose id env is empty is skipped at import. It is not disabled later,
and it does not appear in `/models`.

Each loaded server becomes one record:

```text
id, api_key, api_base, context_window, max_tokens, cost{input, output, cache_read, cache_write}, tools
```

`api_key` holds the **name** of the environment variable, never the secret.
Lookup is `os.getenv(record["api_key"])`. `context_window` and `max_tokens` are
`None`, the four cost fields are zero, and `tools` is `True`. Nothing reads the
cost fields or `max_tokens` yet.

`default_id` is `os.getenv("GEMINI_MODEL")` read once at import. The active id
starts as `default_id` when that id is loaded, otherwise as the first loaded
model. A restart returns to `default_id`; `/models` changes it for the session
only.

`_client_for(record, max_retries=None)` builds an `OpenAI` client from the
record. A missing key on a loopback base becomes the literal `"ollama"`, so a
local server needs no key. Any other missing key is passed through and fails at
the first call.

`_create(client, **kwargs)` is the only `chat.completions.create` call in the
package. The agent loop and the title worker both call it.

The create body is:

```python
{
    "model": record["id"],
    "messages": messages,
    "tools": active_schemas(),
    "stream": True,
    "stream_options": {"include_usage": True},
}
```

Two optional additions, chosen by the base URL:

- A `generativelanguage.googleapis.com` base gets
  `extra_body.google.thinking_config` with `include_thoughts: True` and
  `thinking_level` from `/effort`.
- A loopback base gets `reasoning_effort` from `/effort`.

They are mutually exclusive. An Ollama server never receives the Gemini body.

A failure returns `Model Error: {exc}`, printed once, and the REPL survives.

## Why this shape

A model string cannot carry `api_base`, which env var holds the key, or a
context window. The `openai` package speaks any server that exposes
`/chat/completions`, so the base URL selects the server and the id is that
server's own id. There is no `gemini/` prefix, no `ollama_chat/` prefix, and no
installed SDK per provider.

The registry is the product layer, the same idea as `tool_from_fn` applied to
servers: one typed record instead of scattered strings. A new server is one
`_SERVERS` tuple plus two env lines. Groq would be
`https://api.groq.com/openai/v1` and nothing else, but it is not added until it
is asked for.

This deliberately stops short of OpenCode's provider catalog. A 75-provider
list, `/connect`, and variants are a later phase and a different mechanism; see
`docs/STATUS.md`. Pi scrapes models.dev for the same reason MiniCode does not:
the catalog is a product, and this harness needs two servers. OpenCode Console
free-tier ids are also out: since 18 September 2026 that tier returns
`403 FreeTierError` outside the official client, and faking client headers is
not a workaround.

Mid-session switching needs no history conversion because history is plain
Chat Completions dicts. A Gemini thought signature, if the server sent one,
rides in the assistant dict and is neither parsed nor invented.

## Invariants

- `api_key` is an env var name. The secret never enters the record.
  `agent._entry`.
- Base URLs live in code. Only ids and keys come from `.env`.
- One create site. `agent._create`.
- The Gemini body never reaches a loopback server, and `reasoning_effort` never
  reaches Gemini. `agent._gemini_extra`.
- `/models` never writes the session's choice back to `.env`.
- A failed create returns `Model Error:` and does not raise.

## Edge cases

| Input | Result |
|---|---|
| `GEMINI_MODEL` empty | Gemini is skipped; Ollama may be the only model |
| both ids empty | `MODELS` is empty; the first prompt returns `Model Error:` |
| `/models 0` or `99` | `Unknown Model: {token}`, no switch |
| `/models <unloaded id>` | `Unknown Model: {token}`, no switch |
| key missing on Gemini | `401`, reported as `Model Error:` |
| key missing on loopback | becomes `"ollama"`, call proceeds |
| Ollama not running | `Model Error:` with the connection error |

## Verification

- `/models` lists each loaded id with a position and an ` (active)` marker.
- `/models 2` switches and the next status block names the new id.
- Restart returns to `default_id`.
- With `OLLAMA_MODEL` empty, no Ollama id appears.
- Bad key: the first prompt prints `Model Error:` and `>>> ` returns.

## Gaps

- `context_window` is `None`, so the context percentage in the status line
  never prints.
- `max_tokens` is `None` and unused; the title worker passes its own.
- Cost fields are zero and unused. Pricing waits for more models.
- No `/connect`, no browser login, no catalog import, no variants.
- No retry policy beyond the SDK default for the agent; the title worker passes
  `max_retries=1`.

## History

- 2026-09-30  LiteLLM was replaced by the `openai` client. `_SERVERS` and the
  record replaced a model string plus a provider prefix.
- 2026-09-30  The registry stopped storing the secret; the record keeps the env
  var name.
- 2026-10-28  `/model` was renamed `/models`; the old name is now a named error.
