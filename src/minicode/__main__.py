import time

from minicode.resolve_path import SANDBOX
from minicode.agent import agent, TOOLS, last_usage, SYSTEM, active, MODELS

MODE = "build"

def main() -> None:
    print(f"Sandbox: {SANDBOX}")
    messages = [
        {
            "role":"system",
            "content": SYSTEM
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
        if stripped == "/model" or stripped.startswith("/model "):
            parts = stripped.split(maxsplit=1)
            if len(parts) == 1:
                for mid in MODELS:
                    mark = " (active)" if mid == active["id"] else ""
                    print(f"{mid}{mark}")
            else:
                chosen = parts[1].strip()
                if chosen not in MODELS:
                    print(f"Unknown Model: {chosen}")
                else:
                    active["id"] = chosen
                    print(f"Model: {active["id"]}")
            continue


        messages.append(
            {
                "role":"user",
                "content": text
            }
        )
        start_time = time.perf_counter()
        answer = agent(messages)
        elapsed = time.perf_counter() - start_time
        prompt_tokens = last_usage["prompt_tokens"]
        out_tokens = last_usage["completion_tokens"]

        print(f"\nminicode >> {answer}\n")
        window = MODELS[active["id"]]["context_window"]
        ctx = f" | {prompt_tokens / window:.1%} context" if window else ""
        print(
            f"---"
            f"\nModel: {active['id']} | Mode: {MODE} | Tools Loaded: {', '.join(TOOLS)}"
            f"\nSandbox: {SANDBOX}"
            f"\n{prompt_tokens:,} In | {out_tokens:,} Out | Elapsed: {elapsed:.1f}s{ctx}\n"
            f"---"
        )

if __name__ == "__main__":
    main()
