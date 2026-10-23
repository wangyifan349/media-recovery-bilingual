# 🛠️ Development notes / 开发说明

## One implementation / 一套实现

- **EN:** Keep format parsers and validators independent of UI language. Only presentation is translated. English/Chinese launchers must import the same `app.py` and `recover.py`.
- **中文：** 格式解析和校验不得依赖界面语言，只翻译展示层；两个语言入口必须共用 `app.py`、`recover.py`。

## Translation contract / 翻译约定

- **EN:** Add the English message and its Chinese counterpart to `i18n.ZH_MESSAGES`. Use named placeholders with identical names, conversion flags and format specs. Use `Translator` per window/call, not a mutable global locale. New validation explanations go through `verification_result`, which stores both languages. Never translate file bytes, stable status codes, suffixes, hashes or user paths. Do not construct new message keys by concatenating dynamic values.
- **中文：** 在 `i18n.ZH_MESSAGES` 同时添加英文消息和中文对应项。命名占位符的名称、转换标志和格式必须一致。每窗口/调用使用独立 `Translator`，禁止可变全局语言。新校验说明通过 `verification_result` 保留双语。不得翻译文件字节、稳定状态码、扩展名、哈希或用户路径，也不要拼接动态值生成消息键。

## Parsing and safety invariants / 解析与安全约束

- **EN:** Source handles are `rb`, exports are exclusively created, and scans operate on regular files only. Every offset/length calculation must be bounded by image size and per-file limit. Reject ambiguous sizes rather than treating the entire disk-image EOF as a file EOF. Document heuristic boundaries explicitly. Do not execute recovered files, extract archive paths, invoke shell commands, or introduce network protocols in decoders.
- **中文：** 源句柄仅 `rb`，导出独占创建，只扫描普通文件。所有偏移和长度须受镜像大小及单文件上限约束。对于歧义长度应拒绝，不能把镜像末尾当原文件末尾。明确说明启发式边界。不得执行恢复文件、解压归档路径、调用 shell 或给解码器引入网络协议。

## Checks and status meanings / 校验与状态

- **EN:** `OK` means only the implemented check passed. Missing libraries, unsupported codecs, timeout and inconclusive decoder rejection are `UNVERIFIED`, not proof of damage. Use `DAMAGED` for a detected error. Always preserve decoder limits and document them. Subprocess isolation/deadlines are not a security sandbox.
- **中文：** `OK` 仅表示已实现检查通过。缺库、不支持、超时、原因不确定的解码拒绝均应为 `UNVERIFIED`，不是损坏证明；发现具体错误才用 `DAMAGED`。保留并记录解码限制，子进程隔离和限时不等于安全沙箱。

## Style / 代码风格

- **EN:** Use English `snake_case` names, `UPPER_SNAKE_CASE` constants, small focused functions and type annotations at public/UI boundaries. Add concise English/Chinese comments beside non-obvious invariants. Avoid “comments on every line”: they obscure logic and become inconsistent. Never maintain two copied parser implementations just to translate comments.
- **中文：** 使用英文 `snake_case` 名称、`UPPER_SNAKE_CASE` 常量、单一职责函数，在公开/UI 边界补类型。关键约束旁用简洁双语注释。不要逐行重复语法，避免遮蔽逻辑和注释失配；不能为了翻译注释维护两份解析实现。

## Before publishing / 发布前

```bash
python -X utf8 -m unittest discover -s . -p "test_*.py" -v
python recover.py --language en --help
python recover.py --language zh --help
```

- **EN:** Test an extracted source ZIP as well as the working tree. Check language placeholder parity, byte/status parity, export hashes and no-overwrite behavior. State actual skips and available platforms; do not claim real-device recovery or remote CI success without evidence. Publish source/tests/docs only, never real recovery images, manifests, secrets, local dependencies or caches.
- **中文：** 工作树和解压后的源码包都要测试。检查占位符、字节/状态一致性、导出哈希和不覆盖行为。如实说明跳过项及已测平台，不得无依据声称真盘恢复或远端 CI 通过。仅发布源码、测试和文档，不发布真实镜像、恢复清单、密钥、本地依赖或缓存。
