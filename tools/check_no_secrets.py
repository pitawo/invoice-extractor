"""リポジトリ内に API キーらしい文字列が無いことの検査。python tools/check_no_secrets.py

  - キーの形の文字列（sk-…、AIza…、key = "長い文字列" の代入）
  - .gitignore が .env を除外していること
  - .env が git 管理下に入っていないこと
"""
import re
import subprocess
import sys
from pathlib import Path

PATTERNS = [
    re.compile(r"sk-(?:ant-)?[A-Za-z0-9_\-]{20,}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{30,}"),
    re.compile(r"(?i)(?:api[_-]?key|secret|token)\s*[:=]\s*[\"'][A-Za-z0-9_\-]{16,}[\"']"),
]
SKIP_DIRS = {".git", "out", "__pycache__", "node_modules"}
SKIP_SUFFIX = {".png", ".pdf", ".jpg", ".webp"}


def scan(root):
    root = Path(root)
    hits = []
    for f in root.rglob("*"):
        if not f.is_file() or SKIP_DIRS & set(f.relative_to(root).parts) or f.suffix in SKIP_SUFFIX:
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if any(p.search(line) for p in PATTERNS):
                hits.append(f"{f.relative_to(root)}:{n}")
    gi = root / ".gitignore"
    if not gi.exists() or ".env" not in gi.read_text(encoding="utf-8").split():
        hits.append(".gitignore に .env が無い")
    return hits


def tracked_env_files(root):
    try:
        out = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True).stdout
    except Exception:
        return []
    return [p for p in out.splitlines() if Path(p).name == ".env" or (Path(p).name.startswith(".env.") and p != ".env.example")]


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    problems = scan(root) + [f"git 管理下に {p}" for p in tracked_env_files(root)]
    print("\n".join(problems) if problems else "問題なし")
    sys.exit(1 if problems else 0)
