from pathlib import Path
from minicode.resolve_path import SANDBOX, _resolve

def glob(pattern:str, path:str=".", limit:int=50) -> str:
    """
    List files under sandbox whose names match a glob pattern.

    Args:
        pattern: glob pattern, e.g. *.py or test_*
        path: subtree root, relative to the sandbox
        limit: maximum paths to return
    """

    root = _resolve(path)
    if not root.is_dir():
        raise ValueError(f"Not a directory: {path}")
    found: list[str] = []
    for dirpath, dirnames, filenames in root.walk():
        dirnames[:] = [
            name for name in dirnames
            if not name.startswith(".") and name not in ("__pycache__", ".venv")
        ]
        for name in filenames:
            if name == ".env" or name.startswith(".env."):
                continue
            if not Path(name).match(pattern):
                continue
            rel = (Path(dirpath) / name).relative_to(SANDBOX).as_posix()
            found.append(rel)
    found.sort()
    if not found:
        return "(no matches)"
    cap = min(max(limit,0),50)
    shown = found[:cap]
    if len(found) > cap:
        shown.append(f"... and {len(found) - cap} more — refine pattern")
    return "\n".join(shown)
