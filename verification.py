"""Run decoders in child processes so corrupt inputs cannot hang the menu."""

import html
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

from validation_worker import IMAGE_EXTENSIONS, AUDIO_EXTENSIONS, ARCHIVE_EXTENSIONS
from i18n import STATUS_KEYS, Translator, record_detail, verification_result


STATUS_LABELS = {status: Translator("zh")(key) for status, key in STATUS_KEYS.items()}
VIDEO_EXTENSIONS = {"mp4", "mov", "avi", "mkv", "webm", "flv", "3gp"}


def run_process(command, timeout, cancel_event=None, output=None):
    """Bound process lifetime/output; always kill and reap on cancel/timeout."""
    with tempfile.TemporaryFile() as capture:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                   stdout=capture if output is None else output,
                                   stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + timeout
        try:
            while process.poll() is None:
                if cancel_event is not None and cancel_event.is_set():
                    return None, "cancelled"
                if time.monotonic() > deadline:
                    return None, "timeout"
                time.sleep(0.05)
            capture.seek(0)
            return process.returncode, capture.read(32768).decode("utf-8", "replace")
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()


def verify_file(path, preview_directory, timeout=120, cancel_event=None, language="zh"):
    """Select report language without changing validation behavior. 仅改变说明语言。"""
    Translator(language)  # Reject unsupported language codes early. / 提前检查语言参数。
    checked = _verify_file(path, preview_directory, timeout, cancel_event)
    checked["detail"] = record_detail(checked, language)
    return checked


def _verify_file(path, preview_directory, timeout=120, cancel_event=None):
    extension = path.suffix.lower().lstrip(".")
    preview = preview_directory / (path.stem + ".png")
    try:
        if extension in IMAGE_EXTENSIONS | AUDIO_EXTENSIONS | ARCHIVE_EXTENSIONS:
            code, output = run_process([sys.executable, "-X", "utf8",
                                        str(Path(__file__).with_name("validation_worker.py")),
                                        str(path.resolve()), str(preview.resolve())], timeout, cancel_event)
            if code is None:
                return verification_result("UNVERIFIED", "Verification timed out or was cancelled.")
            if code != 0:
                return verification_result("UNVERIFIED", "Verification worker failed; the check did not complete.")
            checked = json.loads(output)
            if checked.get("status") not in STATUS_LABELS:
                raise ValueError("The validator returned an unknown status.")
            if checked.get("preview"):
                checked["preview"] = str(preview.relative_to(path.parent).as_posix())
            return checked
        if extension in VIDEO_EXTENSIONS:
            ffmpeg = shutil.which("ffmpeg")
            if ffmpeg is None:
                return verification_result("UNVERIFIED", "Optional FFmpeg was not found; video structure only.")
            # Restrict protocols and avoid the shell. / 限制输入协议，禁止调用 shell。
            command = [ffmpeg, "-nostdin", "-v", "error", "-xerror", "-err_detect", "explode",
                       "-protocol_whitelist", "file,pipe", "-threads", "1", "-i", str(path.resolve()),
                       "-map", "0:v?", "-map", "0:a?", "-f", "null", "-"]
            code, _ = run_process(command, timeout, cancel_event, subprocess.DEVNULL)
            if code is None:
                return verification_result("UNVERIFIED", "Video verification timed out or was cancelled before completion.")
            if code != 0:
                return verification_result("UNVERIFIED", "FFmpeg decoding failed: possible damage or unsupported codec.")
            return verification_result("OK", "FFmpeg completed decoding without a reported error; equality to the original is not proven.")
        return verification_result("UNVERIFIED", "Structure only; full content verification was not performed.")
    except (OSError, ValueError, TypeError) as error:
        return verification_result("UNVERIFIED", "Verification unavailable: {error}", error=str(error)[:300])


def annotate_record(record, directory, timeout=120, cancel_event=None, language="zh"):
    source = directory / record["file"]
    checked = verify_file(source, directory / "previews", timeout, cancel_event, language)
    checked["detail"] = record_detail(checked, language)
    # Stable status prefixes in both editions. / 两种语言使用相同的状态前缀。
    destination = directory / f"{checked['status']}__{source.name}"
    if destination.exists():
        raise FileExistsError(destination)
    source.rename(destination)
    return {**record, **checked, "file": destination.name}


def write_gallery(directory, records, language="zh"):
    """Write both languages plus preview.html for the selected one. 双语预览共用同一批文件。"""
    for selected in ("en", "zh"):
        _write_gallery_page(directory, records, selected, f"preview_{selected}.html")
    return _write_gallery_page(directory, records, language, "preview.html")


def _write_gallery_page(directory, records, language, filename):
    translate = Translator(language)
    rows = []
    for record in records:
        name = html.escape(record["file"], quote=True)
        status = record.get("status", "UNVERIFIED")
        detail = html.escape(record_detail(record, language))
        preview = record.get("preview")
        image = (f'<img loading="lazy" src="{html.escape(preview, quote=True)}" alt="{translate("Image preview")}">'
                 if preview else f'<div class="placeholder">{translate("No image preview")}</div>')
        rows.append(f'<article class="{status}">{image}<p>{translate.status(status)}</p>'
                    f'<a href="{name}">{name}</a><p>{detail}</p></article>')
    document = (f'<!doctype html><html lang="{"zh-CN" if language == "zh" else "en"}"><meta charset="utf-8">'
                '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
                'img-src \'self\'; style-src \'unsafe-inline\'">'
                f'<title>{translate("Recovered results")}</title><style>body{{font:15px sans-serif;background:#edf1f5;padding:24px}}'
                'main{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px}'
                'article{background:white;padding:16px;border-top:5px solid #d99d24;overflow-wrap:anywhere}'
                '.OK{border-color:#26945f}.DAMAGED{border-color:#d84a4a}'
                'img,.placeholder{width:100%;height:200px;object-fit:contain}.placeholder{background:#eee}'
                f'</style><h1>{translate("Recovered results")}</h1>'
                f'<nav><a href="preview_en.html">{translate("English")}</a> | '
                f'<a href="preview_zh.html">{translate("Chinese")}</a></nav><p>'
                + translate("OK = the specified decode/integrity check passed, not proof of equality to the original. DAMAGED = a content error was detected. UNVERIFIED = not fully checked. Do not execute unknown recovered files.") + '</p><main>'
                + "".join(rows) + '</main></html>')
    target = directory / filename
    temporary = directory / (filename + ".part")
    temporary.write_text(document, encoding="utf-8")
    temporary.replace(target)
    return target
