import os
import re
from pathlib import Path
from minicode.resolve_path import SANDBOX, _resolve

def grep(pattern: str, path:str=".", include:str="*",limit:int=50) -> str:
    """
    Search file contents under the sandbox for a regex pattern.

    Args:
        pattern: Regex pattern to search for
        path: Subtree root, relative to the sandbox
        include: Only search files whose names match this glob, e.g. *.py
        limit: Maximum matches to return
    """

    root = _resolve(path)
    if not root.is_dir():
        raise ValueError(f"Not a directory: {path}")
    regex = re.compile(pattern)
    hits: list[tuple[str, int, str]] = []
    for dirpath, dirnames, filenames in root.walk():
        dirnames[:] = [
            name for name in dirnames
            if not name.startswith(".") and name not in ("__pycache__",".venv")
        ]
        for name in filenames:
            if name == ".env" or name.startswith(".env."):
                continue
            if not Path(name).match(include):
                continue
            file = Path(dirpath) / name
            try:
                text = file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if "\0" in text:
                continue
            rel = file.relative_to(SANDBOX).as_posix()
            for i,line in enumerate(text.splitlines(),1):
                if regex.search(line):
                    hits.append((rel,i,line))
    if not hits:
        return "(no matches)"
    hits.sort()
    found = [f"{rel}:{i}: {line}" for rel, i, line in hits]
    cap = min(max(limit, 0), 50)
    shown = found[:cap]
    if len(found) > cap:
        shown.append(f"... and {len(found) - cap} more matches")
    return "\n".join(shown)