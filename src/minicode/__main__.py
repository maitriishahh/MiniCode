import time

from minicode.resolve_path import SANDBOX
from minicode.agent import agent, TOOLS, last_usage, SYSTEM, MODEL

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
        print(
            f"---"
            f"\nModel: {MODEL} | Mode: {MODE} | Tools Loaded: {', '.join(TOOLS)}"
            f"\nSandbox: {SANDBOX}"
            f"\n{prompt_tokens:,} In | {out_tokens:,} Out | {elapsed:.1f}\n"
            f"---"
        )

if __name__ == "__main__":
    main()
