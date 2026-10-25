#!/usr/bin/env python3
"""Secret scan: fail if a tracked file contains a real credential.

Scans only git-tracked files (so the untracked .env and the gitignored
llm_cache.jsonl are never scanned / never committed) for credential value
patterns. Key *names* (DEEPSEEK_API_KEY = os.getenv(...)) are fine; key
*values* are not.

Usage: python scripts/scan_secrets.py
Exit 0 on clean, 1 on any hit.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

_PATTERNS = [
    (re.compile(r"sk-[A-Za-z0-9_-]{16,}"), "OpenAI-style API key (sk-...)"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key id"),
    (re.compile(r"ghp_[A-Za-z0-9]{30,}"), "GitHub personal access token"),
    (re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"), "Slack token"),
    (re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"), "private key"),
    (re.compile(r"gsk_[A-Za-z0-9]{16,}"), "Groq API key (gsk_...)"),
]

# Files that are allowed to mention key names but never values.
_SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".xlsx", ".db", ".joblib", ".bin", ".pt"}


def _tracked_files() -> list[str]:
    try:
        out = subprocess.check_output(
            ["git", "ls-files"], cwd=BASE_DIR, stderr=subprocess.DEVNULL, text=True
        )
        return [ln.strip() for ln in out.splitlines() if ln.strip()]
    except Exception:
        # Fallback: walk the tree excluding obvious non-text dirs.
        files = []
        for p in BASE_DIR.rglob("*"):
            if not p.is_file():
                continue
            rel = str(p.relative_to(BASE_DIR))
            if any(part in (".git", ".venv", "__pycache__", "node_modules") for part in p.parts):
                continue
            files.append(rel)
        return files


def main() -> int:
    hits: list[str] = []
    for rel in _tracked_files():
        p = BASE_DIR / rel
        if p.suffix.lower() in _SKIP_SUFFIXES:
            continue
        if "ml/results/" in rel or "ml/external/" in rel:
            # Evaluation artifacts may contain transcripts but never credentials;
            # still scan them for sk-/token patterns to be safe.
            pass
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for line_no, line in enumerate(text.splitlines(), 1):
            for pattern, label in _PATTERNS:
                if pattern.search(line):
                    hits.append(f"{rel}:{line_no}: {label}")

    if hits:
        print("SECRET SCAN FAILED:")
        for h in hits:
            print(f"  {h}")
        return 1
    print("Secret scan clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
