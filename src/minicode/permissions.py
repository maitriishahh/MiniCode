import re
import sys

RULES = (
    ("read", "*", "allow"),
    ("read", "*.env", "ask"),
    ("read", "*.env.*", "ask"),
    ("read", "*.env.example", "allow"),
    ("glob", "*", "allow"),
    ("grep", "*", "allow"),
    ("edit", "*", "allow"),
    ("shell", "*", "allow"),
    ("shell", "*.env*", "ask"),
    ("external_directory", "*", "ask"),
)

_PLAN_VERBS = {
    "rm", "rmdir", "del", "erase", "touch", "mkdir", "mv", "cp", "ln",
    "cat", "head", "tail", "less", "more",
}

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
    return re.fullmatch("".join(parts), value, flags=re.DOTALL) is not None


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


def snapshot_always() -> list[list[str]]:
    return [list(item) for item in sorted(ALWAYS)]


def restore_always(items) -> None:
    ALWAYS.clear()
    if not isinstance(items, list):
        return
    for item in items:
        if (
            isinstance(item, (list, tuple))
            and len(item) == 2
            and isinstance(item[0], str)
            and isinstance(item[1], str)
        ):
            ALWAYS.add((item[0], item[1]))


def plan_touches(command: str) -> bool:
    if ">" in command:
        return True
    for part in re.split(r"&&|;|\|", command):
        words = part.strip().split()
        if not words:
            continue
        token = words[0].replace("\\", "/").rsplit("/", 1)[-1].lower()
        if token in _PLAN_VERBS:
            return True
    return False


def force_ask(key: str, value: str) -> str:
    if check(key, value) == "deny":
        return "deny"
    if (key, norm(value)) in ALWAYS:
        return "allow"
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