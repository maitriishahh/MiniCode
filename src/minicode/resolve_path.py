from pathlib import Path
import sys

def _sandbox_root() -> Path:
    if "--sandbox" in sys.argv:
        i = sys.argv.index("--sandbox")
        if i + 1 < len(sys.argv):
            return Path(sys.argv[i + 1]).resolve()
    return Path.cwd().resolve()

SANDBOX = _sandbox_root()
SANDBOX.mkdir(parents=True, exist_ok=True)

_approved: set[Path] = set()

def classify(path: str) -> tuple[str, Path]:
    p = (SANDBOX / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
    if p.name == ".env" or p.name.startswith(".env."):
        return "dotenv", p
    if p != SANDBOX and SANDBOX not in p.parents:
        return "external", p
    return "inside", p


def approve(path: Path) -> None:
    _approved.add(path)


def clear_approved() -> None:
    _approved.clear()


def _resolve(path: str) -> Path:
    kind, p = classify(path)
    if kind == "dotenv":
        raise ValueError("Refusing to access .env files")
    if kind == "external" and p not in _approved:
        raise ValueError(f"Outside sandbox: {path}")
    return p