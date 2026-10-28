import time

from minicode.resolve_path import SANDBOX
from minicode.agent import agent, TOOLS, last_usage, session_usage, SYSTEM, active, MODELS, mode, effort, active_names, PLAN_SYSTEM
from minicode.permissions import ask as permission_ask

def _permission(key:str, value:str) -> str:
    print(f"\nPermission: {key} | {value}")
    try:
        answer = input("[o]nce / [a]lways / [d]eny: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return "deny"
    if answer in ("o", "once"):
        return "once"
    if answer in ("a", "always"):
        return "always"
    return "deny"

permission_ask["fn"] = _permission
thinking = {"name": "off"}

def _elapsed(seconds: float) -> str:
    if seconds < 60:
        shown = f"{seconds:.1f}"
        if shown == "60.0":
            return "1m"
        return f"{shown}s"
    left = int(seconds + 0.5)
    parts: list[str] = []
    for name, size in (
        ("y", 365 * 24 * 3600),
        ("w", 7 * 24 * 3600),
        ("d", 24 * 3600),
        ("h", 3600),
        ("m", 60),
        ("s", 1),
    ):
        count, left = divmod(left, size)
        if count:
            parts.append(f"{count}{name}")
        if len(parts) == 2:
            break
    return " ".join(parts)

def main() -> None:
    print(f"Sandbox: {SANDBOX}")
    print(f"\nMode: {mode['name']} | Tools Loaded: {', '.join(active_names())}\n")
    messages = [
        {
            "role":"system",
            "content": SYSTEM + " " + PLAN_SYSTEM if mode["name"] == "plan" else SYSTEM
        }
    ]
    while True:
        try:
            text = input("user >> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if text.strip().lower() in ("exit", "quit", "bye"):
            break
        if not text.strip():
            continue

        stripped = text.strip()
        if stripped == "/plan" or stripped == "/build":
            want = stripped[1:]
            mode["name"] = want
            if want == "plan":
                messages[0]["content"] = SYSTEM + " " + PLAN_SYSTEM
            else:
                messages[0]["content"] = SYSTEM
            print(f"\nMode: {mode['name']} | Tools Loaded: {', '.join(active_names())}\n")
            continue
        if stripped == "/thinking" or stripped.startswith("/thinking "):
            parts = stripped.split(maxsplit=1)
            if len(parts) == 1:
                print(f"\nThinking: {thinking['name']}\n")
            else:
                chosen = parts[1].strip().lower()
                if chosen not in ("on", "off"):
                    print(f"\nUnknown Thinking: {parts[1].strip()}\n")
                else:
                    thinking["name"] = chosen
                    print(f"\nThinking: {thinking['name']}\n")
            continue
        if stripped == "/effort" or stripped.startswith("/effort "):
            parts = stripped.split(maxsplit=1)
            if len(parts) == 1:
                print(f"\nEffort: {effort['name']}\n")
            else:
                chosen = parts[1].strip().lower()
                if chosen not in ("low", "medium", "high"):
                    print(f"\nUnknown Effort: {parts[1].strip()}\n")
                else:
                    effort["name"] = chosen
                    print(f"\nEffort: {effort['name']}\n")
            continue
        if stripped == "/model" or stripped.startswith("/model "):
            ids = list(MODELS)
            parts = stripped.split(maxsplit=1)
            if len(parts) == 1:
                print()
                for n, mid in enumerate(ids, 1):
                    mark = " (active)" if mid == active["id"] else ""
                    print(f"{n} {mid}{mark}")
                print()
            else:
                chosen = parts[1].strip()
                if chosen.isdigit():
                    n = int(chosen)
                    picked = ids[n - 1] if 1 <= n <= len(ids) else None
                    if picked is None:
                        print(f"\nUnknown Model: {chosen}\n")
                        continue
                    chosen = picked
                if chosen not in MODELS:
                    print(f"\nUnknown Model: {chosen}\n")
                else:
                    active["id"] = chosen
                    print(f"\nModel: {active['id']}\n")
            continue

        messages.append(
            {
                "role":"user",
                "content": text
            }
        )
        start_time = time.perf_counter()

        wrote = False
        reasoning = False
        held_nl = ""

        def on_event(kind:str, piece:str = "", final: bool = False) -> None:
            nonlocal wrote, reasoning, held_nl
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
        elapsed = time.perf_counter() - start_time
        prompt_tokens = last_usage["prompt_tokens"]
        out_tokens = last_usage["completion_tokens"]
        session_tokens = session_usage["completion_tokens"]
        window = MODELS[active["id"]]["context_window"]
        if wrote:
            print()
        if answer is None:
            print("\n[interrupted by user]\n")
        elif answer:
            print(f"\n{answer}\n")

        ctx = f" | {prompt_tokens / window:.1%} context" if window else ""
        print(
            f"---"
            f"\nModel: {active['id']} | Mode: {mode['name']} | Tools Loaded: {', '.join(active_names())}"
            f"\nSandbox: {SANDBOX} | Thinking: {thinking['name']} | Effort: {effort['name']}"
            f"\n{prompt_tokens:,} In | {out_tokens:,} Out | {session_tokens:,} Session Usage | Elapsed: {_elapsed(elapsed)}{ctx}\n"
            f"---"
        )

if __name__ == "__main__":
    main()
