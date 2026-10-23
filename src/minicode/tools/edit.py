from minicode.resolve_path import _resolve
import difflib

def _diff_lines(text: str) -> list[str]:
    return [line + "\n" for line in text.splitlines()]

CONTEXT = 5

def _window(original: str, old_text:str, new_text:str, updated: str) -> tuple[str, str]:
    start_line = original[:original.find(old_text)].count("\n")
    changed = len(new_text.splitlines()) if new_text else 0
    lines = updated.splitlines()
    if not lines:
        return "(empty file)", f"deleted at {start_line + 1}"
    lo = max(0, start_line - CONTEXT)
    if changed == 0:
        hi = min(len(lines), start_line + CONTEXT)
        where = f"deleted at {start_line + 1}"
    else:
        hi = min(len(lines), start_line + changed + CONTEXT)
        where = f"changed {start_line + 1} - {start_line + changed}"
    body = "\n".join(f"{i + 1}: {lines[i]}" for i in range(lo, hi))
    return body, where


def edit(path:str, old_text:str, new_text:str) -> str:
    """
    Replace one exact unique span in an existing file.
    Use for any partial change: replacements, insertions (old_text=anchor, new_text=anchor+insertion), deletions.
    Read the file first for exact text. Never rewrite the whole file; use `write` instead.

    Args:
        path: Absolute path, or path relative to the workspace. Outside the workspace asks permission.
        old_text: Exact text to find (must match once)
        new_text: Replacement text
    """
    if not old_text:
        raise ValueError("old_text must not be empty")
    target = _resolve(path)
    original = target.read_text(encoding="utf-8", errors="replace")
    n = original.count(old_text)
    if n == 0:
        raise ValueError(f"old_text not found in {path}")
    if n > 1:
        raise ValueError(f"old_text found {n} times in {path}")
    updated = original.replace(old_text, new_text,1)
    diff = "".join(
        difflib.unified_diff(
            _diff_lines(original),
            _diff_lines(updated),
            fromfile=f"a/{path} (before)",
            tofile=f"b/{path} (after)",
            lineterm="\n",
        )
    )
    if diff:
        print(f"---\nDiff: {path}\n{diff}", end="---\n" if diff.endswith("\n") else "\n---\n")

    target.write_text(updated,encoding="utf-8")

    body, where = _window(original, old_text, new_text, updated)
    return f"Replaced 1 occurrence in {path} ({where})\n{body}"