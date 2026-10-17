"""Scan git history + working tree for secrets. Never prints a secret value.
Usage: python -m scripts.secret_scan [repo_path]     (.env is always read from this project)
Checks: (1) every non-trivial value in .env, (2) common key patterns, (3) .env was never tracked."""
import re
import subprocess
import sys
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ENV_FILE.parent
# Only these .env keys are secrets; LLM urls/model names are public defaults and usernames are not secret.
SENSITIVE_KEYS = {"FALKORDB_HOST", "FALKORDB_PORT", "FALKORDB_PASSWORD", "LLM_API_KEY",
                  "LLM_FALLBACK_API_KEY", "RESET_TOKEN"}
PATTERNS = {
    "groq key": r"gsk_[A-Za-z0-9]{20,}",
    "google key": r"AIza[0-9A-Za-z_\-]{30,}",
    "github token": r"gh[pousr]_[A-Za-z0-9]{30,}",
    "openai-style key": r"sk-[A-Za-z0-9]{20,}",
    "private key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "hardcoded password": r"(?i)password\s*[:=]\s*['\"][^'\"\s]{6,}['\"]",
}


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                          errors="replace").stdout


def env_values():
    values = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, _, value = line.partition("=")
                value = value.strip().strip('"').strip("'")
                if key.strip() in SENSITIVE_KEYS and len(value) >= 4 and value.lower() not in ("true", "false", "localhost", "acme", "*"):
                    values[key.strip()] = value
    return values


def main():
    problems = []
    if git("log", "--all", "--oneline", "--", ".env").strip():
        problems.append(".env appears in git history")
    if ".env" in git("ls-files").split():
        problems.append(".env is tracked")

    history = git("log", "--all", "-p", "--no-color")
    tracked = [f for f in git("ls-files").splitlines() if f]
    tree = "".join((ROOT / f).read_text(encoding="utf-8", errors="replace") for f in tracked
                   if (ROOT / f).is_file())

    for key, value in env_values().items():
        for where, text in (("history", history), ("tracked files", tree)):
            if value in text:
                problems.append(f"value of {key} found in {where}")
    for label, pattern in PATTERNS.items():
        for where, text in (("history", history), ("tracked files", tree)):
            if re.search(pattern, text):
                problems.append(f"{label} pattern found in {where}")

    checked = len(env_values())
    print(f"checked {checked} .env value(s), {len(PATTERNS)} patterns, {len(tracked)} tracked files, "
          f"{len(history.splitlines())} lines of history")
    if problems:
        print("PROBLEMS:", *problems, sep="\n  - ")
        sys.exit(1)
    print("clean: no secrets found")


if __name__ == "__main__":
    main()
