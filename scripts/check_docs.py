"""Check the live docs against the convention in docs/STYLE.md.

Stdlib only. The archived build guides are frozen and are not checked.
Run from the repository root:

    uv run python scripts/check_docs.py
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
INDEX = DOCS / "index.md"
SKIP = {"archive"}

FEATURE_SECTIONS = ("## Verification", "## Gaps")
CONTRACT = ("## Contract", "## Event contract")
STALE = (
    re.compile(r"What you'll build"),
    re.compile(r"Segment \d"),
    re.compile(r"(?m)^user >>"),
    re.compile(r"(?m)^minicode >>"),
)
NUMBERED = re.compile(r"docs/(0\d|1[01])-")
LINK = re.compile(r"\]\(([^)]+)\)")
LIMITS = {"STATUS.md": 60}


def live_markdown() -> list[Path]:
    found = []
    for path in ROOT.rglob("*.md"):
        if any(part in SKIP or part == ".venv" for part in path.parts):
            continue
        found.append(path)
    return found


def check_links(paths: list[Path], errors: list[str]) -> None:
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for match in LINK.finditer(text):
            target = match.group(1)
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            file_part = target.split("#", 1)[0]
            if not file_part:
                continue
            dest = (path.parent / file_part).resolve()
            if not dest.exists():
                errors.append(f"{path.relative_to(ROOT)}: broken link {target}")


def check_index(errors: list[str]) -> None:
    text = INDEX.read_text(encoding="utf-8")
    if "](archive/" in text or "](../docs/archive" in text:
        errors.append("docs/index.md links the archived build guides")
    links = []
    for match in LINK.finditer(text):
        target = match.group(1).split("#", 1)[0]
        if not target:
            continue
        links.append((INDEX.parent / target).resolve())
    names = [path.name for path in links if path.parent == DOCS.resolve()]
    dupes = sorted({name for name in names if names.count(name) > 1})
    if dupes:
        errors.append(f"docs/index.md links more than once: {', '.join(dupes)}")
    linked = set(names)
    for path in sorted(DOCS.glob("*.md")):
        if path.name == "index.md":
            continue
        if path.name not in linked:
            errors.append(f"docs/index.md does not link {path.name}")


def check_feature(path: Path, errors: list[str]) -> None:
    text = path.read_text(encoding="utf-8")
    if "**Status:**" not in text:
        return
    if "**Verified:**" not in text:
        errors.append(f"{path.relative_to(ROOT)}: missing Verified")
    if not any(heading in text for heading in CONTRACT):
        errors.append(f"{path.relative_to(ROOT)}: missing a contract heading")
    for heading in FEATURE_SECTIONS:
        if heading not in text:
            errors.append(f"{path.relative_to(ROOT)}: missing {heading}")
    limit = LIMITS.get(path.name, 250)
    lines = text.count("\n") + (0 if text.endswith("\n") else 1)
    if lines > limit:
        errors.append(f"{path.relative_to(ROOT)}: {lines} lines, limit {limit}")


def check_phrases(paths: list[Path], errors: list[str]) -> None:
    for path in paths:
        # STYLE.md quotes the forbidden phrases. That is the rule, not a violation.
        if path.name == "STYLE.md" or path.is_relative_to(DOCS / "archive"):
            continue
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(ROOT)
        for pattern in STALE:
            if pattern.search(text):
                errors.append(f"{rel}: stale phrase {pattern.pattern}")
        if NUMBERED.search(text):
            errors.append(f"{rel}: numbered build-guide path")


def main() -> int:
    errors: list[str] = []
    paths = live_markdown()
    check_links(paths, errors)
    check_index(errors)
    for path in sorted(DOCS.glob("*.md")):
        check_feature(path, errors)
    status = DOCS / "STATUS.md"
    lines = status.read_text(encoding="utf-8").count("\n")
    if lines > LIMITS["STATUS.md"]:
        errors.append(f"docs/STATUS.md: {lines} lines, limit {LIMITS['STATUS.md']}")
    check_phrases(paths, errors)
    if errors:
        print("\n".join(errors))
        return 1
    print(f"docs ok ({len(paths)} markdown files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
