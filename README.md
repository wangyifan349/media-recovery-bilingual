# 🔎 Media Recovery · English & 中文

🌐 **Language / 语言:** [🇬🇧 English](README.md) ⇄ [🇨🇳 简体中文](README.zh-CN.md)

A Python 3 **read-only raw-image file-carving tool** with English and Chinese desktop interfaces, optional post-export checks, status-prefixed filenames, and offline image galleries.

> ⚠️ This is an experimental recovery aid, **not a guaranteed recovery or damaged-file repair product**. It finds recognizable, contiguous byte ranges in an image; it cannot determine whether a candidate was deleted. Passing a check does not prove that a file matches its original contents.

## 🛑 1. Protect the original disk first

1. Stop using the physical disk that lost data. Do not install this project or dependencies, download files, run filesystem repair, or save results there.
2. Put Python, this project, the image and output on healthy storage **other than the original physical disk**. Different partitions/drive letters can still belong to the same disk. The program does not check physical-disk identity.
3. Use a trusted imaging tool to create a sector-by-sector **raw** image, then scan a copy. Imaging is not implemented here. E01, VHD/VHDX, QCOW2 and compressed containers must first be converted correctly to raw bytes; changing an extension is not conversion.
4. Clicking, disconnecting or failing drives should not be repeatedly scanned. For valuable data, consult a professional recovery service.

SSD TRIM, overwriting, encryption and fragmentation can make recovery impossible. “I have not written anything” does not guarantee that bytes remain recoverable. A read-only file handle does not replace a forensic write blocker; the OS may still update access metadata.

## 🚀 2. Start either edition

**Python 3.10+** is required. GUI use also requires Tkinter and a working graphical display. Windows/macOS Python distributions commonly include Tk; Linux installations may require a separate Tk package. The CLI does not import Tkinter.

Extract the ZIP and open a terminal **inside the `media_recovery` folder**, or enter the cloned repository. All commands below run from that directory:

```bash
python start_en.py                 # English edition
python start_zh.py                 # Chinese edition
python start.py --language en      # Equivalent explicit choice
```

Both launchers use **the same recovery/verification code**, not independently maintained copies. The **Language** menu switches the interface when no task is running, preserving paths, settings and loaded results. System file dialogs and third-party error messages may follow the OS/library language; user paths and filenames are never translated.

There are no bundled third-party libraries, automatic installers, account sign-ins, telemetry or application-initiated network requests. These guarantees concern the application itself, not OS behavior or a browser/viewer you launch.

### 📦 Required Python libraries

Install the following Python libraries before starting. They are imported directly, without missing-library fallback branches. Core carving and PCM WAV reading use standard-library algorithms, but the application imports its verification libraries at startup:

```bash
python -m pip install -r requirements.txt
```

| Component | Used for | Requirement |
| --- | --- | --- |
| Pillow | Image identification, integrity checks, exposed-frame/page decoding and thumbnails | Required |
| miniaudio | Streaming decode of supported MP3, FLAC, Ogg Vorbis and non-PCM WAV | Required |
| pillow-heif | Registered HEIC decoder plugin | Required |

**All checks use Python code/libraries. No FFmpeg executable, external player or other external media program is used for verification.** The isolated verification worker is another Python process, not an external media tool. Video checks are structural only and video results remain `UNVERIFIED`; installing these libraries does not provide full video decoding. miniaudio, Pillow and pillow-heif contain native components: Python-package-only does **not** mean pure Python. Offline installation needs suitable wheels and their dependencies; none are bundled. AVIF depends on Pillow's codec support. Missing required libraries raise an ordinary import error; data/decoder/timeout exception handling is retained.

### 🔠 Larger, adjustable interface

The default UI font is **14 points**, with matching menu/heading fonts, padded buttons and taller result rows. Use **A− / A+** or the **Text size** menu to adjust it between 11 and 22 points without stopping recovery. Reset returns to 14 points. Font size is kept when switching languages for the current session. Format groups use tabs; settings/actions use multiple rows, long explanations wrap, and results have both scrollbars. The whole page can scroll vertically on smaller displays. Window size adapts to the display; extremely small displays or very large text may still require resizing/reducing text size. Gallery text is also larger.

## 🖱️ 3. Desktop workflow

1. Choose a raw `.img`, `.dd`, `.raw` or other regular image file. Device paths and direct physical-disk access are deliberately unsupported.
2. Choose format selectors. **MP4** also scans the supported ISO-BMFF variants below; **OGG**, **MKV** and **ZIP** similarly cover their listed relatives.
3. **Read-only scan** lists candidate offsets/sizes in the log. It exports nothing and performs **no decoder checks or previews**. It can still consume substantial time and I/O.
4. Choose a safe output folder and use **Recover and check**. Confirm that the destination is not on the original physical disk. Unchecking “Verify after recovery” marks exports `UNVERIFIED`.
5. Filter results by status, select an image thumbnail, or open the offline gallery after the task finishes/stops. Opening a selected media file requires confirmation and uses the system viewer; other file types are not opened automatically.

**Stop** cooperatively cancels scanning/export; a running decoder subprocess is terminated. Already completed files are kept, and an incomplete export is removed. A currently open result may make renaming fail, particularly on Windows. This is not a resumable scan; rerunning creates a new session.

## 🧩 4. Format coverage — selected variants, not every encoding

There are **21 public scan selectors**, expanding to multiple possible suffixes. The table describes candidate identification separately from content verification. Structural checks are deliberately partial; a candidate can be a false positive or a damaged file, and a damaged/unusual original may be skipped entirely.

| Selector | Candidate suffixes | Boundary/structure checks | Optional post-export checks |
| --- | --- | --- | --- |
| `jpg` | `.jpg` | JPEG markers, segment lengths, frame/scan presence; stuffed bytes and EXIF segment boundaries | Pillow |
| `png` | `.png` | Signature, basic IHDR, chunks, CRCs, IDAT/IEND | Pillow |
| `gif` | `.gif` | GIF87a/89a, color tables, block chain, trailer | Pillow, all frames within limits |
| `bmp` | `.bmp` | Selected DIB header sizes, declared length/pixel offset | Pillow |
| `ico` | `.ico` | Icon directory and referenced data ranges | Pillow's exposed images; **not a guarantee that every embedded size is decoded** |
| `tif` | `.tif` | Classic little-/big-endian TIFF IFDs, selected references, strip/tile ranges | Pillow, exposed pages within limits |
| `webp` | `.webp` | RIFF length/chunk boundaries and WebP chunk presence | Pillow |
| `wav` | `.wav` | RIFF/WAVE, fmt/data, lengths and padding | Standard-library `wave` for supported PCM; otherwise miniaudio if compatible |
| `mp3` | `.mp3` | Optional ID3v2 prefix, at least 3 consecutive MPEG **Layer III** frames; optional ID3v1 | miniaudio; boundary is heuristic |
| `flac` | `.flac` | STREAMINFO with known nonzero sample count, metadata, supported subframes/Rice residuals, header/frame CRCs | miniaudio; **no STREAMINFO PCM-MD5 verification** |
| `aac` | `.aac` | At least 3 consecutive ADTS frames | Structure only; no full AAC decoder integrated |
| `amr` | `.amr` | AMR-NB/WB magic and selected speech/SID frame types | Structure only; no full AMR decoder integrated |
| `ogg` | `.ogg`, `.opus` | Ogg page boundaries, sequence/serial checks, CRC, EOS; OpusHead suffix hint | miniaudio for supported Ogg Vorbis; Opus is structure only |
| `aiff` | `.aiff` | AIFF/AIFC FORM, COMM/SSND and chunk boundaries | Structure only |
| `au` | `.au` | AU header, known data length and basic parameters | Structure only |
| `mp4` | `.mp4`, `.mov`, `.m4a`, `.3gp`, `.heic`, `.avif` | Selected ftyp brands, allowed contiguous boxes; basic moov/mdat or meta/mdat checks | Pillow/plugin for images; video and M4A are structure only |
| `avi` | `.avi` | One RIFF AVI range, top-level chunk boundaries and LIST presence | Structure only; AVI/OpenDML continuations are not reassembled |
| `mkv` | `.mkv`, `.webm` | EBML DocType hint and **finite-size** Segment | Structure only; unknown-size Segments are rejected |
| `flv` | `.flv` | Header and selected tag types, lengths and PreviousTagSize | Structure only; boundary is heuristic |
| `pdf` | `.pdf` | Header and first `%%EOF` with nearby `startxref` | Structure only; may recover an older incremental revision, not the latest document |
| `zip` | `.zip`, `.docx`, `.xlsx`, `.pptx`, `.epub` | EOCD and central directory; member-name suffix hints | Standard-library member read/CRC checks; **not Office/EPUB semantic validation** |

Important exclusions and ambiguities:

- No NTFS/FAT/exFAT metadata recovery, deleted/live distinction, original filenames/paths/timestamps, filesystem-fragment reassembly, bad-sector rescue, encrypted-volume decryption or damaged-media repair.
- ISO-BMFF has no universal end marker: adjacent valid-looking boxes can be included, and unknown/size-zero boxes or missing `moov` can cause omission/truncation. Only selected MOV/3GP/HEIC/AVIF layouts are recognized; fragmented MP4 is not guaranteed.
- MP3/AAC/AMR/FLV boundaries are inferred from consecutive structures; padding or unrelated bytes may resemble more frames. An imposed file-size limit can also produce a partial candidate in heuristic formats. Decoding successfully does not prove that the original ending was recovered.
- FLAC with unknown/zero total sample count, BigTIFF, arbitrary camera RAW layouts, ZIP64 and split ZIP archives are not supported. ZIP-derived extensions are hints, not authoritative document-type identification.
- Successful candidates suppress overlapping/nested candidates. Embedded thumbnails or files inside accepted containers are not exported separately. Only contiguous bytes are copied.

## ✅ 5. Statuses, previews and verification limits

| Prefix | Meaning | What it does **not** mean |
| --- | --- | --- |
| `OK__` | The implemented decoder/read/CRC check completed without the specified failure | Perfect recovery, identical original content, semantic correctness, every codec feature validated, or malware-free |
| `DAMAGED__` | A supported check detected a concrete content error, empty decode or insufficient data | That every other file was fully checked |
| `UNVERIFIED__` | No integrated compatible decoder, unsupported codec, skipped check, timeout, safety limit or inconclusive failure | Definitely damaged or definitely usable |

Checks are limited to what each library reports. A decoder can conceal errors or accept truncated-but-decodable content. miniaudio sample-count comparison allows **8192 interleaved samples** of tolerance; this is not exact original-length verification. PCM WAV reading checks the declared frame byte count, not whether audio sounds correct.

Safety/timeout limits:

- Images: at most **1000 exposed frames/pages** and **150,000,000 cumulative pixels**, plus Pillow's decompression-bomb checks. An ICO may expose only its default selected size. The first exposed frame/page is used for the thumbnail.
- ZIP: at most **10,000 members** and **512 MiB declared uncompressed total**. Encrypted ZIP content is not checked. Members are read for CRC, **never extracted**.
- Each file's decoder subprocess has a default **120-second** deadline and is killed/reaped on timeout/cancel. These are practical checks, **not an OS security sandbox** or a hard memory/CPU quota. Use trusted, updated decoder libraries and inspect untrusted files cautiously.
- The scan buffer defaults to **8 MiB**, but validator buffers, candidate bookkeeping and GUI result/history lists also consume memory. The application is not constant-memory for unlimited results. GUI history loading refuses manifests larger than 64 MiB.

## 📁 6. Output and audit trail

Every export run creates a new `recovered_<UTC timestamp>_<random id>` folder:

```text
recovered_.../
├── OK__offset_0000000000001000.png
├── UNVERIFIED__offset_0000000000009000.mp4
├── manifest.jsonl
├── preview.html          # Selected language
├── preview_en.html       # English gallery
├── preview_zh.html       # Chinese gallery
└── previews/             # Generated image thumbnails, when available
```

Filenames use the **source-image byte offset**, not the original filename. The three HTML files are offline galleries with no JavaScript or remote assets; switching language does not copy media again.

`manifest.jsonl` is append-oriented JSON Lines. Start records include source path/size, selectors, maximum candidate size, selected language and schema version. Export records include offset, size, suffix, structural-check identifier, SHA-256, stable status code, bilingual `detail_en`/`detail_zh`, selected-language `detail` and optional preview path. The session ends with `complete`, `cancelled` or `error` when possible. Without `complete`, **do not treat the scan as complete**. Sudden power loss/process termination may leave a partial final line or unlisted file; this is not a crash-safe transaction log.

SHA-256 fingerprints the exported bytes; it does not prove equality to the deleted original. Source paths in manifests can be private: do not publish real recovery output. Gallery-write failure does not necessarily invalidate already exported media. Old manifests with only `detail` remain readable, but their historical explanation cannot be retroactively translated.

## ⌨️ 7. Command-line interface

Example paths below are placeholders; replace them with your safe source/output locations:

```bash
python recover.py --language en "/safe/images/disk.img" --dry-run
python recover.py --language en "/safe/images/disk.img" --output "/other-disk/recovered"
python recover.py --language zh "/safe/images/disk.img" --output "/other-disk/recovered"
python recover.py --language en "/safe/images/disk.img" -o "/other-disk/recovered" --types jpg,png,flac,mp4
python recover.py --language en "/safe/images/disk.img" -o "/other-disk/recovered" --max-file-mib 16384 --verify-timeout 300
python recover.py --language en --help
```

On Windows, a path such as `"E:\images\disk.img"` and a destination such as `"F:\Recovered"` can be used **only after you confirm the physical disks are safe**.

| Argument | Default / behavior |
| --- | --- |
| `image` | Required raw image file for CLI scans |
| `-o`, `--output` | Required unless `--dry-run` |
| `--language en\|zh` | `zh`; selects application messages and primary gallery language |
| `--types` | `all`; comma-separated public selectors from the format table |
| `--max-file-mib` | `4096`; upper bound per candidate, 1 MiB = 1,048,576 bytes |
| `--chunk-mib` | `8`; positive scan-block size |
| `--verify-timeout` | `120`; positive seconds per file |
| `--no-verify` | Export with `UNVERIFIED__`; no decoder work |
| `--dry-run` | Scan/log only; no exports, manifest or gallery |
| `--gui --language en` | Start the GUI instead of a CLI scan; do not combine with scan arguments |

CLI exit codes: `0` = scan completed (not proof of successful recovery), `1` = runtime error, `2` = invalid CLI arguments, `130` = cooperative cancellation. No-argument `recover.py` starts the Chinese GUI. The program does not prevent access-time updates or source changes made by other processes; keep the image unchanged throughout scanning.

## 🧪 8. Tests and code structure

```bash
python -X utf8 -m unittest discover -s . -p "test_*.py" -v
```

Tests create temporary synthetic media/container data; Pillow tests also generate real small images. They cover boundaries, malformed/truncated structures, no-overwrite exports, hashes, cancellation, language placeholders, English-only presentation and byte/status parity between editions. Required libraries must be installed. GUI tests require an interactive display and skip in GitHub Actions or when Tk/a display is unavailable. Synthetic MP3/MP4 fixtures are **structural tests, not proof of real-world audio/video decoding coverage**.

GitHub Actions installs requirements and tests Python 3.10/3.13 on Linux, Windows and macOS, plus a Python-library job. Configuration alone is not evidence of success: check Actions for the particular commit. No developer-machine diagnostics or environment inventories are distributed.

| File | Responsibility |
| --- | --- |
| `start_en.py`, `start_zh.py`, `start.py` | Language-specific and configurable launchers |
| `app.py` | Tk menus, worker queue, previews and history |
| `recovery_gui.py` | Compatibility entry point for the earlier filename |
| `recover.py` | Read-only input, built-in carvers, CLI and export pipeline |
| `extra_formats.py`, `flac_carver.py` | Additional bounded structural parsers |
| `validation_worker.py`, `verification.py` | Decoder subprocesses, statuses and dual-language galleries |
| `i18n.py` | Central English/Chinese messages and bilingual explanations |
| `release_check.py`, `build_release.py` | Publication allowlist/privacy patterns and retested, normalized source ZIPs |
| `test_*.py` | Regression and language-consistency tests |

Identifiers use English. Critical inline comments/docstrings are bilingual to keep one auditable implementation. Comments explain invariants and non-obvious boundaries rather than repeating every Python statement. See [the bilingual development notes](DEVELOPMENT.md) before changing parsers or translations.

For irreplaceable data, evaluate mature tools such as PhotoRec/TestDisk or professional services before relying on this prototype. Recovery finds remaining bytes; **repair reconstructs damaged structures and is outside this program's scope**.

## 💾 9. Build a backup habit before you need recovery

- **🗂️ Keep multiple copies on multiple media.** A useful baseline is **3–2–1**: three total copies including the working copy, on at least two kinds of storage, with one copy stored separately/off-site. For example: your working files, a versioned external-drive backup, and an independent off-site copy. A single cloud account or one external drive is not enough for irreplaceable data.
- **⏱️ Back up promptly and regularly.** Copy important new photos, recordings and documents soon after creating/importing them. Use a schedule, check that scheduled jobs actually complete, and keep older versions rather than overwriting your only good copy.
- **🔄 Synchronization is not the same as backup.** Deletions and unwanted edits may synchronize too. Confirm the service's version history, deletion retention and restore behavior; keep another independent copy rather than relying only on cloud sync.
- **🔌 Keep a disconnected or otherwise isolated copy.** Disconnect a backup drive when it is not needed, and do not keep every copy attached to the same device. Isolation helps prevent a single mistake or failure from affecting all copies.
- **🛡️ Reduce accidental changes.** Where practical, give completed archives read-only permissions and limit write access to backup folders. Ordinary read-only permissions can be changed or bypassed by privileged software: they help prevent mistakes, but do **not** replace a disconnected, independent backup.
- **✅ Check data periodically—and test a restore.** Open a small sample, compare file counts/sizes or trusted checksums, and restore a few files to a temporary location. A successful copy message is not proof that the backup is complete, readable or restorable. Check that your other copies remain accessible as media age.
- **🏷️ Organize before deleting.** Use clear dated folders and meaningful filenames, keep a simple list of where each backup lives, and review duplicates carefully. Confirm at least one independent, tested copy before removing originals or reorganizing large collections.

> 🌱 The best recovery plan is a recent, independent and tested backup. This tool is a fallback for accidents—not a substitute for backup.

## 🤝 A note from the author

This personal project is shared in good faith to help others. My skills outside my professional work are limited, so I cannot make the software fully polished or as powerful and comprehensive as a professional recovery product. Thank you for your understanding. The software already provides basic recovery and checking functions, but successful recovery is not guaranteed.

This project is licensed under the **GNU General Public License, version 3 only (`GPL-3.0-only`)**; see the complete [LICENSE](LICENSE). It is provided without warranty, as described in the license. Third-party libraries retain their own licenses.

**📜 License: GPL 3.0 (`GPL-3.0-only`) · ✍️ Author: 王一帆 (Wang Yifan)**
