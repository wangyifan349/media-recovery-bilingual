"""Shared English/Chinese messages. 统一的中英文消息目录。"""

from __future__ import annotations

from dataclasses import dataclass


SUPPORTED_LANGUAGES = ("en", "zh")
STATUS_KEYS = {"OK": "Verified", "DAMAGED": "Damage detected", "UNVERIFIED": "Not fully verified"}

# English messages are stable keys; placeholders must match. / 英文为稳定键，占位符必须一致。
ZH_MESSAGES = {
    "Media Recovery | Read-only image scanner": "媒体数据恢复 | 只读镜像扫描",
    "Select an image. Do not write anything to the physical disk with lost data.": "请选择镜像。不要向丢失数据所在的物理磁盘写入任何内容。",
    "All": "全部", "Verified": "验证通过", "Damage detected": "检测到损坏", "Not fully verified": "未充分验证",
    "Select disk image...": "选择磁盘镜像…", "Select output folder...": "选择输出目录…",
    "Load previous manifest...": "载入历史结果清单…", "Open results folder": "打开结果目录",
    "Exit": "退出", "File": "文件", "Scan without exporting": "只扫描，不导出",
    "Recover and check": "恢复并检查", "Stop task": "停止任务", "Recovery": "恢复",
    "Open image gallery": "打开图片预览页面", "Open selected media...": "打开选中的媒体…",
    "Preview": "预览", "Check optional dependencies": "检测可选依赖", "Formats and limitations": "格式与能力边界",
    "Help": "帮助", "Language": "语言", "Chinese": "中文", "English": "英语",
    "Source and destination": "来源与输出位置", "Source image (read-only)": "源镜像（只读）",
    "Safe output folder": "安全输出目录", "Browse...": "浏览…",
    "Formats | MP4 includes selected MOV / M4A / 3GP / HEIC / AVIF variants": "识别格式 | MP4 包含部分 MOV / M4A / 3GP / HEIC / AVIF 变体",
    "Images": "图片", "Audio": "音频", "Video / HEIC / AVIF": "视频 / HEIC / AVIF", "Documents / archives": "文档 / 压缩包",
    "Select all": "全选", "Clear": "清空", "Max file MiB": "每文件上限 MiB",
    "Verify after recovery": "恢复后自动校验", "Timeout (seconds)": "校验超时（秒）",
    "Read-only scan": "只读扫描", "Stop": "停止", "Filter:": "结果筛选：",
    "OK means the specified check passed, not proof of original integrity.": "OK 表示指定检查通过，不证明与原文件完全一致。",
    "Status": "校验状态", "Recovered filename": "恢复文件名", "Size": "大小",
    "Image preview / verification details": "图片预览 / 校验详情", "Select a result to preview it.": "选择恢复结果以查看预览。",
    "Select a raw sector-by-sector image": "选择原始逐扇区镜像", "Raw images": "原始镜像", "All files": "全部文件",
    "Select a folder on a different, healthy physical disk": "选择另一块健康物理磁盘上的目录",
    "Task running": "任务进行中", "Stop the current task first.": "请先停止当前任务。",
    "Invalid source": "源镜像无效", "Select a regular raw image file, not a drive letter or device.": "请选择普通原始镜像文件，而不是盘符或磁盘设备。",
    "No formats selected": "未选择格式", "Select at least one format.": "请至少选择一种格式。",
    "Invalid settings": "参数错误", "File limit and timeout must be positive integers.": "文件上限和超时必须是正整数。",
    "Confirm safe destination": "确认安全输出位置",
    "Are the program, image and output folder all on disks OTHER than the physical disk with lost data?\n\nDifferent drive letters do not necessarily mean different disks. This program cannot determine that for you.": "确认程序、镜像和输出目录都不在丢失数据所在的物理磁盘上？\n\n不同盘符不一定是不同硬盘。程序不会自动判断。",
    "Scanning read-only. Recovery and full decoding can take a long time...": "正在只读扫描。恢复和完整解码可能需要较长时间…",
    "Task exception: {error}": "任务异常：{error}", "Complete": "完成", "Stopped": "已停止",
    "Error; see the log": "发生错误，请查看日志",
    "{state} | Verified: {ok} | Damage detected: {damaged} | Not fully verified: {unverified}": "{state} | 验证通过 {ok} | 检测到损坏 {damaged} | 未充分验证 {unverified}",
    "No image preview for this result.": "此结果暂无图片预览。", "Cannot load the preview. Try the gallery.": "预览无法加载，请尝试打开预览页面。",
    "No results yet": "尚无结果", "Recover files or load a previous manifest first.": "请先恢复文件，或载入历史结果清单。",
    "Gallery not ready": "预览尚未生成", "The gallery is generated when the task finishes or stops.": "任务结束或停止后会生成预览页面。",
    "Missing file": "文件不存在", "The result does not exist or its path is unsafe.": "结果文件不存在或路径不安全。",
    "Safety notice": "安全提示", "Only image/audio/video files can be opened here. Inspect other recovered files safely yourself.": "此处只打开图片及音视频。其他恢复文件请自行安全检查。",
    "Open recovered media": "打开恢复的媒体",
    "The system viewer will open this file. Recovered files may be damaged or untrusted. Continue?": "将使用系统查看器打开。恢复文件可能损坏或不可信，是否继续？",
    "Cannot open": "无法打开", "Select manifest.jsonl": "选择 manifest.jsonl", "Recovery manifest": "恢复清单",
    "The manifest contains an invalid record.": "清单包含无效记录。", "Cannot read manifest": "无法读取清单",
    "Loaded {count} previous records. This does not re-verify the files.": "已载入 {count} 条历史记录；这不会重新校验文件。",
    "Installed": "已安装", "Not installed (optional)": "未安装（可选）", "Available": "可用", "Not found": "未检测到",
    "FFmpeg (optional; video checks only)": "FFmpeg（可选，仅视频校验）", "Dependency check": "依赖检测",
    "\n\nOptional installation (you run it yourself):\npython -m pip install Pillow miniaudio\n\nPCM WAV uses Python's wave module. Audio does not call FFmpeg or require Windows audio components. miniaudio contains native code; it is not pure Python.": "\n\n可选安装（由你自行执行）：\npython -m pip install Pillow miniaudio\n\nPCM WAV 使用 Python wave 模块。音频不调用 FFmpeg，也不需要 Windows 音频组件。miniaudio 包含原生代码，并非纯 Python。",
    "Limitations": "能力边界",
    "Only contiguous data in raw images is carved; the source is opened read-only.\nNo original names, disk-fragment reassembly, repair or guaranteed recovery.\n\nMKV/WebM: finite Segment sizes only. MP3/AAC/AMR/FLV/MP4/PDF boundaries include heuristics.\nZIP: no ZIP64 or split archives. TIFF: not all private RAW tags.\nHEIC needs an optional Pillow plugin; AVIF depends on the Pillow build.\n\nPassing a check does not prove the file matches the original or is safe.": "仅提取原始镜像中连续存放的数据；源文件只读打开。\n不能恢复原文件名、重组磁盘碎片、修复损坏或保证恢复成功。\n\nMKV/WebM 仅支持有限 Segment 长度。MP3/AAC/AMR/FLV/MP4/PDF 边界含推断。\nZIP 不支持 ZIP64 或分卷。TIFF 不包含所有 RAW 私有标签。\nHEIC 需要可选 Pillow 插件；AVIF 取决于 Pillow 构建。\n\n通过检查不证明与原文件一致或文件绝对安全。",
    "Stopping; completed results will be kept...": "正在停止，保留已完成结果…", "Stop and exit": "停止并退出",
    "Stop the running task and exit? Completed results will be kept.": "是否停止当前任务并退出？已完成结果会保留。",
    "Language change": "切换语言", "Stop the task before changing the interface language.": "请先停止任务，再切换界面语言。",
    "Read-only carving of contiguous media from a raw disk image.": "只读扫描原始磁盘镜像，提取连续存放的媒体文件。",
    "Raw image file, for example disk.img or disk.dd": "普通原始镜像文件，例如 disk.img 或 disk.dd",
    "Output folder on a different healthy physical disk": "另一块健康物理磁盘上的输出目录",
    "Inspect candidates without exporting or decoding": "检查候选，不导出也不解码",
    "all, or comma-separated selectors: {types}": "all 或逗号分隔的选择器：{types}",
    "Maximum candidate size in MiB (default: 4096)": "每个候选最大 MiB（默认 4096）",
    "Scan block size in MiB (default: 8)": "扫描块大小 MiB（默认 8）",
    "Skip content verification after export": "跳过导出后的内容校验",
    "Per-file verification timeout in seconds (default: 120)": "每文件校验超时秒数（默认 120）",
    "Interface/report language: en or zh": "界面及报告语言：en 或 zh", "Show this help message and exit": "显示帮助并退出",
    "Unknown selector. Supported: {types}": "未知选择器。支持：{types}", "Recovery requires --output; use --dry-run to scan only.": "恢复需要 --output；只扫描请使用 --dry-run。",
    "A positive integer is required.": "必须输入正整数。",
    "Input must be a regular image file; disk device paths are not supported.": "输入必须是普通镜像文件；不支持磁盘设备路径。",
    "Input is not a regular file.": "输入不是普通文件。",
    "Scan block size and file limit must be positive.": "扫描块大小和文件上限必须大于零。",
    "Select at least one supported format.": "请至少选择一种受支持的格式。",
    "Insufficient free space on the output disk.": "输出磁盘可用空间不足。",
    "The image changed or was truncated during reading.": "镜像在读取过程中发生变化或被截断。",
    "Source is read-only. Save results on a different physical disk from the lost data.": "源文件只读。结果必须保存到非丢失数据所在的物理磁盘。",
    "OK means the specified check passed, not equality to the original. Deleted and live files cannot be distinguished.": "OK 表示指定检查通过，不代表与原文件一致。不能区分已删除与仍存在的文件。",
    "Output: {path}": "输出目录：{path}", "Verifying: {file}": "正在校验：{file}",
    "Content verification skipped by user.": "用户跳过内容校验。",
    "{extension:4s} offset=0x{offset:x} size={size} bytes {status}": "{extension:4s} 偏移=0x{offset:x} 大小={size} 字节 {status}",
    "Complete: {files} candidates, {size} bytes.": "完成：{files} 个候选，{size} 字节。",
    "Cancelled. Completed files and manifest are kept; any incomplete export is removed.": "已取消。已完成文件和清单保留；正在导出的半成品会移除。",
    "Error: {error}": "错误：{error}", "Cannot write gallery: {error}": "无法写入预览索引：{error}",
    "Verification timed out or was cancelled.": "校验超时或用户取消。",
    "Verification worker failed; the check did not complete.": "校验子进程失败，未完成检查。",
    "The validator returned an unknown status.": "校验器返回未知状态。",
    "Optional FFmpeg was not found; video structure only.": "未检测到可选 FFmpeg；视频仅做结构检查。",
    "Video verification timed out or was cancelled before completion.": "视频校验超时或用户取消，未检查完整内容。",
    "FFmpeg decoding failed: possible damage or unsupported codec.": "FFmpeg 解码失败：可能损坏或编码不受支持。",
    "FFmpeg completed decoding without a reported error; equality to the original is not proven.": "FFmpeg 完成解码且未报告错误；不证明与原文件完全一致。",
    "Structure only; full content verification was not performed.": "仅通过结构检查，未执行完整内容校验。",
    "Verification unavailable: {error}": "校验不可用：{error}",
    "Pillow is not installed; image decoding was not performed.": "未安装 Pillow，未执行图片解码。",
    "Animation/page count exceeds the 1000-frame safety limit.": "动画或多页图片超过 1000 帧安全限制。",
    "Cumulative image pixels exceed the safety limit.": "图片累计像素超过安全限制。",
    "Pillow decoded all {frames} frames/pages, but the preview could not be saved.": "Pillow 完整解码 {frames} 帧或页，但无法保存预览。",
    "Pillow decoded all {frames} frames/pages.": "Pillow 完整解码 {frames} 帧或页。",
    "Image exceeds decoding safety limits.": "图片超过解码安全限制。",
    "Pillow cannot identify the image: possible damage or missing format plugin.": "Pillow 无法识别图片：可能损坏或缺少格式插件。",
    "Image codec not supported: {error}": "当前图片编码不受支持：{error}",
    "Full image decoding failed: {error}": "图片完整解码失败：{error}",
    "PCM WAV data is incomplete or contains no audio frames.": "PCM WAV 数据不完整或没有音频帧。",
    "Python wave read all PCM data: {frames} frames, {rate} Hz.": "Python wave 完整读取 PCM：{frames} 帧，{rate} Hz。",
    "WAV reading failed: {error}": "WAV 读取失败：{error}",
    "This audio format has structural checks only; no compatible full decoder is integrated.": "此音频格式暂仅有结构检查，没有集成兼容的完整解码器。",
    "Optional miniaudio is not installed; audio structure only.": "未安装可选 miniaudio，音频仅通过结构检查。",
    "Audio decoding produced no samples.": "音频解码结果为空。",
    "Audio decoding ended before the declared sample count (allowing decoder tolerance).": "音频解码提前结束，少于声明样本数（已考虑解码器容差）。",
    "miniaudio completed streaming decode (no Windows or FFmpeg dependency).": "miniaudio 完成流式解码（不依赖 Windows 或 FFmpeg）。",
    "miniaudio could not complete decoding: possible damage or unsupported codec: {error}": "miniaudio 未能完成解码：可能损坏或编码不支持：{error}",
    "Encrypted ZIP contents require a password and were not verified.": "加密 ZIP 内容需要密码，未验证。",
    "Archive exceeds the decompression safety limits.": "压缩包超过解压安全限制。",
    "ZIP member CRC failed: {member}": "ZIP 成员 CRC 错误：{member}",
    "All ZIP members passed read/CRC checks; document semantics were not validated.": "ZIP 所有成员读取及 CRC 检查通过；未验证文档语义。",
    "Unsupported compression or encryption: {error}": "压缩算法或加密不受支持：{error}",
    "ZIP integrity check failed: {error}": "ZIP 完整性检查失败：{error}",
    "Image preview": "图片预览", "No image preview": "无图片预览", "Recovered results": "恢复结果",
    "OK = the specified decode/integrity check passed, not proof of equality to the original. DAMAGED = a content error was detected. UNVERIFIED = not fully checked. Do not execute unknown recovered files.": "OK = 指定解码或完整性检查通过，不证明与原文件一致。DAMAGED = 检测到内容错误。UNVERIFIED = 未充分检查。不要执行未知恢复文件。",
}


@dataclass(frozen=True)
class Translator:
    """Immutable per-window language; no process-wide locale. 每窗口语言独立。"""

    language: str = "zh"

    def __post_init__(self) -> None:
        if self.language not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language: {self.language}")

    def __call__(self, message: str, **values: object) -> str:
        template = ZH_MESSAGES[message] if self.language == "zh" else message
        return template.format(**values) if values else template

    def status(self, status: str) -> str:
        return self(STATUS_KEYS[status])


def verification_result(status: str, message: str, **values: object) -> dict:
    """Keep both explanations in manifests. 清单保留两种语言，便于切换。"""
    detail_en = Translator("en")(message, **values)
    detail_zh = Translator("zh")(message, **values)
    return {"status": status, "detail": detail_zh, "detail_en": detail_en, "detail_zh": detail_zh}


def record_detail(record: dict, language: str) -> str:
    """Legacy manifests may only have detail. 兼容旧版仅有 detail 的清单。"""
    return record.get(f"detail_{language}", record.get("detail", ""))
