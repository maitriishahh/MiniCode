from minicode.resolve_path import _resolve

def write(path:str, content:str) -> str:
    """
   Create a new file or overwrite an entire existing file with complete content.

    Args:
        path: Path to the file
        content: FULL final file contents — replaces everything
    """
    target = _resolve(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"Wrote {len(content.encode('utf-8'))} bytes to {path}"