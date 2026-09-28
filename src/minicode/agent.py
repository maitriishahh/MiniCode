import os
from dotenv import load_dotenv

load_dotenv()

from litellm import completion

from minicode.schema_generator import tool_from_fn
from minicode.tools.read import read
from minicode.tools.write import write
from minicode.tools.edit import edit

MODEL = os.getenv("GEMINI_MODEL")
API_KEY = os.getenv("GEMINI_API_KEY")
MAX_STEPS = 8

SYSTEM = (
    "You are a concise coding assistant. Use tools when they help. Be brief. "
    "Read before mutating. `write` creates or overwrites whole files with complete content; "
    "`edit` changes one exact unique span. For add/append/insert or replace X with Y, `read` then `edit`; "
    "add/append means insert while preserving all existing content — never delete or rewrite it; "
    "never `write` with partial content."
)

TOOLS = {}
SCHEMAS = []

for _fn in (read,write,edit):
    _schema, _run = tool_from_fn(_fn)
    TOOLS[_fn.__name__] = _run
    SCHEMAS.append(_schema)

last_usage = {"prompt_tokens": 0, "completion_tokens": 0}

def agent(messages:list) -> str:
    last_usage["prompt_tokens"] = 0
    last_usage["completion_tokens"] = 0

    for step in range(MAX_STEPS):
        resp = completion(
            model=MODEL,
            api_key=API_KEY,
            messages=messages,
            tools=SCHEMAS
        )
        usage = getattr(resp,"usage", None)
        last_usage["prompt_tokens"] = getattr(usage,"prompt_tokens",0) or 0
        last_usage["completion_tokens"] += getattr(usage,"completion_tokens",0) or 0
        msg = resp.choices[0].message
        messages.append(
            msg.model_dump(exclude_none=True) if hasattr(msg,"model_dump") else msg
        )
        if not msg.tool_calls:
            return msg.content or ""
        for call in msg.tool_calls:
            run = TOOLS.get(call.function.name)
            if run:
               content = run(call.function.arguments)
               print(f"|Tools Used: `{str(call.function.name)}`|")
            else:
                content = f"Unknown tool: {call.function.name}"

            messages.append(
                {
                    "role":"tool",
                    "tool_call_id":call.id,
                    "content":content,
                }
            )
    return f"Max limit reached: {MAX_STEPS}. Try smaller request."