"""Read-only contiguous carving from a raw image. 从原始镜像中只读提取连续媒体。"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import sys
import uuid
import zlib

from extra_formats import EXTRA_SIGNATURES, EXTRACTORS, mp3_frame
from verification import annotate_record, write_gallery
from i18n import ZH_MESSAGES, Translator, verification_result


MIB = 1024 * 1024
BLOCK = 1024 * 1024
SIGNATURES = {
    "jpg": (b"\xff\xd8\xff", 0),
    "png": (b"\x89PNG\r\n\x1a\n", 0),
    "wav": (b"RIFF", 0),
    "mp4": (b"ftyp", -4),
}
SIGNATURES.update(EXTRA_SIGNATURES)
FORMAT_GROUPS = {
    "Images": ("jpg", "png", "gif", "bmp", "ico", "tif", "webp"),
    "Audio": ("wav", "mp3", "flac", "aac", "amr", "ogg", "aiff", "au"),
    "Video / HEIC / AVIF": ("mp4", "avi", "mkv", "flv"),
    "Documents / archives": ("pdf", "zip"),
}
PUBLIC_TYPES = tuple(kind for group in FORMAT_GROUPS.values() for kind in group)


class RecoveryCancelled(Exception):
    """Cooperative cancellation; completed exports remain. 协作式取消，保留完整导出。"""


@dataclass(frozen=True)
class Candidate:
    offset: int
    size: int
    extension: str
    validation: str


class Image:
    def __init__(self, path: Path, cancel_event=None):
        # Regular files only; never write to the source. / 仅普通文件，绝不写入源文件。
        if not path.is_file():
            raise ValueError("Input must be a regular image file; disk device paths are not supported.")
        self.file = path.open("rb")
        info = os.fstat(self.file.fileno())
        if not stat.S_ISREG(info.st_mode):
            self.file.close()
            raise ValueError("Input is not a regular file.")
        self.size = info.st_size
        self.cancel_event = cancel_event

    def read(self, offset: int, length: int) -> bytes:
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise RecoveryCancelled()
        if offset < 0 or length < 0 or offset >= self.size:
            return b""
        self.file.seek(offset)
        return self.file.read(min(length, self.size - offset))

    def close(self):
        self.file.close()


def png(image: Image, start: int, limit: int) -> Candidate | None:
    end = min(image.size, start + limit)
    pos = start + 8
    seen_data = False
    first = True
    while pos + 12 <= end:
        header = image.read(pos, 8)
        length, kind = struct.unpack(">I4s", header)
        if length > 0x7FFFFFFF or pos + 12 + length > end:
            return None
        if not all(65 <= c <= 90 or 97 <= c <= 122 for c in kind):
            return None
        if first:
            if kind != b"IHDR" or length != 13:
                return None
            width, height, depth, color, compression, filtering, interlace = (
                struct.unpack(">IIBBBBB", image.read(pos + 8, 13))
            )
            depths = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8),
                      4: (8, 16), 6: (8, 16)}
            if (not width or not height or depth not in depths.get(color, ())
                    or compression or filtering or interlace not in (0, 1)):
                return None
            first = False
        elif kind == b"IHDR":
            return None
        checksum = zlib.crc32(kind)
        cursor = pos + 8
        remaining = length
        while remaining:
            data = image.read(cursor, min(BLOCK, remaining))
            if not data:
                return None
            checksum = zlib.crc32(data, checksum)
            cursor += len(data)
            remaining -= len(data)
        expected = struct.unpack(">I", image.read(cursor, 4))[0]
        if checksum & 0xFFFFFFFF != expected:
            return None
        pos += length + 12
        seen_data |= kind == b"IDAT"
        if kind == b"IEND":
            if length or not seen_data:
                return None
            return Candidate(start, pos - start, "png", "chunk_structure_and_crc")
    return None


def jpeg(image: Image, start: int, limit: int) -> Candidate | None:
    end = min(image.size, start + limit)
    pos = start + 2
    entropy = False
    seen_frame = seen_scan = False
    while pos < end:
        if entropy:
            # FF00 is a stuffed data byte, not a marker. / FF00 是转义数据而非标记。
            while pos < end:
                data = image.read(pos, min(65536, end - pos))
                index = data.find(b"\xff")
                if index >= 0:
                    pos += index
                    break
                pos += len(data)
        if pos >= end or image.read(pos, 1) != b"\xff":
            return None
        while pos < end and image.read(pos, 1) == b"\xff":
            pos += 1
        if pos >= end:
            return None
        marker = image.read(pos, 1)[0]
        pos += 1
        if marker == 0 or 0xD0 <= marker <= 0xD7:
            if not entropy:
                return None
            continue
        if marker == 0xD9:
            if seen_frame and seen_scan:
                return Candidate(start, pos - start, "jpg", "jpeg_marker_structure")
            return None
        if marker == 0x01:
            continue
        if marker == 0xD8 or marker < 0xC0:
            return None
        if pos + 2 > end:
            return None
        length = int.from_bytes(image.read(pos, 2), "big")
        if length < 2 or pos + length > end:
            return None
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                      0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            if length < 8:
                return None
            frame = image.read(pos + 2, 6)
            if (not int.from_bytes(frame[1:3], "big")
                    or not int.from_bytes(frame[3:5], "big")
                    or not frame[5] or length != 8 + 3 * frame[5]):
                return None
            seen_frame = True
        if marker == 0xDA:
            if not seen_frame or length < 6:
                return None
            components = image.read(pos + 2, 1)[0]
            if not components or length != 6 + 2 * components:
                return None
            seen_scan = True
        entropy = marker == 0xDA
        pos += length
    return None


def wav(image: Image, start: int, limit: int) -> Candidate | None:
    header = image.read(start, 12)
    if len(header) != 12 or header[8:12] != b"WAVE":
        return None
    size = int.from_bytes(header[4:8], "little") + 8
    if size < 12 or size > limit or start + size > image.size:
        return None
    pos, end = start + 12, start + size
    seen_fmt = seen_data = False
    while pos + 8 <= end:
        chunk = image.read(pos, 8)
        length = int.from_bytes(chunk[4:8], "little")
        next_pos = pos + 8 + length + (length & 1)
        if next_pos > end:
            return None
        if chunk[:4] == b"fmt ":
            if length < 16:
                return None
            fmt = image.read(pos + 8, 16)
            codec, channels, rate, _, alignment, _ = struct.unpack("<HHIIHH", fmt)
            if not codec or not channels or not rate or not alignment:
                return None
            seen_fmt = True
        if chunk[:4] == b"data":
            seen_data = True
        pos = next_pos
    if pos != end or not seen_fmt or not seen_data:
        return None
    return Candidate(start, size, "wav", "riff_chunk_structure")


def box_header(image: Image, pos: int, end: int):
    if pos + 8 > end:
        return None
    data = image.read(pos, 8)
    size, kind = struct.unpack(">I4s", data)
    header_size = 8
    if size == 1:
        if pos + 16 > end:
            return None
        size = int.from_bytes(image.read(pos + 8, 8), "big")
        header_size = 16
    # Image EOF is not the original file EOF. / 镜像末尾并非原文件末尾，拒绝 size=0。
    if size < header_size or pos + size > end:
        return None
    return size, kind, header_size


def valid_moov(image: Image, pos: int, end: int) -> bool:
    kinds = set()
    while pos < end:
        box = box_header(image, pos, end)
        if box is None:
            return False
        size, kind, _ = box
        kinds.add(kind)
        pos += size
    return b"mvhd" in kinds and b"trak" in kinds


def mp4(image: Image, start: int, limit: int) -> Candidate | None:
    end = min(image.size, start + limit)
    first = box_header(image, start, end)
    if first is None:
        return None
    size, kind, header_size = first
    if kind != b"ftyp" or size < header_size + 8 or size > MIB:
        return None
    payload = image.read(start + header_size, size - header_size)
    if len(payload) % 4:
        return None
    brands = {payload[:4]} | {payload[i:i + 4] for i in range(8, len(payload), 4)}
    still_brands = {b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1", b"avif", b"avis"}
    supported = {b"isom", b"mp41", b"mp42", b"avc1", b"dash", b"qt  ",
                 b"M4V ", b"M4A ", b"M4B ", b"MSNV", b"3gp4", b"3gp5", b"3gp6", b"3g2a"} | still_brands
    supported.update(f"iso{i}".encode() for i in range(2, 10))
    if not brands & supported:
        return None
    allowed = {b"moov", b"mdat", b"free", b"skip", b"wide", b"uuid", b"pnot",
               b"meta", b"moof", b"mfra", b"sidx", b"ssix", b"styp", b"pdin",
               b"emsg", b"prft"}
    pos = start + size
    seen_moov = seen_mdat = False
    seen_meta = False
    still_image = bool(brands & still_brands)
    while pos < end:
        box = box_header(image, pos, end)
        if box is None:
            break
        size, kind, header_size = box
        if kind not in allowed:
            break
        if kind == b"moov":
            if seen_moov or not valid_moov(image, pos + header_size, pos + size):
                return None
            seen_moov = True
        if kind == b"mdat":
            seen_mdat = True
        if kind == b"meta":
            seen_meta = True
        pos += size
    if not seen_mdat or not (seen_meta if still_image else seen_moov):
        return None
    extension = "mov" if payload[:4] == b"qt  " else "mp4"
    if payload[:4] in (b"M4A ", b"M4B "):
        extension = "m4a"
    if payload[:4].startswith((b"3gp", b"3g2")):
        extension = "3gp"
    if still_image:
        extension = "avif" if brands & {b"avif", b"avis"} else "heic"
    return Candidate(start, pos - start, extension, "box_structure_estimated_boundary")


VALIDATORS = {"jpg": jpeg, "png": png, "wav": wav, "mp4": mp4}


def wrap_extractor(kind, extractor):
    def validate(image, start, limit):
        extracted = extractor(image, start, limit)
        if extracted is None:
            return None
        size, extension, validation = extracted
        if kind in ("webp", "avi") and extension != kind:
            return None
        return Candidate(start, size, extension, validation)
    return validate


VALIDATORS.update({kind: wrap_extractor(kind, extractor) for kind, extractor in EXTRACTORS.items()})


def expand_types(types):
    expanded = set(types)
    if "tif" in expanded:
        expanded.add("tif_be")
    if "mp3" in expanded:
        expanded.add("mp3_raw")
    return expanded


def scan(image: Image, types, max_bytes: int, chunk_size: int = 8 * MIB, progress=None):
    """Yield non-overlapping candidates with a bounded scan buffer. 分块提取非重叠候选。"""
    if chunk_size <= 0 or max_bytes <= 0:
        raise ValueError("Scan block size and file limit must be positive.")
    types = expand_types(types)
    if not types or not types <= SIGNATURES.keys():
        raise ValueError("Select at least one supported format.")
    overlap = max(len(SIGNATURES[kind][0]) for kind in types) - 1  # Preserve split signatures. / 保留跨块签名。
    pos = skip_until = 0
    while pos < image.size:
        if progress is not None:
            progress(pos, image.size)
        data = image.read(pos, chunk_size + overlap)
        base_length = min(chunk_size, image.size - pos)
        hits = set()
        for kind in types:
            signature, adjustment = SIGNATURES[kind]
            cursor = 0
            while True:
                index = data.find(signature, cursor)
                if index < 0 or index >= base_length:
                    break
                start = pos + index + adjustment
                if kind in ("mp3_raw", "aac"):
                    header = data[index:index + 4]
                    if len(header) < 4:
                        header = image.read(start, 4)
                    if (kind == "mp3_raw" and mp3_frame(header) is None
                            or kind == "aac" and (len(header) < 4 or header[1] & 246 != 240)):
                        cursor = index + 1
                        continue
                if start >= skip_until:
                    hits.add((start, kind))
                cursor = index + 1
        for start, kind in sorted(hits):
            if start < skip_until:
                continue
            candidate = VALIDATORS[kind](image, start, max_bytes)
            if candidate is not None:
                yield candidate
                skip_until = start + candidate.size
        pos = max(pos + base_length, skip_until)
    if progress is not None:
        progress(image.size, image.size)


def export(image: Image, candidate: Candidate, directory: Path) -> dict:
    name = f"offset_{candidate.offset:016x}.{candidate.extension}"
    target = directory / name
    if shutil.disk_usage(directory).free < candidate.size + MIB:
        raise OSError("Insufficient free space on the output disk.")
    digest = hashlib.sha256()
    output = target.open("xb")  # Exclusive creation; no overwrite. / 独占创建，禁止覆盖。
    try:
        with output:
            pos = candidate.offset
            remaining = candidate.size
            while remaining:
                data = image.read(pos, min(BLOCK, remaining))
                if not data:
                    raise OSError("The image changed or was truncated during reading.")
                output.write(data)
                digest.update(data)
                pos += len(data)
                remaining -= len(data)
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return {**asdict(candidate), "file": name, "sha256": digest.hexdigest()}


def positive_int(text: str) -> int:
    value = int(text)
    if value <= 0:
        raise argparse.ArgumentTypeError("A positive integer is required.")
    return value


def main(argv=None, *, log=None, on_record=None, on_directory=None, progress=None,
         cancel_event=None, language="zh") -> int:
    """Shared CLI/GUI pipeline; only presentation depends on language. 中英共用恢复流程。"""
    language_parser = argparse.ArgumentParser(add_help=False)
    language_parser.add_argument("--language", choices=("en", "zh"), default=language)
    language_args, _ = language_parser.parse_known_args(argv)
    translate = Translator(language_args.language)

    def localized_positive_int(value):
        try:
            return positive_int(value)
        except (ValueError, argparse.ArgumentTypeError):
            raise argparse.ArgumentTypeError(translate("A positive integer is required.")) from None

    parser = argparse.ArgumentParser(
        description=translate("Read-only carving of contiguous media from a raw disk image."),
        add_help=False,
    )
    parser.add_argument("-h", "--help", action="help", help=translate("Show this help message and exit"))
    parser.add_argument("--language", choices=("en", "zh"), default=language_args.language,
                        help=translate("Interface/report language: en or zh"))
    parser.add_argument("image", type=Path, help=translate("Raw image file, for example disk.img or disk.dd"))
    parser.add_argument("-o", "--output", type=Path, help=translate("Output folder on a different healthy physical disk"))
    parser.add_argument("--dry-run", action="store_true", help=translate("Inspect candidates without exporting or decoding"))
    parser.add_argument("--types", default="all", help=translate("all, or comma-separated selectors: {types}", types=",".join(PUBLIC_TYPES)))
    parser.add_argument("--max-file-mib", type=localized_positive_int, default=4096,
                        help=translate("Maximum candidate size in MiB (default: 4096)"))
    parser.add_argument("--chunk-mib", type=localized_positive_int, default=8,
                        help=translate("Scan block size in MiB (default: 8)"))
    parser.add_argument("--no-verify", action="store_true", help=translate("Skip content verification after export"))
    parser.add_argument("--verify-timeout", type=localized_positive_int, default=120,
                        help=translate("Per-file verification timeout in seconds (default: 120)"))
    args = parser.parse_args(argv)
    types = set(PUBLIC_TYPES) if args.types.strip().lower() == "all" else {
        item.strip().lower() for item in args.types.split(",")
    }
    if not types or not types <= SIGNATURES.keys():
        parser.error(translate("Unknown selector. Supported: {types}", types=",".join(PUBLIC_TYPES)))
    if not args.dry_run and args.output is None:
        parser.error(translate("Recovery requires --output; use --dry-run to scan only."))

    image = None
    report = None
    counts = Counter()
    total = 0
    records = []
    directory = None
    def emit(message, **values):
        message = translate(message, **values)
        if log is not None:
            log(message)
        else:
            print(message)
    try:
        image = Image(args.image, cancel_event)
        emit("Source is read-only. Save results on a different physical disk from the lost data.")
        emit("OK means the specified check passed, not equality to the original. Deleted and live files cannot be distinguished.")
        if args.dry_run:
            directory = None
        else:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            directory = args.output / f"recovered_{stamp}_{uuid.uuid4().hex[:8]}"
            directory.mkdir(parents=True, exist_ok=False)
            report = (directory / "manifest.jsonl").open("x", encoding="utf-8")
            report.write(json.dumps({"event": "start", "source": str(args.image.resolve()),
                                     "source_size": image.size, "types": sorted(types),
                                     "max_file_bytes": args.max_file_mib * MIB,
                                     "language": translate.language, "schema_version": 2},
                                    ensure_ascii=False) + "\n")
            report.flush()
            if on_directory is not None:
                on_directory(directory)
            emit("Output: {path}", path=directory.resolve())
        for candidate in scan(image, types, args.max_file_mib * MIB, args.chunk_mib * MIB, progress):
            record = (export(image, candidate, directory) if directory is not None
                      else asdict(candidate))
            if directory is not None:
                if not args.no_verify:
                    emit("Verifying: {file}", file=record["file"])
                    record = annotate_record(record, directory, args.verify_timeout, cancel_event, translate.language)
                else:
                    path = directory / record["file"]
                    target = path.with_name("UNVERIFIED__" + path.name)
                    path.rename(target)
                    record.update(verification_result("UNVERIFIED", "Content verification skipped by user."))
                    record.update(file=target.name, detail=record[f"detail_{translate.language}"])
                records.append(record)
                if on_record is not None:
                    on_record(record)
            if report is not None:
                report.write(json.dumps({"event": "recovered", **record}) + "\n")
                report.flush()
            counts[candidate.extension] += 1
            total += candidate.size
            emit("{extension:4s} offset=0x{offset:x} size={size} bytes {status}",
                 extension=candidate.extension, offset=candidate.offset, size=candidate.size,
                 status=record.get("status", ""))
        if cancel_event is not None and cancel_event.is_set():
            raise RecoveryCancelled()
        summary = {"event": "complete", "files": sum(counts.values()),
                   "bytes": total, "by_type": dict(counts)}
        if report is not None:
            report.write(json.dumps(summary) + "\n")
        emit("Complete: {files} candidates, {size} bytes.", files=summary["files"], size=total)
        return 0
    except (KeyboardInterrupt, RecoveryCancelled):
        emit("Cancelled. Completed files and manifest are kept; any incomplete export is removed.")
        if report is not None:
            report.write(json.dumps({"event": "cancelled"}) + "\n")
        return 130
    except (OSError, ValueError) as error:
        error_text = translate(str(error)) if str(error) in ZH_MESSAGES else str(error)
        emit("Error: {error}", error=error_text)
        if report is not None:
            report.write(json.dumps({"event": "error", "message": str(error)},
                                    ensure_ascii=False) + "\n")
        return 1
    finally:
        if report is not None:
            report.close()
        if image is not None:
            image.close()
        if directory is not None and directory.is_dir():
            try:
                write_gallery(directory, records, translate.language)
            except OSError as error:
                emit("Cannot write gallery: {error}", error=error)


if __name__ == "__main__":
    if len(sys.argv) == 1 or "--gui" in sys.argv[1:]:
        from app import launch

        gui_parser = argparse.ArgumentParser(description="Media Recovery / 媒体恢复", add_help=False)
        gui_parser.add_argument("--gui", action="store_true")
        gui_parser.add_argument("--language", choices=("en", "zh"), default="zh")
        launch(gui_parser.parse_args().language)
    else:
        raise SystemExit(main())
