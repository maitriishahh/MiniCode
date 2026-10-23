import re
import sys

RULES = (
    ("read", "*", "allow"),
    ("glob", "*", "allow"),
    ("grep", "*", "allow"),
    ("edit", "*", "allow"),
    ("shell", "*", "ask"),
    ("external_directory", "*", "ask"),
)

ALWAYS: set[tuple[str, str]] = set()
ask = {"fn": None}


def norm(value: str) -> str:
    text = value.replace("\\", "/")
    if sys.platform == "win32":
        return text.casefold()
    return text


def _match(pattern: str, value: str) -> bool:
    parts: list[str] = []
    for ch in pattern:
        if ch == "*":
            parts.append(".*")
        elif ch == "?":
            parts.append(".")
        else:
            parts.append(re.escape(ch))
    return re.fullmatch("".join(parts), value) is not None


def check(key: str, value: str) -> str:
    seen = norm(value)
    action = "deny"
    for rule_key, pattern, effect in RULES:
        if rule_key == key and _match(norm(pattern), seen):
            action = effect
    if action == "ask" and (key, seen) in ALWAYS:
        return "allow"
    return action


def remember(key: str, value: str) -> None:
    ALWAYS.add((key, norm(value)))


def decide(key: str, value: str) -> str:
    action = check(key, value)
    if action != "ask":
        return action
    fn = ask["fn"]
    if fn is None:
        return "deny"
    choice = fn(key, value)
    if choice == "always":
        remember(key, value)
        return "allow"
    if choice == "once":
        return "allow"
    return "deny"