"""Bounded structural carvers. 限定读取范围的结构提取器；偏移均相对于镜像。"""

import struct
from flac_carver import flac, make_crc_table


OGG_CRC_TABLE = make_crc_table(0x04C11DB7, 32)


EXTRA_SIGNATURES = {
    "gif": (b"GIF8", 0), "bmp": (b"BM", 0),
    "ico": (b"\x00\x00\x01\x00", 0),
    "tif": (b"II\x2a\x00", 0), "tif_be": (b"MM\x00\x2a", 0),
    "webp": (b"RIFF", 0), "avi": (b"RIFF", 0),
    "aiff": (b"FORM", 0), "au": (b".snd", 0),
    "ogg": (b"OggS", 0), "mp3": (b"ID3", 0),
    "mp3_raw": (b"\xff", 0), "aac": (b"\xff", 0),
    "amr": (b"#!AMR", 0), "mkv": (b"\x1aE\xdf\xa3", 0),
    "flv": (b"FLV", 0), "pdf": (b"%PDF-", 0),
    "zip": (b"PK\x03\x04", 0),
    "flac": (b"fLaC", 0),
}


def gif(image, start, limit):
    end = min(image.size, start + limit)
    header = image.read(start, 13)
    if len(header) < 13 or header[:6] not in (b"GIF87a", b"GIF89a"):
        return None
    if not int.from_bytes(header[6:8], "little") or not int.from_bytes(header[8:10], "little"):
        return None
    position = start + 13
    if header[10] & 128:
        position += 3 * (2 << (header[10] & 7))
    frames = 0
    while position < end:
        marker = image.read(position, 1)
        position += 1
        if marker == b";":
            return (position - start, "gif", "gif_blocks") if frames else None
        if marker == b",":
            descriptor = image.read(position, 9)
            if len(descriptor) < 9:
                return None
            position += 9
            if descriptor[8] & 128:
                position += 3 * (2 << (descriptor[8] & 7))
            if position >= end or not 2 <= image.read(position, 1)[0] <= 8:
                return None
            position += 1
            frames += 1
        elif marker == b"!":
            position += 1  # Extension label. / 扩展标签。
        else:
            return None
        while position < end:
            length = image.read(position, 1)[0]
            position += 1 + length
            if not length:
                break
        else:
            return None
    return None


def bmp(image, start, limit):
    header = image.read(start, 30)
    if len(header) < 30:
        return None
    size, pixel_offset, dib_size = (int.from_bytes(header[a:b], "little")
                                   for a, b in ((2, 6), (10, 14), (14, 18)))
    if (header[6:10] != b"\0" * 4 or dib_size not in (12, 40, 52, 56, 64, 108, 124)
            or not 14 + dib_size <= pixel_offset < size <= limit or start + size > image.size):
        return None
    return size, "bmp", "bmp_declared_size"


def ico(image, start, limit):
    header = image.read(start, 6)
    if len(header) != 6:
        return None
    count = int.from_bytes(header[4:6], "little")
    if not 1 <= count <= 256:
        return None
    size = 6 + count * 16
    entries = image.read(start + 6, count * 16)
    if len(entries) != count * 16:
        return None
    for index in range(count):
        entry = entries[index * 16:(index + 1) * 16]
        length, offset = struct.unpack("<II", entry[8:16])
        if not length or offset < 6 + count * 16:
            return None
        size = max(size, offset + length)
    if size > limit or start + size > image.size:
        return None
    return size, "ico", "icon_directory"


def tiff(image, start, limit):
    end = min(limit, image.size - start)
    endian = "<" if image.read(start, 2) == b"II" else ">"
    header = image.read(start, 8)
    if len(header) != 8:
        return None
    position = struct.unpack(endian + "I", header[4:8])[0]
    pending = [position]
    seen = set()
    size = 8
    widths = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2,
              9: 4, 10: 8, 11: 4, 12: 8, 13: 4}
    has_pixels = False
    while pending:
        position = pending.pop()
        if not position:
            continue
        if position in seen or len(seen) >= 256 or position < 8 or position + 2 > end:
            return None
        seen.add(position)
        count = int.from_bytes(image.read(start + position, 2), "little" if endian == "<" else "big")
        table_end = position + 2 + count * 12 + 4
        if count > 4096 or table_end > end:
            return None
        size = max(size, table_end)
        tags = {}
        for index in range(count):
            entry = image.read(start + position + 2 + index * 12, 12)
            tag, kind, amount = struct.unpack(endian + "HHI", entry[:8])
            if kind not in widths or amount > 1000000:
                return None
            length = widths[kind] * amount
            offset = struct.unpack(endian + "I", entry[8:12])[0]
            if length > 4:
                if offset < 8 or offset + length > end:
                    return None
                size = max(size, offset + length)
            if kind in (3, 4, 13) and tag in (273, 279, 324, 325, 330, 34665, 34853, 513, 514):
                data = entry[8:8 + length] if length <= 4 else image.read(start + offset, length)
                values = struct.unpack(endian + ("H" if kind == 3 else "I") * amount, data)
                tags[tag] = values
        for offset_tag, size_tag in ((273, 279), (324, 325), (513, 514)):
            if offset_tag not in tags:
                continue
            if size_tag not in tags or len(tags[offset_tag]) != len(tags[size_tag]):
                return None
            for offset, length in zip(tags[offset_tag], tags[size_tag]):
                if not length or offset < 8 or offset + length > end:
                    return None
                size = max(size, offset + length)
                has_pixels = True
        for tag in (330, 34665, 34853):
            pending.extend(tags.get(tag, ()))
        pending.append(struct.unpack(endian + "I", image.read(start + table_end - 4, 4))[0])
    return (size, "tif", "tiff_referenced_ranges") if has_pixels else None


def riff(image, start, limit):
    header = image.read(start, 12)
    if len(header) < 12:
        return None
    extension = {b"WEBP": "webp", b"AVI ": "avi"}.get(header[8:12])
    size = int.from_bytes(header[4:8], "little") + 8
    if not extension or size < 20 or size > limit or start + size > image.size:
        return None
    position = start + 12
    kinds = set()
    while position + 8 <= start + size:
        chunk = image.read(position, 8)
        length = int.from_bytes(chunk[4:8], "little")
        kinds.add(chunk[:4])
        position += 8 + length + (length & 1)
    if position != start + size:
        return None
    if extension == "webp" and not kinds & {b"VP8 ", b"VP8L", b"VP8X"}:
        return None
    if extension == "avi" and b"LIST" not in kinds:
        return None
    return size, extension, "riff_chunk_structure"


def aiff(image, start, limit):
    header = image.read(start, 12)
    if len(header) < 12 or header[8:12] not in (b"AIFF", b"AIFC"):
        return None
    size = int.from_bytes(header[4:8], "big") + 8
    if not 12 <= size <= limit or start + size > image.size:
        return None
    position = start + 12
    kinds = set()
    while position + 8 <= start + size:
        chunk = image.read(position, 8)
        length = int.from_bytes(chunk[4:8], "big")
        kinds.add(chunk[:4])
        position += 8 + length + (length & 1)
    if position != start + size or not {b"COMM", b"SSND"} <= kinds:
        return None
    return size, "aiff", "aiff_chunks"


def au(image, start, limit):
    header = image.read(start, 24)
    if len(header) < 24:
        return None
    offset, length, encoding, rate, channels = struct.unpack(">IIIII", header[4:24])
    size = offset + length
    if (offset < 24 or not length or length == 0xFFFFFFFF or not 1 <= encoding <= 27
            or not rate or not channels or size > limit or start + size > image.size):
        return None
    return size, "au", "au_declared_size"


def ogg_crc(data):
    checksum = 0
    for value in data:
        checksum = ((checksum << 8) & 0xFFFFFFFF) ^ OGG_CRC_TABLE[(checksum >> 24) ^ value]
    return checksum


def ogg(image, start, limit):
    end = min(image.size, start + limit)
    position = start
    serials = {}
    completed = set()
    extension = "ogg"
    while position + 27 <= end:
        header = image.read(position, 27)
        if header[:5] != b"OggS\0" or header[5] & ~7:
            return None
        serial, sequence, checksum = struct.unpack("<III", header[14:26])
        if serial in completed:
            return None
        if serial not in serials:
            if not header[5] & 2 or sequence:
                return None
        elif sequence != serials[serial] + 1 or header[5] & 2:
            return None
        serials[serial] = sequence
        segments = image.read(position + 27, header[26])
        length = 27 + len(segments) + sum(segments)
        if len(segments) != header[26] or position + length > end:
            return None
        page = image.read(position, length)
        if ogg_crc(page[:22] + b"\0" * 4 + page[26:]) != checksum:
            return None
        if position == start and page[27 + len(segments):].startswith(b"OpusHead"):
            extension = "opus"
        position += length
        if header[5] & 4:
            completed.add(serial)
            if completed == serials.keys():
                return position - start, extension, "ogg_pages_crc_eos"
    return None


def mp3_frame(data):
    if len(data) < 4 or data[0] != 255 or data[1] & 224 != 224:
        return None
    version, layer = (data[1] >> 3) & 3, (data[1] >> 1) & 3
    bitrate_index, rate_index = data[2] >> 4, (data[2] >> 2) & 3
    if version == 1 or layer != 1 or bitrate_index in (0, 15) or rate_index == 3:
        return None  # Layer III only. / 仅支持 MPEG Layer III，不含 Layer I/II。
    bitrates = ([0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320]
                if version == 3 else [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160])
    rate = (44100, 48000, 32000)[rate_index] // {3: 1, 2: 2, 0: 4}[version]
    size = (144 if version == 3 else 72) * bitrates[bitrate_index] * 1000 // rate + ((data[2] >> 1) & 1)
    return size, (version, rate)


def mp3(image, start, limit):
    end = min(image.size, start + limit)
    position = start
    if image.read(position, 3) == b"ID3":
        header = image.read(position, 10)
        if len(header) < 10 or header[3] not in (2, 3, 4) or any(value & 128 for value in header[6:10]):
            return None
        length = sum(value << (7 * (3 - index)) for index, value in enumerate(header[6:10]))
        position += 10 + length + (10 if header[3] == 4 and header[5] & 16 else 0)
    count = 0
    stream = None
    while position + 4 <= end:
        frame = mp3_frame(image.read(position, 4))
        if frame is None or position + frame[0] > end or (stream is not None and stream != frame[1]):
            break
        stream = frame[1]
        position += frame[0]
        count += 1
    if count < 3:
        return None
    if position + 128 <= end and image.read(position, 3) == b"TAG":
        position += 128
    return position - start, "mp3", "mpeg_frames_estimated_boundary"


def aac(image, start, limit):
    end = min(image.size, start + limit)
    position = start
    count = 0
    stream = None
    while position + 7 <= end:
        header = image.read(position, 7)
        if header[0] != 255 or header[1] & 246 != 240 or (header[2] >> 2) & 15 >= 13:
            break
        length = ((header[3] & 3) << 11) | (header[4] << 3) | (header[5] >> 5)
        identity = (header[2] & 252, header[3] & 192)
        if (length < (7 if header[1] & 1 else 9) or position + length > end
                or (stream is not None and identity != stream)):
            break
        stream = identity
        position += length
        count += 1
    return (position - start, "aac", "adts_frames_estimated_boundary") if count >= 3 else None


def amr(image, start, limit):
    wide = image.read(start, 9) == b"#!AMR-WB\n"
    if not wide and image.read(start, 6) != b"#!AMR\n":
        return None
    sizes = ([18, 24, 33, 37, 41, 47, 51, 59, 61, 6] if wide
             else [13, 14, 16, 18, 20, 21, 27, 32, 6])
    position = start + (9 if wide else 6)
    end = min(image.size, start + limit)
    count = 0
    while position < end:
        header = image.read(position, 1)[0]
        frame_type = (header >> 3) & 15
        if header & 131 or frame_type >= len(sizes) or position + sizes[frame_type] > end:
            break
        position += sizes[frame_type]
        count += 1
    return (position - start, "amr", "amr_frames_estimated_boundary") if count >= 3 else None


def read_vint(image, position, end, keep_marker=False):
    if position >= end:
        return None
    first = image.read(position, 1)[0]
    if not first:
        return None
    width = 9 - first.bit_length()
    if position + width > end:
        return None
    raw = image.read(position, width)
    value = int.from_bytes(raw, "big")
    if not keep_marker:
        value &= (1 << (7 * width)) - 1
        if value == (1 << (7 * width)) - 1:
            return None  # Unknown length has no safe boundary. / 未知长度无法确定安全边界。
    return value, width


def mkv(image, start, limit):
    end = min(image.size, start + limit)
    header = read_vint(image, start + 4, end)
    if header is None or header[0] > 4096:
        return None
    position = start + 4 + header[1] + header[0]
    header_data = image.read(start, position - start)
    if b"webm" in header_data:
        extension = "webm"
    elif b"matroska" in header_data:
        extension = "mkv"
    else:
        return None
    if image.read(position, 4) != b"\x18\x53\x80\x67":
        return None
    segment = read_vint(image, position + 4, end)
    if segment is None:
        return None
    size = position + 4 + segment[1] + segment[0] - start
    if start + size > end:
        return None
    return size, extension, "ebml_finite_segment"


def flv(image, start, limit):
    end = min(image.size, start + limit)
    header = image.read(start, 9)
    if len(header) < 9 or header[3] != 1 or header[4] & ~5:
        return None
    offset = int.from_bytes(header[5:9], "big")
    if offset < 9 or offset > 4096 or start + offset + 4 > end:
        return None
    position = start + offset
    if image.read(position, 4) != b"\0" * 4:
        return None
    position += 4
    count = 0
    while position + 15 <= end:
        tag = image.read(position, 11)
        length = int.from_bytes(tag[1:4], "big")
        if tag[0] not in (8, 9, 18) or tag[8:11] != b"\0" * 3 or position + 15 + length > end:
            break
        if int.from_bytes(image.read(position + 11 + length, 4), "big") != length + 11:
            break
        position += length + 15
        count += 1
    return (position - start, "flv", "flv_tags_estimated_boundary") if count else None


def find_marker(image, position, end, marker):
    while position < end:
        data = image.read(position, min(1024 * 1024, end - position))
        index = data.find(marker)
        if index >= 0:
            yield position + index
            position += index + 1
        elif len(data) <= len(marker):
            break
        else:
            position += len(data) - len(marker) + 1


def pdf(image, start, limit):
    end = min(image.size, start + limit)
    header = image.read(start, 8)
    if len(header) < 8 or header[5:6] not in (b"1", b"2") or header[6:7] != b".":
        return None
    # First EOF may be an older revision. / 首个 EOF 可能属于较早增量修订，边界仅为推断。
    for position in find_marker(image, start + 8, end, b"%%EOF"):
        tail = image.read(max(start, position - 256), min(256, position - start))
        if b"startxref" in tail:
            size = position + 5 - start
            while start + size < end and image.read(start + size, 1) in (b"\r", b"\n"):
                size += 1
            return size, "pdf", "pdf_first_eof_estimated_boundary"
    return None


def zip_archive(image, start, limit):
    end = min(image.size, start + limit)
    for position in find_marker(image, start + 30, end, b"PK\x05\x06"):
        header = image.read(position, 22)
        if len(header) < 22:
            continue
        disk, central_disk, disk_count, count, length, offset, comment = struct.unpack("<HHHHIIH", header[4:22])
        if (disk or central_disk or not count or disk_count != count or count == 65535
                or start + offset + length != position or position + 22 + comment > end):
            continue
        cursor = start + offset
        names = set()
        valid = True
        for _ in range(count):
            entry = image.read(cursor, 46)
            if len(entry) < 46 or entry[:4] != b"PK\x01\x02":
                valid = False
                break
            name_size, extra_size, comment_size = struct.unpack("<HHH", entry[28:34])
            next_cursor = cursor + 46 + name_size + extra_size + comment_size
            local_offset = int.from_bytes(entry[42:46], "little")
            if next_cursor > position or start + local_offset >= start + offset:
                valid = False
                break
            names.add(image.read(cursor + 46, min(name_size, 256)))
            cursor = next_cursor
        if not valid or cursor != position:
            continue
        extension = "zip"
        if b"[Content_Types].xml" in names:
            for prefix, suffix in ((b"word/", "docx"), (b"xl/", "xlsx"), (b"ppt/", "pptx")):
                if any(name.startswith(prefix) for name in names):
                    extension = suffix
                    break
        elif b"META-INF/container.xml" in names:
            extension = "epub"
        return position + 22 + comment - start, extension, "zip_central_directory"
    return None


EXTRACTORS = {
    "gif": gif, "bmp": bmp, "ico": ico, "tif": tiff, "tif_be": tiff,
    "webp": riff, "avi": riff, "aiff": aiff, "au": au, "ogg": ogg,
    "mp3": mp3, "mp3_raw": mp3, "aac": aac, "amr": amr,
    "mkv": mkv, "flv": flv, "pdf": pdf, "zip": zip_archive,
    "flac": flac,
}
