import array
import contextlib
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

import extra_formats
import flac_carver
import recover
import validation_worker
import verification
from test_recover import box, make_jpeg, make_png, make_wav


def make_flac(subframe_kind="constant", channels=1):
    samples = 16
    pcm = b"\0\0" * samples * channels
    header = b"\xff\xf8\x69" + bytes([((channels - 1) << 4) | 8]) + b"\0\x0f"
    header += bytes([flac_carver.crc8(header)])
    if subframe_kind == "constant":
        subframe = b"\0\0\0"
    elif subframe_kind == "verbatim":
        subframe = b"\x02" + b"\0\0" * samples
    else:
        # Fixed predictor zero; Rice parameter zero. / 零阶固定预测，Rice 参数为零。
        bits = ("00010000" + "000000" + "0000" + "1" * samples) * channels
        bits += "0" * ((-len(bits)) % 8)
        subframe = int(bits, 2).to_bytes(len(bits) // 8, "big")
    frame = header + (subframe if subframe_kind == "fixed" else subframe * channels)
    frame += flac_carver.crc16(frame).to_bytes(2, "big")
    packed = (44100 << 44) | ((channels - 1) << 41) | (15 << 36) | samples
    stream_info = (struct.pack(">HH", samples, samples) + len(frame).to_bytes(3, "big") * 2
                   + packed.to_bytes(8, "big") + hashlib.md5(pcm).digest())
    return b"fLaC\x80\0\0\x22" + stream_info + frame


def make_mp3():
    return (b"\xff\xfb\x90\x64" + b"\0" * 413) * 4


def make_aac():
    length = 15
    header = bytes([255, 241, 80, 128 | (length >> 11), (length >> 3) & 255,
                    ((length & 7) << 5) | 31, 252])
    return (header + b"\0" * (length - 7)) * 4


def make_ogg(payload=b"OpusHead" + b"\0" * 12):
    header = b"OggS\0\x06" + b"\0" * 8 + struct.pack("<III", 1234, 0, 0) + b"\x01"
    page = header + bytes([len(payload)]) + payload
    checksum = extra_formats.ogg_crc(page)
    return page[:22] + struct.pack("<I", checksum) + page[26:]


def make_zip(entries=None):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in (entries or {"example.txt": b"hello recovery"}).items():
            archive.writestr(name, data)
    return buffer.getvalue()


class ExtendedTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.sequence = 0

    def carve(self, data, types=None, chunk_size=17, limit=1024 * 1024):
        self.sequence += 1
        path = self.root / f"image_{self.sequence}.img"
        path.write_bytes(data)
        image = recover.Image(path)
        try:
            return list(recover.scan(image, types or recover.PUBLIC_TYPES, limit, chunk_size))
        finally:
            image.close()

    def assert_exact(self, data, extension, types=None):
        found = self.carve(b"prefix" + data + b"\0" * 32, types)
        self.assertEqual([(entry.offset, entry.size, entry.extension) for entry in found],
                         [(6, len(data), extension)])

    def test_flac_subframes(self):
        for kind in ("constant", "verbatim", "fixed"):
            for channels in (1, 2):
                with self.subTest(kind=kind, channels=channels):
                    self.assert_exact(make_flac(kind, channels), "flac")

    def test_flac_crc_and_truncation(self):
        data = make_flac()
        self.assertEqual(self.carve(data[:-1]), [])
        damaged = data[:-1] + bytes([data[-1] ^ 1])
        self.assertEqual(self.carve(damaged), [])

    def test_independent_crc_reference_values(self):
        self.assertEqual(flac_carver.crc8(b"123456789"), 0xF4)
        self.assertEqual(flac_carver.crc16(b"123456789"), 0xFEE8)
        self.assertEqual(extra_formats.ogg_crc(b"123456789"), 0x89A1897F)

    def test_raw_mp3_and_id3(self):
        self.assert_exact(make_mp3(), "mp3")
        self.assert_exact(b"ID3\x04\0\0\0\0\0\0" + make_mp3(), "mp3")

    def test_mp3_requires_multiple_frames(self):
        self.assertEqual(self.carve(make_mp3()[:417], ("mp3",)), [])

    def test_aac_frames(self):
        self.assert_exact(make_aac(), "aac")

    def test_amr_frames(self):
        data = b"#!AMR\n" + (b"\x04" + b"\0" * 12) * 4
        found = self.carve(data + b"\xff" * 16)
        self.assertEqual([(entry.offset, entry.size, entry.extension) for entry in found],
                         [(0, len(data), "amr")])

    def test_ogg_opus_and_vorbis(self):
        self.assert_exact(make_ogg(), "opus")
        self.assert_exact(make_ogg(b"\x01vorbis" + b"\0" * 20), "ogg")

    def test_ogg_crc_and_eos(self):
        data = make_ogg()
        self.assertEqual(self.carve(data[:-1] + b"x"), [])
        self.assertEqual(self.carve(data[:-1]), [])

    def test_au(self):
        self.assert_exact(b".snd" + struct.pack(">IIIII", 24, 32, 3, 8000, 1) + b"\0" * 32, "au")

    def test_aiff(self):
        body = b"AIFF" + b"COMM" + struct.pack(">I", 18) + b"\0" * 18
        body += b"SSND" + struct.pack(">I", 40) + b"\0" * 40
        self.assert_exact(b"FORM" + struct.pack(">I", len(body)) + body, "aiff")

    def test_avi_and_riff_filter(self):
        body = b"AVI " + b"LIST" + struct.pack("<I", 4) + b"hdrl"
        data = b"RIFF" + struct.pack("<I", len(body)) + body
        self.assert_exact(data, "avi", ("avi",))
        self.assertEqual(self.carve(data, ("webp",)), [])

    def test_iso_image_brands_and_3gp(self):
        for brand, extension in ((b"heic", "heic"), (b"avif", "avif")):
            data = box(b"ftyp", brand + b"\0" * 4 + brand) + box(b"meta", b"\0" * 4) + box(b"mdat", b"data")
            self.assert_exact(data, extension)
        data = (box(b"ftyp", b"3gp6" + b"\0" * 4 + b"3gp6")
                + box(b"moov", box(b"mvhd") + box(b"trak")) + box(b"mdat", b"data"))
        self.assert_exact(data, "3gp")

    def test_finite_webm(self):
        ebml = b"\x1aE\xdf\xa3\x87\x42\x82\x84webm"
        data = ebml + b"\x18\x53\x80\x67\x84data"
        self.assert_exact(data, "webm")
        self.assertEqual(self.carve(ebml + b"\x18\x53\x80\x67\xffdata"), [])

    def test_flv(self):
        tag = b"\x08\0\0\x03" + b"\0" * 7 + b"abc" + struct.pack(">I", 14)
        data = b"FLV\x01\x04\0\0\0\x09" + b"\0" * 4 + tag
        self.assert_exact(data, "flv")

    def test_pdf(self):
        data = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\nstartxref\n9\n%%EOF\n"
        self.assert_exact(data, "pdf")

    def test_zip_and_office(self):
        self.assert_exact(make_zip(), "zip")
        self.assert_exact(make_zip({"[Content_Types].xml": b"xml", "word/document.xml": b"document"}), "docx")
        self.assert_exact(make_zip({"[Content_Types].xml": b"xml", "xl/workbook.xml": b"sheets"}), "xlsx")
        self.assert_exact(make_zip({"META-INF/container.xml": b"xml"}), "epub")

    def test_zip_crc_validation_and_safe_paths(self):
        path = self.root / "archive.zip"
        path.write_bytes(make_zip({"../../do_not_extract.txt": b"payload"}))
        checked = verification.verify_file(path, self.root / "previews")
        self.assertEqual(checked["status"], "OK")
        self.assertFalse((self.root / "do_not_extract.txt").exists())

    def test_real_images_carve_decode_preview(self):
        from PIL import Image as PillowImage
        formats = [("GIF", "gif", {}), ("BMP", "bmp", {}), ("ICO", "ico", {}),
                   ("TIFF", "tif", {}), ("TIFF", "tif", {"compression": "tiff_lzw"}),
                   ("WEBP", "webp", {}), ("JPEG", "jpg", {"progressive": True})]
        for file_format, extension, options in formats:
            with self.subTest(file_format=file_format, options=options):
                buffer = io.BytesIO()
                PillowImage.new("RGB", (32, 32), (80, 100, 120)).save(buffer, format=file_format, **options)
                data = buffer.getvalue()
                self.assert_exact(data, extension)
                path = self.root / f"sample_{file_format}.{extension}"
                path.write_bytes(data)
                checked = verification.verify_file(path, self.root / "previews")
                self.assertEqual(checked["status"], "OK", checked)
                self.assertTrue((self.root / checked["preview"]).is_file())

    def test_animated_gif_all_frames(self):
        from PIL import Image as PillowImage
        buffer = io.BytesIO()
        frames = [PillowImage.new("RGB", (16, 16), color) for color in ("red", "green", "blue")]
        frames[0].save(buffer, format="GIF", save_all=True, append_images=frames[1:], duration=50, loop=0)
        self.assert_exact(buffer.getvalue(), "gif")
        path = self.root / "animated.gif"
        path.write_bytes(buffer.getvalue())
        checked = verification.verify_file(path, self.root / "previews")
        self.assertEqual(checked["status"], "OK")
        self.assertIn("3", checked["detail"])

    def test_wave_verified_without_external_audio_dependencies(self):
        path = self.root / "audio.wav"
        path.write_bytes(make_wav())
        with patch.dict(sys.modules, {"miniaudio": None}):
            checked = validation_worker.check_audio(path)
        self.assertEqual(checked["status"], "OK")
        self.assertIn("Python wave", checked["detail"])

    def test_truncated_wave_damaged(self):
        path = self.root / "audio.wav"
        path.write_bytes(make_wav()[:-2])
        self.assertEqual(validation_worker.check_audio(path)["status"], "DAMAGED")

    def test_audio_decoder_rejection_not_marked_ok(self):
        path = self.root / "audio.mp3"
        path.write_bytes(make_mp3())
        with patch("validation_worker.miniaudio.get_file_info", side_effect=ValueError("Unsupported codec")):
            self.assertEqual(validation_worker.check_audio(path)["status"], "UNVERIFIED")

    def test_unsupported_audio_never_invokes_ffmpeg(self):
        path = self.root / "audio.aac"
        path.write_bytes(make_aac())
        with patch("validation_worker.miniaudio.get_file_info", side_effect=AssertionError("AAC has no integrated decoder")):
            checked = validation_worker.check_audio(path)
        self.assertEqual(checked["status"], "UNVERIFIED")

    def test_native_audio_library_real_decode(self):
        for extension, data in (("wav", make_wav()), ("flac", make_flac()), ("flac", make_flac("fixed", 2))):
            path = self.root / f"audio.{extension}"
            path.write_bytes(data)
            checked = validation_worker.check_audio(path)
            self.assertEqual(checked["status"], "OK", checked)

    def test_validation_timeout_and_cancel(self):
        code, reason = verification.run_process([sys.executable, "-c", "import time; time.sleep(10)"], 0.1)
        self.assertIsNone(code)
        self.assertEqual(reason, "timeout")
        event = threading.Event()
        event.set()
        code, reason = verification.run_process([sys.executable, "-c", "import time; time.sleep(10)"], 5, event)
        self.assertIsNone(code)
        self.assertEqual(reason, "cancelled")

    def test_cancelled_scan_does_not_change_source(self):
        path = self.root / "cancel.img"
        path.write_bytes(make_png())
        event = threading.Event()
        event.set()
        with contextlib.redirect_stdout(io.StringIO()):
            code = recover.main([str(path), "--dry-run"], cancel_event=event)
        self.assertEqual(code, 130)
        self.assertEqual(path.read_bytes(), make_png())

    def test_video_never_launches_external_decoder(self):
        path = self.root / "video.mp4"
        path.write_bytes(b"not video")
        with patch("verification.run_process", side_effect=AssertionError("No external video programs")):
            self.assertEqual(verification.verify_file(path, self.root / "previews")["status"], "UNVERIFIED")

    def test_gallery_escapes_names(self):
        record = {"file": '<script>name.zip', "status": "UNVERIFIED", "detail": '<unsafe>'}
        gallery = verification.write_gallery(self.root, [record]).read_text(encoding="utf-8")
        self.assertNotIn("<script>", gallery)
        self.assertIn("&lt;unsafe&gt;", gallery)

    def test_end_to_end_named_status_and_gallery(self):
        source = self.root / "source.img"
        source.write_bytes(make_png() + make_wav() + make_zip() + make_jpeg())
        output = self.root / "output"
        with contextlib.redirect_stdout(io.StringIO()):
            code = recover.main([str(source), "-o", str(output)])
        self.assertEqual(code, 0)
        directory = next(output.iterdir())
        entries = [json.loads(line) for line in (directory / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
        records = [entry for entry in entries if entry["event"] == "recovered"]
        self.assertEqual(len(records), 4)
        self.assertTrue((directory / "preview.html").is_file())
        for record in records:
            self.assertTrue(record["file"].startswith(record["status"] + "__"))
            self.assertTrue((directory / record["file"]).is_file())
            self.assertEqual(hashlib.sha256((directory / record["file"]).read_bytes()).hexdigest(), record["sha256"])

    def test_no_verify_marks_unverified(self):
        source = self.root / "source.img"
        source.write_bytes(make_wav())
        output = self.root / "output"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(recover.main([str(source), "-o", str(output), "--no-verify"]), 0)
        directory = next(output.iterdir())
        self.assertEqual(len(list(directory.glob("UNVERIFIED__*.wav"))), 1)

    def test_no_crash_on_malformed_headers(self):
        import random
        randomizer = random.Random(42)
        for kind, (signature, _) in recover.SIGNATURES.items():
            for length in (0, 1, 5, 32, 100, 500):
                self.carve(signature + randomizer.randbytes(length), (kind,), chunk_size=7)


if __name__ == "__main__":
    unittest.main()
