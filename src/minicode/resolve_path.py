from pathlib import Path
import re
import sys

_BASH_DRIVE = re.compile(r"^/([A-Za-z])/(.*)$")

def _sandbox_root() -> Path:
    if "--sandbox" in sys.argv:
        i = sys.argv.index("--sandbox")
        if i + 1 < len(sys.argv):
            return Path(sys.argv[i + 1]).resolve()
    return Path.cwd().resolve()

SANDBOX = _sandbox_root()
SANDBOX.mkdir(parents=True, exist_ok=True)

_approved: set[Path] = set()

def _from_bash(path: str) -> str:
    if sys.platform != "win32":
        return path
    match = _BASH_DRIVE.match(path.replace("\\", "/"))
    if not match:
        return path
    return f"{match.group(1)}:/{match.group(2)}"


def classify(path: str) -> tuple[str, Path]:
    path = _from_bash(path)
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