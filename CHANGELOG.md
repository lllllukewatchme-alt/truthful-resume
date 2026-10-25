# Changelog

## 0.2.0 - 2026-10-25
- Six new templates (11 in total): `harvard` (classic, education-first), `banner` (full-width header band), `sidebar-dark` (dark sidebar with contact/skills),
  `timeline` (vertical line down every entry), `date-left` (Europass-style date column), `developer-mono` (`// section` monospace look).
  Layouts follow common résumé conventions; the style files are original, no third-party template files were copied.
- Renderer options (all optional, defaults unchanged): `heading.prefix/align/left_bar`, `header.style=band`, `layout.sidebar_fill/sidebar_text/sidebar_heading/sidebar_contact`,
  `layout.entry_style=timeline|date_left`, `layout.date_col_mm`.
- New richer fictional examples: `examples/sample_resume_rich.json` (English, product designer) and `examples/sample_resume_rich.md` (Chinese, tech manager).
- `harvard` is auto-selected for academic roles (professor, postdoc, lecturer, 教授, 讲师, 博士后).

## 0.1.4 - 2026-10-25 (first public release)
First public release of the repository `truthful-resume` (skill/package name `resume-design`), MIT licensed.

Features: create / improve / JD-tailor / translate resumes (zh, en); Markdown, DOCX and PDF output; five templates; three-tier quality
report and status model; placeholders for missing facts; overwrite protection; offline, standard-library-only engine; adapters for
Claude Code, Codex, DeepSeek, Doubao and generic prompts.

Known limitations (also in README): PDF export verified only with Microsoft Word 16 on Windows 11 / Python 3.12; LibreOffice, macOS/Linux
and older Python versions are untested; the Claude Code / Codex skills were checked statically but not exercised inside those products;
no DOCX/PDF import; no photo embedding; creative template is not ATS-safe; JD matching is a keyword heuristic.

Changes since the internal 0.1.3 build:
- P1-8 (audit F12, confirmed): after a Word export timeout the Word process stayed alive (and kept the .docx locked). The export script now records the PID of the Word instance it started and, on timeout, closes exactly that process (plus a windowless, newly started Word as fallback); a Word that was already running is never touched. PowerShell/soffice are killed as a process tree. Test hook `RESUME_DESIGN_TEST_WORD_HANG=1` simulates a hung Word.
- P1-7 test gaps closed (`tests/test_gaps.py`, 20 tests): backend exits 0 without output / with an empty or junk PDF / with a valid PDF of the wrong text; CJK text lost in a PDF; installer `--dry-run` fingerprints (existing install, siblings, project targets); hostile-input exit-code contract for every script; real-Word page-1 fill and long-resume checks for all five templates.
- Fixes found by those tests: `--report` pointing into an impossible folder is a clear exit-2 error (generate checks it before generating); `inspect_environment.py` no longer crashes on a bad `--report`; `export_pdf.py --timeout` must be a whole number >= 1.

## 0.1.3 - 2026-10-25
- P1-3 (audit F7): a verified PDF with more pages than `preferences.page_limit` now yields status `needs_review` (finding `pdf.page_limit`, reason lists the page counts), in `generate_resume.py` and in `validate_resume.py --pdf`; `--strict` fails on it.
- P1-4 (audit F8): `ready_to_submit` needs the human to pass the new `--confirm-ready` flag (generate/validate) in addition to `meta.review.*` in the data; data flags alone give `validated`. Reports record `confirmed_via_cli`. Both SKILL.md files forbid passing it unprompted. (Behaviour change: earlier versions reached `ready_to_submit` from data flags alone.)
- P1-5 (audit F10): unsupported languages (from `--lang` or `target.language`) are rejected with exit 2 and a message listing supported ones; `locale.unknown` is now a visible warning.

## 0.1.2 - 2026-10-25
- P1-1 (audit F4): the two-column `creative` template no longer leaves page 1 empty for resumes longer than one page. Cause (reproduced in Word): keep-with-next paragraphs inside table cells made Word move the whole table row to page 2; keep-with-next is now switched off inside cells. Sidebar certificates/awards are stacked (name, then issuer/date) so dates no longer wrap mid-date.
- P1-2 (audit F5): in a Markdown entry heading only a field that is *entirely* a date or date range is the date (the last such field); a year inside a role or location (`Lead of 2021 Migration`) is text. Month-name dates only match real month names.
- Tests: `tests/test_regressions.py` P11/P12 (including a real-Word check that page 1 of a long creative resume is filled).

## 0.1.1 - 2026-10-25
Fixes from the 2026-10-25 engineering audit (P0-1..P0-4, P1-6). New regression tests: `tests/test_regressions.py`.
- P0-1: a target/report path that is the input file is refused (exit 2) - `generate_resume.py --force`, and `--report` of every script. Case/link variants are detected.
- P0-2: unrecognised Markdown sections are reported as warning `section.unknown` (visible in the console report) and keep the status at `needs_review`.
- P0-3: dates in lenient forms (`2020-5`, `May 2020`, `2020/05`) are canonicalised before rendering; line breaks inside single-line fields are collapsed to one space; `|` inside names is escaped as `\|` in Markdown. A Markdown round-trip failure no longer blocks DOCX/PDF (partial success, exit 4, `failed_stage: md`).
- P0-4: wrong data types no longer crash (schema error, exit 5); unpaired surrogates are rejected (exit 5); I/O errors such as a locked target become exit 4 with a clear message; every script has a last-resort handler (exit 4, one-line redacted message, no traceback).
- P1-6: both SKILL.md files now require reading `core/workflow.md`/`core/data-model.md` first, reporting files only if `generated:` was printed, treating non-zero exit as failure, and never using `--force` unprompted.
- Fixed a latent false positive: `target.*` fields (not printed) were counted as expected DOCX/PDF text.

## 0.1.0 — 2026-10-25
Initial release.
- Canonical data model + JSON schema; Markdown ⇄ JSON conversion with round-trip guard.
- Stdlib DOCX writer (OOXML) with 5 style configs (ats-clean, technical, management, modern-business, creative); locale-aware dates/paper/name order.
- `generate_resume.py`, `validate_resume.py`, `export_pdf.py`, `inspect_environment.py`, `match_jd.py`, `install_skill.py`.
- PDF via Microsoft Word COM (tested) and LibreOffice headless (implemented, not tested here); PDF verification (structure, pages, text, CJK, fonts).
- Three-tier quality report (A automated / B manual / C environment) and status model.
- Adapters: Claude Code, Codex (spec-based, not invoked in the platforms), DeepSeek, Doubao, generic (manual prompts).
- Known limits: no DOCX/PDF import, no photo embedding, single-user sandbox tests only on Windows 11.
