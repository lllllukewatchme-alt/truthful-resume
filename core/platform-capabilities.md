# Platform capability matrix

Status vocabulary: **tested** (actually run on this project) · **spec-based** (written to the platform's
published spec, not run on the platform) · **manual** (user performs steps) · **unsupported**.
"Looks similar" is never counted as verified. Last updated for v0.1.4 (first public release).

## Engine (platform independent)

| Capability | Status | Evidence |
|---|---|---|
| Markdown ⇄ JSON, Markdown/DOCX generation | **tested** | `tests/` (Windows 11, Python 3.12) |
| DOCX structure (OOXML) check | **tested** | `tests/test_generate_resume.py` |
| PDF via Microsoft Word COM | **tested** on Windows 11 + Word 16.0 (real export, text/CJK/fonts verified) | `reports/` |
| PDF via LibreOffice `--headless` | **blocked_by_environment** (not installed here; code path implemented, unit-checked with a stub only) | `reports/` |
| Any PDF backend absent → exit 4 + report | **tested** | `tests/test_export_pdf.py` |
| macOS/Linux | **not tested** (stdlib only; Word path is Windows-only; LibreOffice path untested) | – |

## Agent platforms

| Platform | Entry file | Install | Status |
|---|---|---|---|
| Claude Code | `adapters/claude-code/SKILL.md` | `.claude/skills/resume-design/` (project) or `~/.claude/skills/resume-design/` (user) via `scripts/install_skill.py` | **spec-based**: frontmatter/paths checked against code.claude.com/docs/en/skills (2026-10-25); SKILL.md lint tested; **not invoked inside Claude Code** |
| OpenAI Codex | `adapters/codex/SKILL.md` + `AGENTS.md.example` | `.agents/skills/resume-design/` (repo) or `~/.agents/skills/resume-design/` (user) | **spec-based**: checked against Codex skills docs (2026-10-25); Codex CLI not installed here; **not invoked in Codex** |
| DeepSeek (web/app/API) | `adapters/deepseek/PROMPT.md` | paste as system/first message | **manual**; untested. Chat-only unless you run the scripts yourself or use an agent with shell access |
| Doubao (豆包) | `adapters/doubao/PROMPT.md` | paste as first message / bot persona | **manual**; untested. File generation needs the user to run the scripts locally |
| Other LLMs | `adapters/generic/PROMPT.md` | paste | **manual**; untested |

Capability differences that matter

| | Reads local files | Runs scripts | Produces DOCX/PDF itself |
|---|---|---|---|
| Claude Code / Codex (agent with shell) | yes | yes | yes, via scripts |
| Chat-only models (DeepSeek/Doubao web) | only pasted text | no | **no** — model outputs the JSON/Markdown; user runs the scripts (Windows commands in README) |

A prompt alone cannot control a local computer; chat-only flows end with "copy this JSON to a file and run …".
