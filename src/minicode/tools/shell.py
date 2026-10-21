import os
import shutil
import subprocess
import sys
from pathlib import Path

from minicode.resolve_path import SANDBOX

CAP = 8000
_SEARCHED: list[str] = []

def _file(path:str | None)-> str | None:
    if path and Path(path).is_file():
        return str(Path(path))
    return None

def _wsl_shim(path:str) -> bool:
    system = os.environ.get("SystemRoot",r"C:\Windows")
    resolved = os.path.normcase(str(Path(path).resolve()))
    for folder in ("System32","Sysnative"):
        shim = os.path.normcase(str(Path(system) / folder / "bash.exe"))
        if resolved == shim:
            return True
    return False

def _try(path:str | None, label:str) -> str | None:
    _SEARCHED.append(label)
    return _file(path)

def _win_bash() -> str | None:
    for key in ("ProgramFiles","ProgramFiles(x86"):
        root = os.environ.get(key)
        if not root:
            continue
        found = _try(str(Path(root) / "Git" / "bin" / "bash.exe"), f"{key}\\Git\\bin\\bash.exe")
        if found:
            return found
        which = shutil.which("bash.exe")
        _SEARCHED.append(f"bash.exe on PATH ({which or 'missing'})")
        if which and _file(which) and not _wsl_shim(which):
            return which
        return None

def _win_powershell() -> str | None:
    which = shutil.which("pwsh.exe")
    found = _try(which, f"pwsh.exe on PATH ({which or 'missing'})")
    if found:
        return found
    root = os.environ.get("ProgramFiles")
    if root:
        found = _try(
            str(Path(root) / "PowerShell" / "7" / "pwsh.exe"),
            "ProgramFiles\\PowerShell\\7\\pwsh.exe",
        )
        if found:
            return found
    which = shutil.which("powershell.exe")
    found = _try(which, f"powershell.exe on PATH ({which or 'missing'})")
    if found:
        return found
    system = os.environ.get("SystemRoot", r"C:\Windows")
    return _try(
        str(Path(system) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"),
        "System32\\WindowsPowerShell\\v1.0\\powershell.exe",
    )

def _unix() -> tuple[str, str] | None:
    for path, label, dialect in(
        ("/bin/bash", "/bin/bash", "bash"),
        (shutil.which("bash"),"bash on PATH","bash"),
        ("/bin/sh","/bin/sh","sh"),
        (shutil.which("sh"),"sh on PATH","sh"),
    ):
        found = _try(path, f"{label} ({path or 'missing'})")
        if found:
            return found, dialect
    return None

def _resolve() -> tuple[list[str], str, str] | None:
    if sys.platform == "win32":
        bash = _win_bash()
        if bash:
            return [bash, "-c"], "bash", "bash"
        ps = _win_powershell()
        if ps:
            return [ps, "-NoProfile", "-NonInteractive", "-Command"], "powershell", "powershell"
        return None
    found = _unix()
    if not found:
        return None
    binary, dialect = found
    return [binary, "-c"], dialect, "bash"

_RESOLVED = _resolve()

_DOCS = {
    "bash": (
        "Run a bash command in the sandbox for tests and git. Chain with &&.",
        "Bash command. Chain with &&.",
    ),
    "sh": (
        "Run a POSIX sh command in the sandbox for tests and git. No bash features.",
        "POSIX sh command. Chain with &&. No bash features.",
    ),
    "powershell": (
        "Run a PowerShell command in the sandbox for tests and git. Separate commands with a semicolon.",
        "PowerShell command. Separate commands with a semicolon.",
    ),
}


def _decode(raw: bytes | None) -> str:
    if not raw:
        return ""
    powershell = _RESOLVED is not None and _RESOLVED[1] == "powershell"
    if powershell and (raw.startswith((b"\xff\xfe", b"\xfe\xff")) or b"\x00" in raw[:200]):
        return raw.decode("utf-16", errors="replace")
    return raw.decode("utf-8", errors="replace")


def _output(out: bytes | None, err: bytes | None) -> str:
    parts = [p for p in (_decode(out).strip("\n"), _decode(err).strip("\n")) if p]
    return "\n".join(parts)


def _cap(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    if len(text) <= CAP:
        return text
    return f"... truncated — narrow the command\n{text[-CAP:]}"


def _show(text: str) -> str:
    label = _RESOLVED[1] if _RESOLVED else "missing"
    print(
        f"---\nShell ({label}):\n{text}",
        end="---\n" if text.endswith("\n") else "\n---\n",
    )
    return text

def shell(command: str) -> str:
    if not command.strip():
        raise ValueError("Empty command")
    if ".env" in command.lower():
        raise ValueError("Refusing to access .env file")
    if _RESOLVED is None:
        raise ValueError("No shell found. Searched: " +"; ".join(_SEARCHED))
    argv, _dialect, _name = _RESOLVED
    try:
        proc = subprocess.run(
            [*argv, command],
            cwd=SANDBOX,
            capture_output=True,
            timeout=120
        )
    except subprocess.TimeoutExpired as exc:
        body = _cap(_output(exc.stdout, exc.stderr))
        text = f"{body}\nTimed out after 120s" if body else "Timed out after 120s"
        return _show(text)
    body = _cap(_output(proc.stdout, proc.stderr))
    if not body:
        body = "(no output)"
    return _show(f"exit {proc.returncode}\n{body}")

if _RESOLVED:
    _summary, _arg = _DOCS[_RESOLVED[1]]
    shell.__name__ = _RESOLVED[2]
    shell.__doc__ = f"{_summary}\n\nArgs:\n    command: {_arg}\n"
else:
    shell.__name__ = "powershell" if sys.platform == "win32" else "bash"
    shell.__doc__ = (
        "Run a shell command in the sandbox for tests and git.\n\n"
        "Args:\n"
        "    command: Command for the shell named above.\n"
    )