# truthful-resume — 专业简历制作与美化工具包（resume-design）

> **English summary** — An offline, privacy-first resume toolkit for AI coding assistants (Claude Code / Codex skills, plus copy-paste
> prompts for DeepSeek, Doubao and other chat models). Python standard library only. It creates, improves, tailors (JD) and translates
> resumes (zh/en), renders **Markdown / DOCX / PDF** with five real templates (ATS-clean, technical, management, modern-business, creative),
> and **never invents facts**: missing data stays a visible `{{MISSING:field}}` placeholder, rewrites are marked for your approval, and the
> tool will not call a resume "ready to submit" without your explicit confirmation. Everything runs locally; no network, no API keys.
> The repository is `truthful-resume`; the skill/package inside is named `resume-design`. License: MIT.

版本 0.1.4（见 `VERSION`、`CHANGELOG.md`）。**离线、本地、默认保护隐私**：不联网、不调用外部模型 API、不上传任何内容。许可证：MIT（见 `LICENSE`）。

## 平台兼容状态（一眼看懂）

| 平台 / 能力 | 状态 |
|---|---|
| Markdown / DOCX 生成、校验、中英文 | **已实测**（Windows 11、Python 3.12） |
| PDF — Microsoft Word（COM） | **已实测**（Word 16；真实导出并核验文本、中文、字体） |
| PDF — LibreOffice | **未实测**（已实现，作者环境未安装） |
| macOS / Linux、Python < 3.12 | **未实测**（仅用标准库，理论上可用，不作承诺） |
| Claude Code Skill | 依据官方文档实现，静态检查通过；**未在 Claude Code 内实际验证触发与行为** |
| OpenAI Codex Skill | 依据官方文档实现，静态检查通过；**未在 Codex 内实际验证** |
| DeepSeek / 豆包 / 其他模型 | 复制提示词的**人工流程，未实测**；纯聊天模型不能生成文件，需你在本地运行脚本 |

详细证据与说明见 `core/platform-capabilities.md`。

## 1. 项目简介

一个由「通用核心 + 平台适配器 + 独立文件生成引擎」组成的简历工具包：

- 对话层（Claude Code / Codex Skill，或 DeepSeek/豆包/通用提示词）负责收集信息、改写措辞、与你确认事实；
- Python 引擎（仅标准库）负责解析、排版、生成 **Markdown / DOCX / PDF**、质量校验和报告；
- 所有平台共用同一套数据模型、规则和脚本，没有按模型分叉的业务逻辑。

> 工具只能保证"文件格式正确、占位符/日期/重复等可自动检查的项目"。事实是否真实、成果是否有依据、是否夸大等**必须由你确认**，工具不会替你通过。

## 2. 主要功能

创建 / 优化 / 按 JD 定制 / 换风格 / 中英文及其他语言 / 导出与检查；5 种真正不同的视觉模板；三级质量报告（A 自动可验证 · B 需人工确认 · C 环境不可验证）；
状态模型 `draft → needs_review → validated → ready_to_submit`；统一占位符 `{{MISSING:字段名}}`；默认不覆盖文件。

## 3. 架构

```
core/ 与 references/   规则与知识（平台无关，按需加载）
adapters/              各平台入口：SKILL.md、PROMPT.md、AGENTS.md.example
resume_design/         引擎库（数据模型、Markdown/DOCX、校验、PDF、安全）
scripts/               命令行：generate / validate / export_pdf / inspect_environment / match_jd / install_skill
templates/             content/*.md（章节顺序、写作指引） + styles/*.json（视觉） + i18n.json（本地化）
schemas/               resume.schema.json
tests/ reports/        自动化测试与验收报告（虚构数据）
```

## 4. 目录说明

| 路径 | 用途 |
|---|---|
| `core/workflow.md` `data-model.md` `quality-rules.md` `platform-capabilities.md` | 工作流、数据模型、质量/状态规则、平台兼容矩阵 |
| `references/*.md` | 写作、视觉、国际化、ATS、质检、隐私、平台适配 |
| `templates/styles/*.json` | ats-clean / technical / management / modern-business / creative 样式（与内容分离，可单独修改） |
| `templates/selection-rules.json` | 自动选模板规则的覆盖项（可配置，用户指定永远优先） |
| `examples/` | 虚构示例简历（中文 md、英文 json）与 JD |

## 5. 环境要求

Windows 10/11（主要测试平台），Python ≥ 3.9。生成 Markdown/DOCX 无需任何第三方包。
PDF 需要本机已安装 **Microsoft Word**（COM 自动化）或 **LibreOffice**；PDF 文本/字体核验使用 `pdftotext`（可选，Git for Windows 自带一份）或 `pypdf`（可选）。

## 6. 最小依赖与可选依赖

- 必需：Python 标准库。
- 可选（`pip install -e .[extras]`）：`python-docx`、`pypdf`（交叉验证）；开发：`pytest`（测试同样可用 `python -m unittest`）。
- 工具**不会**自动安装任何软件，也不修改系统设置。

## 7. Windows 安装方法

```bash
# 获取代码
git clone https://github.com/lllllukewatchme-alt/truthful-resume.git
cd truthful-resume

# 在项目目录内创建虚拟环境（可选，仅标准库时可跳过）
python -m venv .venv
.venv\Scripts\activate
python scripts/inspect_environment.py
```

`inspect_environment.py` 参数：`--json`、`--report`、`--force`。缺依赖时只会打印虚拟环境内的安装命令，不会全局安装。

安装为 Skill（先预览，默认不覆盖）：

```bash
python scripts/install_skill.py --target claude-code-user --dry-run
python scripts/install_skill.py --target claude-code-user
```

`install_skill.py` 参数：`--target`（`claude-code-user` / `claude-code-project` / `codex-user` / `codex-project`）、`--project-dir`、`--home`（测试用）、`--dry-run`、`--backup`。
目标已存在时默认停止；`--backup` 会把旧目录改名为 `resume-design.bak-<时间>`（不删除任何文件）。

## 8. Claude Code 使用方法

- 个人级：`~/.claude/skills/resume-design/`；项目级：`<项目>/.claude/skills/resume-design/`（依据 Claude Code 官方技能文档）。
- 安装：`python scripts/install_skill.py --target claude-code-user`（项目级加 `--target claude-code-project --project-dir <项目>`）。
- 重启会话后直接说"帮我做一份简历"，或输入 `/resume-design`。技能通过 `${CLAUDE_SKILL_DIR}` 调用脚本。
- **状态：依据规范实现，尚未在 Claude Code 中实际调用测试**（见 `core/platform-capabilities.md`）。

## 9. Codex 使用方法

- 用户级：`~/.agents/skills/resume-design/`；仓库级：`<仓库>/.agents/skills/resume-design/`（依据 Codex 官方技能文档；Codex 的发现目录与 Claude Code 不同）。
- 安装：`python scripts/install_skill.py --target codex-user`（或 `codex-project --project-dir <仓库>`）。可把 `adapters/codex/AGENTS.md.example` 复制为项目的 `AGENTS.md` 并按需修改。
- **状态：依据规范实现，本机未安装 Codex CLI，尚未实际调用测试。** 沙箱可能限制 Word COM 或工作区外写入，被拒绝时请按提示处理。

## 10. DeepSeek 使用方法

把 `adapters/deepseek/PROMPT.md` 中"---"之后的内容作为第一条消息（API 中作为 system）。模型输出 `resume.json`，你保存后在本地运行第 17 节命令。
**人工流程，未实测**；纯聊天模型不能生成文件或控制电脑。

## 11. 豆包使用方法

把 `adapters/doubao/PROMPT.md` 中"---"之后的内容作为第一条消息，或放入自建智能体的人设中。同样由你在本地运行脚本。**人工流程，未实测**。

## 12. 通用大模型使用方法

使用 `adapters/generic/PROMPT.md`。如果模型带有本地终端/代码执行能力，可让它运行脚本；没有则按"模型出 JSON → 你本地生成"流程。**未实测**。

## 13. 如何创建简历

对话方式：告诉模型目标岗位和经历，它会分组提问，缺失处用 `{{MISSING:字段}}`。
手工方式：复制 `examples/sample_resume.json`（或 `.md`），改成自己的内容后生成（第 17 节）。

## 14. 如何优化简历

把旧简历文字贴给模型；模型只改表达不改事实，改写内容标 `ai_suggested`，并给出修改前后对照；你确认后改为 `user_confirmed`。
不会读取旧 DOCX/PDF 的版式（v1 只提取文字，原版式不保留）。

## 15. 如何根据 JD 定制简历

```bash
python scripts/match_jd.py --input examples/sample_resume.md --jd examples/sample_job_description.md
```

`match_jd.py` 参数：`--input`、`--jd`、`--report`、`--force`、`--json`。输出 满足 / 部分满足 / 缺少证据 三类（启发式，必须人工确认），**不会**为提高匹配度添加你没有的经历。
另可同时生成 ATS 版本：`generate_resume.py --template ats-clean`。

## 16. 如何切换模板

`--template ats-clean|technical|management|modern-business|creative`；不指定时按 `references/visual-design.md` 的规则自动选择（用户指定 > `--ats-submission` > 岗位关键词 > 默认 modern-business），规则可在 `templates/selection-rules.json` 覆盖。
`creative` 为双栏、非 ATS 友好，请同时生成 `ats-clean` 版本。

## 17. 如何生成 Markdown、DOCX 和 PDF

```bash
python scripts/generate_resume.py --input examples/sample_resume.md --output-dir out --formats md,docx
python scripts/generate_resume.py --input examples/sample_resume.json --output-dir out --formats md,docx,pdf --template ats-clean
python scripts/generate_resume.py --input examples/sample_resume.json --dry-run
python scripts/export_pdf.py --input out/sample_resume.docx --backend word
```

`generate_resume.py` 参数：

| 参数 | 说明 |
|---|---|
| `--input` | 简历源文件（.md 或 .json）【必需】 |
| `--output-dir` | 输出目录，不存在自动创建（默认 `out`） |
| `--prefix` | 输出文件名前缀（默认输入文件名） |
| `--template` | 模板名；省略则自动选择 |
| `--lang` / `--locale` | 简历语言（zh/en）/ 目标地区（zh-CN、en-US、en-GB…） |
| `--formats` | `md,docx,pdf` 的任意组合（默认 `md,docx`） |
| `--pdf-backend` | 强制 `word` 或 `libreoffice` |
| `--ats-submission` | 在线投递，自动选 ats-clean |
| `--clean-metadata` | DOCX 去掉时间戳等元数据 |
| `--paper` | 覆盖纸张（A4/Letter）；默认随 locale |
| `--allow-draft` | 有校验错误时仍生成草稿 |
| `--confirm-ready` | **人工确认**：你已核对事实、联系方式和目标岗位；配合数据里的 `meta.review.*` 才能得到 `ready_to_submit`（AI 助手不得擅自添加） |
| `--dry-run` | 只预览，不写文件 |
| `--force` | 仅覆盖明确的目标文件 |
| `--report` | 报告 JSON 路径（默认 `<输出目录>/<前缀>.report.json`） |
| `--json` | 以 JSON 输出最终摘要 |

`export_pdf.py` 参数（`--timeout` 必须是 ≥1 的整数；超时后只会关闭本次导出自己启动的 Word 进程，不会碰你已打开的 Word）：`--input`（.docx）、`--output-dir`、`--prefix`、`--backend`（word/libreoffice）、`--dry-run`、`--force`、`--report`、`--timeout`。
后端顺序：显式指定 → Microsoft Word → LibreOffice → 明确失败（退出码 4）。文件名冲突时自动加 `-1`，不覆盖。

**退出码（所有脚本一致）**：`0` 成功 · `2` 输入/参数错误 · `3` 依赖缺失 · `4` 生成或导出失败（若部分文件已生成会明确报告"部分成功"及失败阶段） · `5` 校验未通过。

## 18. 如何运行质量检查

```bash
python scripts/validate_resume.py --input examples/sample_resume.json --docx out/sample_resume.docx --pdf out/sample_resume.pdf --report out/check.json
python scripts/validate_resume.py --input zh.json --compare en.json
python scripts/validate_resume.py --input examples/sample_resume.md --strict
```

`validate_resume.py` 参数：`--input`、`--docx`、`--pdf`、`--compare`、`--lang`、`--locale`、`--confirm-ready`、`--strict`、`--report`、`--force`、`--json`。
报告分三块：**A 自动检查**（占位符、日期、必需章节、重复、DOCX/PDF 结构、文本与中文保留、字体嵌入…）、**B 需要你确认**（事实、成果依据、夸大、JD 匹配、翻译…，永不自动通过）、**C 当前环境无法验证**（真实分页、他人 Word 版本、目标 ATS、缺失字体）。

状态：`draft`（有阻断错误）→ `needs_review`（有占位符或未确认 AI 改写）→ `validated`（自动检查通过）→ `ready_to_submit`（你确认了事实、联系方式、目标岗位：数据里 `meta.review.*` 全为 true，**并且**你在命令行加了 `--confirm-ready`；若要求 PDF 则 PDF 通过）。PDF 页数超过 `page_limit` 时状态为 `needs_review`。不支持的 `--lang`（目前 zh/en）会被拒绝（退出码 2），未知 locale 会给出可见警告。**文件生成成功 ≠ 可直接投递。**
PDF 状态：`passed` · `failed` · `blocked_by_environment` · `not_tested`。

占位符标准：`{{MISSING:phone}}`（唯一格式）。

## 19. 如何运行测试

```bash
python -m unittest discover -s tests -v
python scripts/run_acceptance.py
```

测试只用虚构数据和临时目录。PDF 测试按环境矩阵执行：无后端 → 验证退出码 4 与失败报告；有 Word → 真实导出并核验；有 LibreOffice → 真实导出并核验。缺少的后端会显示为 `skipped: blocked_by_environment`，**不会**算作通过。
`run_acceptance.py` 运行全部测试和场景并写 `reports/acceptance-report.md`、`reports/skill-scenarios.md`（参数：`--force` 覆盖旧报告）。

## 20. PDF 后端缺失时的解决办法

退出码 4，并打印已检测的后端、失败原因和替代方案：① 用 Word/WPS 打开 `.docx` 另存为 PDF；② 自行安装 LibreOffice 后运行 `python scripts/export_pdf.py --input <文件>.docx --backend libreoffice`；③ 暂时只使用 DOCX。工具**不会**静默安装软件，也**不会**生成假 PDF。

## 21. 隐私和安全说明

本地处理；不联网（测试强制检查）；报告与日志对邮箱/手机号/身份证号脱敏，不含完整简历；绝不修改输入文件（哈希核对）；先写临时文件、校验后再落盘；默认不覆盖，`--force` 只覆盖指定文件；
路径与前缀有安全校验；简历文字只作数据、不会被当命令执行；DOCX 不写作者信息。详见 `references/privacy-security.md`。

## 22. 当前限制

- 不读取旧 DOCX/PDF 版式；不支持照片嵌入；创意模板双栏不适合 ATS。
- Claude Code、Codex、DeepSeek、豆包均**未在平台内实测**，仅文件与规范层面的静态检查（见 `core/platform-capabilities.md`）。
- 仅在 Windows 11 + Python 3.12 + Word 16 上测试；LibreOffice 路径本机未安装，状态为 `blocked_by_environment`。
- 分页、不同 Word 版本差异、目标 ATS 解析属于无法离线验证的项目。
- JD 匹配是关键词启发式，需人工判断。

## 23. 版本更新和回滚方法

- 更新：获取新版本目录 → `python scripts/install_skill.py --target <目标> --dry-run` 预览 → 加 `--backup` 安装（旧版本被改名保留）。
- 回滚：删除/改名新的 `resume-design` 文件夹（由你操作），把 `resume-design.bak-<时间>` 改回 `resume-design`。
- 版本记录：`VERSION`、`CHANGELOG.md`；数据文件（resume.json）与工具版本无关，可直接复用。

## 24. 常见问题（FAQ）

**它会替我编造经历或证书吗？** 不会。缺失信息保留为 `{{MISSING:字段}}`；AI 改写标为待确认；要求添加没有的证书会被工具拒绝（校验错误）。但"事实是否真实"最终只能由你确认。

**生成了文件就能直接投递吗？** 不能。状态要经过 `draft → needs_review → validated → ready_to_submit`；最后一步需要你在命令行加 `--confirm-ready` 并在数据里确认事实、联系方式和目标岗位。

**没有 Word / LibreOffice 能用吗？** 能生成 Markdown 和 DOCX。导出 PDF 会以退出码 4 明确失败并给出替代办法，不会生成假 PDF。

**需要联网或 API Key 吗？** 不需要。工具不联网、不调用模型 API；对话部分由你使用的 AI 助手完成。

**支持哪些语言和地区？** 简历语言目前 `zh`、`en`；地区规则见 `templates/i18n.json`，可自行扩展。

**ATS 友好吗？** `ats-clean` 模板为单栏、无表格；`creative` 为双栏，不适合 ATS。无法离线验证具体招聘系统的解析结果。

**怎样确认某个平台真的可用？** 看第 "平台兼容状态" 表。凡标"未实测"的，请自行验证后再依赖，也欢迎提交验证结果。

## 25. 反馈、参与贡献与安全

- **反馈与建议**：优先在 GitHub Issues 提交（请只附虚构示例数据，不要附真实简历）；也可发邮件到 lllllukewatchme@gmail.com。

- 贡献方式、测试要求和代码规范：`CONTRIBUTING.md`
- 漏洞报告与密钥/个人数据注意事项：`SECURITY.md`
- 许可证：MIT，见 `LICENSE`
