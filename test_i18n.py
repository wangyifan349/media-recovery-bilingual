"""Language parity and presentation isolation tests. 语言一致性与展示隔离测试。"""

import json
import ast
import os
from pathlib import Path
import re
from string import Formatter
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from i18n import STATUS_KEYS, SUPPORTED_LANGUAGES, Translator, ZH_MESSAGES, verification_result
import recover
from test_recover import make_png, make_wav
import verification


HAN_CHARACTERS = re.compile(r"[\u3400-\u9fff]")


class TranslationTests(unittest.TestCase):
    def test_catalog_placeholders_are_identical(self):
        formatter = Formatter()
        for english, chinese in ZH_MESSAGES.items():
            with self.subTest(message=english):
                english_fields = [(name, spec, conversion) for _, name, spec, conversion in formatter.parse(english) if name is not None]
                chinese_fields = [(name, spec, conversion) for _, name, spec, conversion in formatter.parse(chinese) if name is not None]
                self.assertEqual(sorted(english_fields), sorted(chinese_fields))
                self.assertFalse(HAN_CHARACTERS.search(english))
                self.assertTrue(HAN_CHARACTERS.search(chinese))

    def test_translator_rejects_unknown_language(self):
        with self.assertRaises(ValueError):
            Translator("unknown")

    def test_bilingual_results_keep_stable_status_codes(self):
        for status in STATUS_KEYS:
            checked = verification_result(status, "Structure only; full content verification was not performed.")
            self.assertEqual(checked["status"], status)
            self.assertFalse(HAN_CHARACTERS.search(checked["detail_en"]))
            self.assertTrue(HAN_CHARACTERS.search(checked["detail_zh"]))

    def test_cli_help_is_english(self):
        output = subprocess.run([sys.executable, "-X", "utf8", str(Path(recover.__file__)),
                                 "--language", "en", "--help"], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(output.returncode, 0)
        self.assertIn("Read-only carving", output.stdout)
        self.assertFalse(HAN_CHARACTERS.search(output.stdout))

    def test_recovery_bytes_and_statuses_match_between_languages(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.img"
            source.write_bytes(make_png() + make_wav())
            before = source.read_bytes()
            results = {}
            for language in SUPPORTED_LANGUAGES:
                logs = []
                self.assertEqual(recover.main([str(source), "-o", str(root / language), "--language", language], log=logs.append), 0)
                if language == "en":
                    self.assertFalse(HAN_CHARACTERS.search("\n".join(logs)))
                folder = next((root / language).iterdir())
                entries = [json.loads(line) for line in (folder / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
                records = [entry for entry in entries if entry["event"] == "recovered"]
                results[language] = [(record["file"], record["status"], record["sha256"], record["offset"], record["size"]) for record in records]
                for record in records:
                    self.assertEqual(record["detail"], record[f"detail_{language}"])
                for gallery_language in SUPPORTED_LANGUAGES:
                    page = (folder / f"preview_{gallery_language}.html").read_text(encoding="utf-8")
                    if gallery_language == "en":
                        self.assertFalse(HAN_CHARACTERS.search(page))
                    else:
                        self.assertTrue(HAN_CHARACTERS.search(page))
                self.assertEqual((folder / "preview.html").read_bytes(), (folder / f"preview_{language}.html").read_bytes())
            self.assertEqual(results["en"], results["zh"])
            self.assertEqual(source.read_bytes(), before)

    def test_verification_fallback_uses_selected_language(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "video.mp4"
            path.write_bytes(b"structure fixture")
            with patch("verification.run_process", side_effect=AssertionError("Video must not launch programs")):
                checked = verification.verify_file(path, path.parent / "previews", language="en")
            self.assertEqual(checked["detail"], checked["detail_en"])
            self.assertFalse(HAN_CHARACTERS.search(checked["detail"]))

    def test_library_rejects_empty_format_set(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "empty.img"
            path.write_bytes(b"")
            image = recover.Image(path)
            try:
                with self.assertRaises(ValueError):
                    list(recover.scan(image, (), 1024))
            finally:
                image.close()

    def test_release_allowlist_passes_privacy_patterns(self):
        from release_check import check_release, release_files
        root = Path(__file__).resolve().parent
        self.assertEqual(check_release(root), [])
        self.assertTrue(all("__pycache__" not in path.parts and ".git" not in path.parts for path in release_files(root)))

    def test_readme_selectors_match_both_editions(self):
        root = Path(__file__).resolve().parent
        for filename in ("README.md", "README.zh-CN.md"):
            document = (root / filename).read_text(encoding="utf-8")
            selectors = re.findall(r"^\| `([a-z0-9]+)` \|", document.split("## ✅", 1)[0], re.MULTILINE)
            self.assertEqual(selectors, list(recover.PUBLIC_TYPES))

    def test_required_libraries_are_not_guarded_by_importerror(self):
        root = Path(__file__).resolve().parent
        for filename in ("validation_worker.py", "verification.py", "app.py"):
            tree = ast.parse((root / filename).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ExceptHandler) and node.type is not None:
                    self.assertNotIn("ImportError", ast.unparse(node.type))

    def test_bilingual_author_and_license_footer(self):
        root = Path(__file__).resolve().parent
        for filename in ("README.md", "README.zh-CN.md"):
            last_line = (root / filename).read_text(encoding="utf-8").strip().splitlines()[-1]
            self.assertIn("王一帆", last_line)
            self.assertIn("GPL-3.0-only", last_line)
        license_text = (root / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("Version 3, 29 June 2007", license_text)
        self.assertIn("END OF TERMS AND CONDITIONS", license_text)

    def test_media_worker_only_launches_python(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "image.png"
            path.write_bytes(make_png())
            checked = verification_result("OK", "Pillow decoded all {frames} frames/pages.", frames=1)
            with patch("verification.run_process", return_value=(0, json.dumps(checked))) as worker:
                self.assertEqual(verification.verify_file(path, path.parent / "previews")["status"], "OK")
            self.assertEqual(worker.call_args.args[0][0], sys.executable)
            self.assertTrue(worker.call_args.args[0][3].endswith("validation_worker.py"))


class GuiLanguageTests(unittest.TestCase):
    def setUp(self):
        if os.environ.get("GITHUB_ACTIONS") == "true":
            self.skipTest("GUI checks require an interactive display; CI exercises CLI and core logic")
        try:
            import tkinter as tk
            self.root = tk.Tk()
            self.root.withdraw()
        except Exception as error:
            self.skipTest(f"Tk/display unavailable: {error}")
        self.addCleanup(self.root.destroy)

    def test_english_widgets_menus_and_switching(self):
        import tkinter as tk
        from app import RecoveryApp

        application = RecoveryApp(self.root, "en")
        self.root.update()

        def check_widgets(widget):
            for option in ("text", "label"):
                try:
                    value = str(widget.cget(option))
                except tk.TclError:
                    continue
                self.assertFalse(HAN_CHARACTERS.search(value), value)
            if isinstance(widget, tk.Menu):
                end = widget.index("end")
                for index in range((end if end is not None else -1) + 1):
                    if widget.type(index) not in ("separator", "tearoff"):
                        self.assertFalse(HAN_CHARACTERS.search(widget.entrycget(index, "label")))
            for child in widget.winfo_children():
                check_widgets(child)

        check_widgets(self.root)
        application.records.append({"file": "OK__example.wav", "size": 100, "status": "OK",
                                    "detail_en": "English check", "detail_zh": "中文校验"})
        application.source_path.set("example.img")
        application.change_language("zh")
        self.root.update()
        self.assertTrue(HAN_CHARACTERS.search(self.root.title()))
        self.assertEqual(application.source_path.get(), "example.img")
        self.assertEqual(len(application.table.get_children()), 1)
        application.change_language("en")
        self.root.update()
        check_widgets(self.root)
        self.assertEqual(len(application.records), 1)
        self.assertEqual(application.font_size, 14)
        application.change_font_size(2)
        self.assertEqual(application.font_size, 16)
        application.change_language("zh")
        self.assertEqual(application.font_size, 16)
        application.change_font_size()
        self.assertEqual(application.font_size, 14)


if __name__ == "__main__":
    unittest.main()
