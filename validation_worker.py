"""Isolated, time-limited decoding worker; no Windows-specific audio dependency."""

import argparse
import json
from pathlib import Path
import warnings
import wave
import zipfile
import zlib

from i18n import verification_result


IMAGE_EXTENSIONS = {"jpg", "png", "gif", "bmp", "ico", "tif", "webp", "avif", "heic"}
AUDIO_EXTENSIONS = {"wav", "aiff", "au", "mp3", "aac", "amr", "ogg", "opus", "flac", "m4a"}
ARCHIVE_EXTENSIONS = {"zip", "docx", "xlsx", "pptx", "epub"}


MAX_IMAGE_FRAMES = 1000
MAX_IMAGE_PIXELS = 150_000_000
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 10_000


def check_image(path, preview):
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError:
        return verification_result("UNVERIFIED", "Pillow is not installed; image decoding was not performed.")
    if path.suffix.lower() == ".heic":
        try:
            import pillow_heif
            pillow_heif.register_heif_opener()  # Optional HEIC integration. / 可选 HEIC 插件注册。
        except ImportError:
            pass
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            # verify() checks structure; load() checks decoding. / 分别检查结构与解码。
            with Image.open(path) as picture:
                picture.verify()
            with Image.open(path) as picture:
                frames = getattr(picture, "n_frames", 1)
                if frames > MAX_IMAGE_FRAMES:
                    return verification_result("UNVERIFIED", "Animation/page count exceeds the 1000-frame safety limit.")
                total_pixels = 0
                thumbnail = None
                for index in range(frames):
                    picture.seek(index)
                    total_pixels += picture.width * picture.height
                    if total_pixels > MAX_IMAGE_PIXELS:
                        return verification_result("UNVERIFIED", "Cumulative image pixels exceed the safety limit.")
                    picture.load()
                    if index == 0:
                        thumbnail = picture.convert("RGBA")
                        thumbnail.thumbnail((480, 320))
                try:
                    preview.parent.mkdir(exist_ok=True)
                    thumbnail.save(preview, "PNG")
                except OSError:
                    return verification_result("OK", "Pillow decoded all {frames} frames/pages, but the preview could not be saved.", frames=frames)
                checked = verification_result("OK", "Pillow decoded all {frames} frames/pages.", frames=frames)
                checked["preview"] = preview.name
                return checked
    except (Image.DecompressionBombError, Image.DecompressionBombWarning, MemoryError):
        return verification_result("UNVERIFIED", "Image exceeds decoding safety limits.")
    except UnidentifiedImageError:
        return verification_result("UNVERIFIED", "Pillow cannot identify the image: possible damage or missing format plugin.")
    except (OSError, ValueError, SyntaxError, EOFError) as error:
        message = str(error)
        if any(word in message.lower() for word in ("not supported", "unsupported", "decoder not available")):
            return verification_result("UNVERIFIED", "Image codec not supported: {error}", error=message[:300])
        return verification_result("DAMAGED", "Full image decoding failed: {error}", error=message[:300])


def check_wave(path):
    try:
        with wave.open(str(path), "rb") as audio:
            expected_frames = audio.getnframes()
            frame_size = audio.getnchannels() * audio.getsampwidth()
            total_bytes = 0
            while True:
                chunk = audio.readframes(65536)
                if not chunk:
                    break
                total_bytes += len(chunk)
            if total_bytes != expected_frames * frame_size or not total_bytes:
                return verification_result("DAMAGED", "PCM WAV data is incomplete or contains no audio frames.")
            return verification_result("OK", "Python wave read all PCM data: {frames} frames, {rate} Hz.", frames=expected_frames, rate=audio.getframerate())
    except wave.Error:
        return None  # Non-PCM may need miniaudio. / 非 PCM 编码交给可选解码器。
    except (OSError, EOFError) as error:
        return verification_result("DAMAGED", "WAV reading failed: {error}", error=str(error)[:300])


def check_audio(path):
    if path.suffix.lower() == ".wav":
        checked = check_wave(path)
        if checked is not None:
            return checked
    if path.suffix.lower() not in {".wav", ".mp3", ".flac", ".ogg"}:
        return verification_result("UNVERIFIED", "This audio format has structural checks only; no compatible full decoder is integrated.")
    try:
        import miniaudio
    except ImportError:
        return verification_result("UNVERIFIED", "Optional miniaudio is not installed; audio structure only.")
    try:
        # Bounded PCM chunks; no playback device is opened. / 分块解码，不打开播放设备。
        audio_info = miniaudio.get_file_info(str(path))
        frames = miniaudio.stream_file(str(path), frames_to_read=4096,
                                      sample_rate=audio_info.sample_rate, nchannels=audio_info.nchannels)
        total_samples = 0
        for samples in frames:
            total_samples += len(samples)
        if not total_samples:
            return verification_result("DAMAGED", "Audio decoding produced no samples.")
        expected_samples = audio_info.num_frames * audio_info.nchannels
        if expected_samples and total_samples + 8192 < expected_samples:
            return verification_result("DAMAGED", "Audio decoding ended before the declared sample count (allowing decoder tolerance).")
        return verification_result("OK", "miniaudio completed streaming decode (no Windows or FFmpeg dependency).")
    except Exception as error:
        # Unsupported codecs are not proof of damage. / 不支持编码并不能证明文件损坏。
        return verification_result("UNVERIFIED", "miniaudio could not complete decoding: possible damage or unsupported codec: {error}", error=str(error)[:300])


def check_archive(path):
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if any(entry.flag_bits & 1 for entry in entries):
                return verification_result("UNVERIFIED", "Encrypted ZIP contents require a password and were not verified.")
            if sum(entry.file_size for entry in entries) > MAX_ARCHIVE_BYTES or len(entries) > MAX_ARCHIVE_ENTRIES:
                return verification_result("UNVERIFIED", "Archive exceeds the decompression safety limits.")
            damaged = archive.testzip()  # Read/CRC only; no extraction. / 仅读取和校验，不解压文件。
            if damaged:
                return verification_result("DAMAGED", "ZIP member CRC failed: {member}", member=damaged[:200])
            return verification_result("OK", "All ZIP members passed read/CRC checks; document semantics were not validated.")
    except (NotImplementedError, RuntimeError) as error:
        return verification_result("UNVERIFIED", "Unsupported compression or encryption: {error}", error=str(error)[:300])
    except (OSError, ValueError, zipfile.BadZipFile, EOFError, zlib.error) as error:
        return verification_result("DAMAGED", "ZIP integrity check failed: {error}", error=str(error)[:300])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("preview", type=Path)
    args = parser.parse_args()
    extension = args.path.suffix.lower().lstrip(".")
    if extension in IMAGE_EXTENSIONS:
        checked = check_image(args.path, args.preview)
    elif extension in AUDIO_EXTENSIONS:
        checked = check_audio(args.path)
    elif extension in ARCHIVE_EXTENSIONS:
        checked = check_archive(args.path)
    else:
        checked = verification_result("UNVERIFIED", "Structure only; full content verification was not performed.")
    print(json.dumps(checked, ensure_ascii=True))


if __name__ == "__main__":
    main()
