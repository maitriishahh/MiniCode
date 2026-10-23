from minicode.resolve_path import _resolve

def read(path: str, offset: int = 1, limit: int = 2000) -> str:
    """Read line-numbered text from a file. Always to be used before editing or writing to any file.

    Args:
        path: Absolute path, or path relative to the workspace. Outside the workspace asks permission.
        offset: First line to read (1-indexed)
        limit: Maximum lines to return
    """
    target = _resolve(path)
    lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    start = max(offset - 1, 0)
    picked = lines[start:start + limit]
    numbered = [f"{start + i + 1}: {line}" for i, line in enumerate(picked)]
    return "\n".join(numbered) if numbered else "(empty file)"