# 验收报告 / Acceptance report — resume-design 0.1.4

生成时间：2026-10-25 08:08；环境：Windows 11 (10.0.26300) [AMD64]，Python 3.12.7。**全部使用虚构数据。**

## 1. 测试结果

运行命令：`python scripts/run_acceptance.py`（内部执行 `unittest discover -s tests`；本机未安装 pytest，未运行 pytest）。

| 总数 | 通过 | 失败 | 错误 | 环境阻断(blocked_by_environment) | 其它跳过 | 耗时 |
|---|---|---|---|---|---|---|
| 163 | 162 | 0 | 0 | 1 | 0 | 139s |

### 环境阻断/跳过的测试（**不计为通过**）

- `test_export_pdf.RealLibreOffice.test_libreoffice_exports_verified_pdf` — blocked_by_environment: libreoffice not available

## 2. 环境与 PDF 后端检测

| 后端 | 可用 | 路径 | 版本/备注 |
|---|---|---|---|
| word | 是 | WINWORD.EXE | 16.0.20430.20182 |
| libreoffice | 否 | - | soffice not found on PATH or in standard install folders |

- pdftotext：pdftotext.EXE（pdftotext version 4.06 [www.xpdfreader.com]）；pdffonts：无（字体检查改用内置 PDF 扫描器）
- 可选 Python 包：{'docx': False, 'pypdf': False, 'fitz': False, 'pytest': False}
- 中文字体：['dengxian', 'fangsong', 'kaiti', 'microsoft yahei', 'noto sans sc', 'noto serif sc', 'simhei', 'simsun', 'source han']

## 3. 实际 PDF 导出结果

对虚构示例 `examples/sample_resume.md` 用 5 个模板分别导出并核验：

| 模板 | 退出码 | PDF 状态 | 后端 | 页数 | 字节 | 文本可提取 | 中文字符保留 | 字体(嵌入全部=是/否) |
|---|---|---|---|---|---|---|---|---|
| ats-clean | 0 | passed | word | 2 | 135978 | passed | 158/158 | ArialMT, MicrosoftYaHei, MicrosoftYaHei-Bold (全部嵌入) |
| creative | 0 | passed | word | 1 | 135929 | passed | 158/158 | ArialMT, MicrosoftYaHei, MicrosoftYaHei-Bold (全部嵌入) |
| management | 0 | passed | word | 2 | 95521 | passed | 158/158 | ArialMT, SimSun (全部嵌入) |
| modern-business | 0 | passed | word | 2 | 136431 | passed | 158/158 | ArialMT, MicrosoftYaHei, MicrosoftYaHei-Bold (全部嵌入) |
| technical | 0 | passed | word | 1 | 135369 | passed | 158/158 | ArialMT, MicrosoftYaHei, MicrosoftYaHei-Bold (全部嵌入) |

LibreOffice 路径：**blocked_by_environment**（本机未安装；代码路径已实现，仅用失败桩程序验证了错误处理，**未做真实 LibreOffice 导出**）。

## 4. 平台兼容矩阵（摘自 core/platform-capabilities.md）

| 平台 | 状态 |
|---|---|
| 引擎（Markdown/DOCX） | 已实际测试（Windows 11 / Python 3.12） |
| PDF — Microsoft Word COM | 已实际测试 |
| PDF — LibreOffice | blocked_by_environment（未安装） |
| Claude Code | 依据官方规范实现；静态检查通过；**未在 Claude Code 内实际调用** |
| OpenAI Codex | 依据官方规范实现；静态检查通过；**本机无 Codex CLI，未实际调用** |
| DeepSeek / 豆包 / 其他 | 人工流程，**未实测** |

## 5. 未完成项与环境阻断

- 平台内实测（Claude Code / Codex / DeepSeek / 豆包）：未做，需要用户在对应平台运行。
- LibreOffice 真实导出：本机未安装。
- macOS/Linux：未测试。
- 分页、其他 Word 版本差异、目标 ATS 解析：无法离线验证（报告 C 类）。
- 十个任务场景中的**模型对话行为**（提问、措辞、口头拒绝）未测试，仅测试了工具链；见 skill-scenarios.md。
- 未执行与 Skill Creator 的基线对比（本机/本环境未使用该工具）。

## 6. 安装、调用与升级

见 README 第 7–9、17、23 节。安装预览：`python scripts/install_skill.py --target claude-code-user --dry-run`。
