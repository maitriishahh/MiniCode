import json
import os
from dotenv import load_dotenv

load_dotenv()

from openai import OpenAI

from minicode.schema_generator import tool_from_fn
from minicode.tools.read import read
from minicode.tools.write import write
from minicode.tools.edit import edit
from minicode.tools.glob import glob
from minicode.tools.grep import grep

MAX_STEPS = 8

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai/"
OLLAMA_BASE = "http://127.0.0.1:11434/v1"

_SERVERS = (
    ("GEMINI_MODEL", "GEMINI_API_KEY", GEMINI_BASE),
    ("OLLAMA_MODEL", "OLLAMA_API_KEY", OLLAMA_BASE),
)

def _entry(model_id, api_key_env, api_base, context_window=None, max_tokens=None):
    return {
        "id": model_id,
        "api_key": api_key_env,
        "api_base": api_base,
        "context_window": context_window,
        "max_tokens": max_tokens,
        "cost": {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0},
        "tools": True,
    }

MODELS = {}
for id_env, key_env, base in _SERVERS:
    model_id = os.getenv(id_env)
    if model_id:
        MODELS[model_id] = _entry(model_id, key_env, base)

default_id = os.getenv("GEMINI_MODEL")
active = {"id": default_id if default_id in MODELS else next(iter(MODELS), None)}

SYSTEM = (
    "You are a concise coding assistant. Use tools when they help. Be brief. "
    "`write` creates a new file, or overwrites an existing file with complete content. "
    "To overwrite, `read` then `write` the full file. "
    "`edit` changes one exact unique span. For add/append/insert or replace X with Y, `read` then `edit`; "
    "add/append means insert while preserving all existing content — never delete or rewrite it; "
    "never `write` with partial content. "
    "Locate with `glob`, confirm with `grep`, then `read` before mutating."
)

TOOLS = {}
SCHEMAS = []

for _fn in (read,write,edit,glob,grep):
    _schema, _run = tool_from_fn(_fn)
    TOOLS[_fn.__name__] = _run
    SCHEMAS.append(_schema)

last_usage = {"prompt_tokens": 0, "completion_tokens": 0}

def agent(messages:list) -> str:
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
        try:
            print(f"\n~~Thinking...\n")
            resp = client.with_raw_response.chat.completions.create(
                model=record["id"],
                messages=messages,
                tools=SCHEMAS
            )
            body = json.loads(resp.text)
        except Exception as exc:
            return f"Model Error: {exc}"

        usage = body.get("usage") or {}
        last_usage["prompt_tokens"] = usage.get("prompt_tokens") or 0
        last_usage["completion_tokens"] += usage.get("completion_tokens") or 0
        msg = body["choices"][0]["message"]
        messages.append(msg)
        calls = msg.get("tool_calls") or []
        if not calls:
            return msg.get("content") or ""
        for call in calls:
            name = call["function"]["name"]
            args = call["function"]["arguments"]
            run = TOOLS.get(name)
            if run:
               content = run(args)
               print(f"\n|Tools Used: `{name}` ({args})|\n")
            else:
                content = f"Unknown tool: {name}"

            messages.append(
                {
                    "role":"tool",
                    "tool_call_id":call["id"],
                    "content":content,
                }
            )
    return f"Max limit reached: {MAX_STEPS}. Try smaller request."