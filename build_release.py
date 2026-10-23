"""Build and retest a privacy-checked source ZIP. 打包并复测经过隐私检查的源码。"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

from release_check import check_release, release_files


def build_release(root: Path, target: Path) -> str:
    findings = check_release(root)
    if findings:
        raise ValueError("Privacy check failed: " + "; ".join(findings))
    files = release_files(root)
    with zipfile.ZipFile(target, "x", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            relative = path.relative_to(root).as_posix()
            entry = zipfile.ZipInfo(f"media_recovery/{relative}", (2020, 1, 1, 0, 0, 0))
            entry.create_system = 3  # Normalized metadata, not host information. / 固定元数据，不记录本机信息。
            entry.external_attr = 0o100644 << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, path.read_bytes())
    try:
        with zipfile.ZipFile(target) as archive:
            if archive.testzip() is not None:
                raise ValueError("ZIP integrity check failed")
            with tempfile.TemporaryDirectory() as temporary:
                archive.extractall(temporary)  # Entries come only from the explicit allowlist. / 仅解压白名单条目。
                extracted = Path(temporary) / "media_recovery"
                if check_release(extracted):
                    raise ValueError("Extracted-source privacy check failed")
                completed = subprocess.run(
                    [sys.executable, "-X", "utf8", "-m", "unittest", "discover", "-s", ".", "-p", "test_*.py"],
                    cwd=extracted, capture_output=True, text=True, encoding="utf-8",
                )
                print(completed.stderr)
                if completed.returncode:
                    raise ValueError("Extracted-package tests failed")
    except BaseException:
        target.unlink(missing_ok=True)  # Remove only the artifact created above. / 仅移除本次创建的失败包。
        raise
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    with target.with_suffix(target.suffix + ".sha256").open("x", encoding="ascii") as checksum:
        checksum.write(f"{digest}  {target.name}\n")
    return digest


def main() -> None:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Build a source ZIP and test its extracted contents.")
    parser.add_argument("--output", type=Path, default=root.parent / "media_recovery_bilingual_v0.4.0.zip")
    arguments = parser.parse_args()
    digest = build_release(root, arguments.output)
    print(f"Source ZIP: {arguments.output.name}")
    print(f"Approved files: {len(release_files(root))}")
    print(f"SHA256: {digest}")
    print("No environment inventories, recovery data or machine-specific ZIP metadata included.")


if __name__ == "__main__":
    main()
