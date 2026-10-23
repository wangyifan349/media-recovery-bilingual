"""Allowlist source releases and check common leaks. 白名单检查源码包和常见泄露。"""

from __future__ import annotations

from pathlib import Path
import re


ROOT_FILES = {
    "app.py", "extra_formats.py", "flac_carver.py", "i18n.py", "recover.py",
    "recovery_gui.py", "release_check.py", "start.py", "start_en.py", "start_zh.py",
    "validation_worker.py", "verification.py", "test_extended.py", "test_i18n.py",
    "test_recover.py", "README.md", "README.zh-CN.md", "DEVELOPMENT.md",
    "requirements.txt", ".gitignore", ".gitattributes", ".editorconfig",
}
RELATIVE_FILES = ROOT_FILES | {".github/workflows/tests.yml"}
LEAK_PATTERNS = {
    "personal home path": re.compile(r"[A-Za-z]:[\\/]Users[\\/][^\s]+|/(?:home|Users)/[^/\s]+/", re.IGNORECASE),
    "GitHub token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "AWS key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
}


def release_files(root: Path) -> list[Path]:
    """Explicit inputs only: never recursively archive the workspace. 绝不递归打包工作区。"""
    paths = [root / relative for relative in sorted(RELATIVE_FILES)]
    missing = [path.name for path in paths if not path.is_file() or path.is_symlink()]
    if missing:
        raise ValueError("Missing or unsafe release inputs: " + ", ".join(missing))
    return paths


def check_release(root: Path) -> list[str]:
    findings = []
    for path in release_files(root):
        content = path.read_text(encoding="utf-8")
        for category, pattern in LEAK_PATTERNS.items():
            if pattern.search(content):
                # Never echo a suspected secret or machine path. / 不回显疑似密钥或本机路径。
                findings.append(f"{path.relative_to(root).as_posix()}: {category}")
    return findings


if __name__ == "__main__":
    findings = check_release(Path(__file__).resolve().parent)
    for finding in findings:
        print(finding)
    print("Privacy pattern check: FAILED" if findings else "Privacy pattern check: PASS (not a guarantee against every possible secret)")
    raise SystemExit(bool(findings))
