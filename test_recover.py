import contextlib
import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
import wave
import zlib

import recover


def png_chunk(kind, data):
    return (struct.pack(">I", len(data)) + kind + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))


def make_png():
    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", header)
            + png_chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00"))
            + png_chunk(b"IEND", b""))


def make_wav():
    data = io.BytesIO()
    with wave.open(data, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(b"\0\0" * 16)
    return data.getvalue()


def jpeg_segment(marker, data):
    return b"\xff" + bytes([marker]) + struct.pack(">H", len(data) + 2) + data


def make_jpeg():
    # Marker fixture, not a decodable image. / 仅标记结构样本，非可解码图片。
    exif = jpeg_segment(0xE1, b"Exif\0\0embedded thumbnail\xff\xd9")
    frame = jpeg_segment(0xC0, b"\x08\x00\x01\x00\x01\x01\x01\x11\x00")
    scan = jpeg_segment(0xDA, b"\x01\x01\x00\x00\x3f\x00")
    return b"\xff\xd8" + exif + frame + scan + b"\x17\xff\x00\x22\xff\xd0\x33\xff\xd9"


def box(kind, payload=b"", extended=False):
    if extended:
        return struct.pack(">I4sQ", 1, kind, len(payload) + 16) + payload
    return struct.pack(">I4s", len(payload) + 8, kind) + payload


def make_mp4(brand=b"isom", extended=False, tail_moov=False):
    # Box fixture, not a playable movie. / 仅 box 结构样本，非可播放视频。
    ftyp = box(b"ftyp", brand + b"\0\0\0\0" + b"isom")
    moov = box(b"moov", box(b"mvhd", b"\0" * 16) + box(b"trak"))
    mdat = box(b"mdat", b"media payload", extended=extended)
    return ftyp + (mdat + moov if tail_moov else moov + mdat)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sequence = 0

    def image(self, data):
        self.sequence += 1
        path = self.root / f"fixture_{self.sequence}.img"
        path.write_bytes(data)
        image = recover.Image(path)
        self.addCleanup(image.close)
        return image

    def candidates(self, data, chunk_size=13, limit=1024 * 1024):
        return list(recover.scan(self.image(data), recover.SIGNATURES, limit, chunk_size))

    def quiet_main(self, args):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return recover.main(args)

    def test_all_formats_and_exact_offsets(self):
        prefix = b"unallocated bytes---"
        parts = [make_png(), make_jpeg(), make_wav(), make_mp4()]
        data = prefix
        expected = []
        for media, extension in zip(parts, ("png", "jpg", "wav", "mp4")):
            expected.append((len(data), len(media), extension))
            data += media + b"\x00" * 19
        found = self.candidates(data)
        self.assertEqual([(c.offset, c.size, c.extension) for c in found], expected)

    def test_signatures_across_every_small_chunk_boundary(self):
        for chunk_size in (1, 2, 3, 4, 7, 8, 9, 16, 31, 64):
            for prefix_size in range(17):
                with self.subTest(chunk_size=chunk_size, prefix_size=prefix_size):
                    found = self.candidates(b"x" * prefix_size + make_mp4() + make_png(), chunk_size)
                    self.assertEqual([c.extension for c in found], ["mp4", "png"])
                    self.assertEqual(found[0].offset, prefix_size)

    def test_png_crc_damage_rejected(self):
        data = bytearray(make_png())
        data[-1] ^= 1
        self.assertEqual(self.candidates(data), [])

    def test_png_invalid_ihdr_rejected_even_with_valid_crc(self):
        header = struct.pack(">IIBBBBB", 0, 1, 8, 2, 0, 0, 0)
        data = (b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", header)
                + png_chunk(b"IDAT", b"x") + png_chunk(b"IEND", b""))
        self.assertEqual(self.candidates(data), [])

    def test_png_without_idat_rejected(self):
        data = make_png()
        self.assertEqual(self.candidates(data[:33] + png_chunk(b"IEND", b"")), [])

    def test_every_truncation_rejected_for_fixed_end_formats(self):
        for data in (make_png(), make_jpeg(), make_wav()):
            for length in range(len(data)):
                with self.subTest(length=length, signature=data[:4]):
                    self.assertEqual(self.candidates(data[:length]), [])

    def test_jpeg_exif_thumbnail_end_is_not_file_end(self):
        data = make_jpeg()
        found = self.candidates(data + b"trailing bytes")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].size, len(data))

    def test_jpeg_without_frame_or_scan_rejected(self):
        self.assertEqual(self.candidates(b"\xff\xd8\xff\xd9"), [])
        self.assertEqual(self.candidates(b"\xff\xd8\xff\xe0\0\x01\xff\xd9"), [])

    def test_wav_odd_chunk_padding(self):
        original = make_wav()
        body = b"WAVE" + b"JUNK" + struct.pack("<I", 3) + b"abc\0" + original[12:]
        data = b"RIFF" + struct.pack("<I", len(body)) + body
        self.assertEqual(self.candidates(data)[0].size, len(data))

    def test_riff_not_wave_rejected(self):
        data = make_wav().replace(b"WAVE", b"AVI ", 1)
        self.assertEqual(self.candidates(data), [])

    def test_wav_missing_fmt_rejected(self):
        data = make_wav().replace(b"fmt ", b"JUNK", 1)
        self.assertEqual(self.candidates(data), [])

    def test_mp4_extended_size_and_tail_moov(self):
        for extended in (False, True):
            for tail in (False, True):
                data = make_mp4(extended=extended, tail_moov=tail)
                found = self.candidates(data)
                self.assertEqual(found[0].size, len(data))
                self.assertEqual(found[0].validation, "box_structure_estimated_boundary")

    def test_mp4_brand_extensions(self):
        for brand, extension in ((b"qt  ", "mov"), (b"M4A ", "m4a"), (b"mp42", "mp4")):
            self.assertEqual(self.candidates(make_mp4(brand))[0].extension, extension)

    def test_mp4_missing_moov_or_mdat_rejected(self):
        data = make_mp4()
        self.assertEqual(self.candidates(data.replace(b"moov", b"free", 1)), [])
        self.assertEqual(self.candidates(data.replace(b"mdat", b"free", 1)), [])

    def test_mp4_invalid_moov_child_rejected(self):
        data = make_mp4().replace(b"trak", b"junk", 1)
        self.assertEqual(self.candidates(data), [])

    def test_mp4_size_zero_mdat_rejected(self):
        data = make_mp4()
        index = data.index(b"mdat") - 4
        data = data[:index] + b"\0\0\0\0" + data[index + 4:]
        self.assertEqual(self.candidates(data), [])

    def test_mp4_unknown_brand_rejected(self):
        data = make_mp4(b"zzzz").replace(b"isom", b"zzzz")
        self.assertEqual(self.candidates(data), [])

    def test_file_size_limit(self):
        for data in (make_png(), make_jpeg(), make_wav(), make_mp4()):
            self.assertEqual(self.candidates(data, limit=len(data) - 1), [])
            self.assertEqual(len(self.candidates(data, limit=len(data))), 1)

    def test_embedded_candidate_not_exported_twice(self):
        image_data = make_png()
        body = b"WAVE" + b"JUNK" + struct.pack("<I", len(image_data)) + image_data
        body += b"\0" * (len(image_data) & 1) + make_wav()[12:]
        data = b"RIFF" + struct.pack("<I", len(body)) + body
        self.assertEqual([c.extension for c in self.candidates(data)], ["wav"])

    def test_export_hash_contents_and_no_overwrite(self):
        data = make_png()
        image = self.image(b"prefix" + data)
        candidate = next(recover.scan(image, ("png",), 1024))
        record = recover.export(image, candidate, self.root)
        target = self.root / record["file"]
        self.assertEqual(target.read_bytes(), data)
        self.assertEqual(record["sha256"], hashlib.sha256(data).hexdigest())
        with self.assertRaises(FileExistsError):
            recover.export(image, candidate, self.root)
        self.assertEqual(target.read_bytes(), data)

    def test_dry_run_does_not_write_or_change_source(self):
        path = self.root / "source.img"
        path.write_bytes(make_png())
        before = path.read_bytes()
        self.assertEqual(self.quiet_main([str(path), "--dry-run"]), 0)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(list(self.root.iterdir()), [path])

    def test_cli_exports_and_manifest(self):
        source = self.root / "source.img"
        source.write_bytes(b"junk" + make_png() + make_wav())
        before = source.read_bytes()
        output = self.root / "output"
        self.assertEqual(self.quiet_main([str(source), "-o", str(output)]), 0)
        sessions = list(output.iterdir())
        self.assertEqual(len(sessions), 1)
        manifest = [json.loads(line) for line in
                    (sessions[0] / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([entry["event"] for entry in manifest],
                         ["start", "recovered", "recovered", "complete"])
        self.assertEqual(manifest[-1]["files"], 2)
        self.assertEqual(source.read_bytes(), before)

    def test_new_session_instead_of_overwriting(self):
        source = self.root / "source.img"
        source.write_bytes(make_png())
        output = self.root / "output"
        for _ in range(2):
            self.assertEqual(self.quiet_main([str(source), "-o", str(output)]), 0)
        self.assertEqual(len(list(output.iterdir())), 2)

    def test_missing_input_does_not_create_output(self):
        output = self.root / "output"
        self.assertEqual(self.quiet_main([str(self.root / "missing.img"), "-o", str(output)]), 1)
        self.assertFalse(output.exists())

    def test_directory_source_rejected(self):
        with self.assertRaises(ValueError):
            recover.Image(self.root)

    def test_empty_image(self):
        self.assertEqual(self.candidates(b""), [])

    def test_types_filter(self):
        image = self.image(make_png() + make_wav())
        self.assertEqual([c.extension for c in recover.scan(image, ("wav",), 1024)], ["wav"])


if __name__ == "__main__":
    unittest.main()
