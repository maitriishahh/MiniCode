from pathlib import Path
from minicode.resolve_path import SANDBOX, _resolve

def glob(pattern:str, path:str=".", limit:int=50) -> str:
    """
    List files whose names match a glob pattern.

    Args:
        pattern: glob pattern, e.g. *.py or test_*
        path: Absolute path, or path relative to the workspace. Outside the workspace asks permission.
        limit: maximum paths to return
    """

    root = _resolve(path)
    if not root.is_dir():
        raise ValueError(f"Not a directory: {path}")
    inside = root == SANDBOX or SANDBOX in root.parents
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
            file = Path(dirpath) / name
            shown = file.relative_to(SANDBOX).as_posix() if inside else file.as_posix()
            found.append(shown)
    found.sort()
    if not found:
        return "(no matches)"
    cap = min(max(limit,0),50)
    shown = found[:cap]
    if len(found) > cap:
        shown.append(f"... and {len(found) - cap} more — refine pattern")
    return "\n".join(shown)
