from pathlib import Path
import sys

def _sandbox_root() -> Path:
    if "--sandbox" in sys.argv:
        i = sys.argv.index("--sandbox")
        if i + 1 < len(sys.argv):
            return Path(sys.argv[i + 1]).resolve()
    return Path(__file__).resolve().parents[2] / "sandbox"

SANDBOX = _sandbox_root()
SANDBOX.mkdir(parents=True, exist_ok=True)

def _resolve(path: str) -> Path:
    p = (SANDBOX / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
    if p != SANDBOX and SANDBOX not in p.parents:
        raise ValueError(f"Outside sandbox: {path}")
    if p.name == ".env" or p.name.startswith(".env."):
        raise ValueError("Refusing to access .env files")
    return p