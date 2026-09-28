import inspect
from typing import get_type_hints
from pydantic import create_model, ValidationError

TYPE_MAP = {"str": "string", "int": "integer", "float": "number", "bool": "boolean"}

def tool_from_fn(fn):
    """
    Build (openai_schema,run) from a function with a Google-style docstring.
    """
    sig = inspect.signature(fn)
    hints = get_type_hints(fn)
    doc = inspect.getdoc(fn) or fn.__name__
    lines = doc.splitlines()
    description = lines[0].strip()

    #parse "Args:" block: name: description
    params, in_args = {}, False
    for line in lines[1:]:
        s = line.strip()
        if s.lower().startswith("args:"):
            in_args = True
            continue
        if in_args:
            if not s or ":" not in s:
                if not s:
                    continue
                break
            name, desc = s.split(":", 1)
            params[name.strip()] = desc.strip()

    fields = {}
    properties = {}
    required = []
    for name, p in sig.parameters.items():
        t = hints.get(name, str)
        tname = getattr(t, "__name__", "str")
        fields[name] = (t, ...)
        properties[name] = {
            "type": TYPE_MAP.get(tname, "string"),
            "description": params.get(name, name),
        }
        if p.default is inspect.Parameter.empty:
            required.append(name)
        else:
            fields[name] = (t, p.default)

    model = create_model(fn.__name__ + "Args", **fields)
    schema = {
        "type":"function",
        "function":{
            "name":fn.__name__,
            "description":description,
            "parameters":{
                "type":"object",
                "properties":properties,
                "required":required,
            },
        },
    }

    def run(raw_json: str) -> str:
        try:
            args = model.model_validate_json(raw_json)
        except ValidationError as exc:
            return f"Invalid Arguments: {exc}"
        try:
            return str(fn(**args.model_dump()))
        except Exception as exc:
            return f"Tool error: {exc}"
    return schema, run