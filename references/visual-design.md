# Visual design and template selection

Styles live in `templates/styles/<name>.json` (independent of content). Content ordering lives in
`templates/content/<name>.md`. Change either without touching code.

## Template differences (actual, from the style files)

| Template | Fonts (latin / east-asian) | Body | Margins (mm, T/R/B/L) | Line | Heading | Columns | Palette | Density | ATS-safe |
|---|---|---|---|---|---|---|---|---|---|
| ats-clean | Arial / YaHei | 10.5 | 18/18/16/18 | 1.12 | CAPS + rule, black | 1 | black | normal | yes |
| technical | Calibri / YaHei | 10 | 14/15/13/15 | 1.05 | rule, blue | 1 (skills early) | blue | compact | yes |
| management | Cambria / SimSun | 10.5 | 22/22/20/22 | 1.25 | CAPS + rule, navy; centred header | 1 | navy | spacious | yes |
| modern-business | Calibri / YaHei | 10.5 | 16/17/15/17 | 1.15 | shaded band, teal | 1 | teal | normal | yes |
| creative | Segoe UI / YaHei | 10 | 14/14/14/14 | 1.15 | caps, orange; stacked contact | 2 (sidebar 37%) | orange | normal | **no** |

Style keys: `page`, `fonts`, `spacing`, `colors`, `heading.style` (`rule|caps_rule|band|plain`), `header`, `bullets`,
`layout` (`columns`, `sidebar_side`, `sidebar_width_pct`, `sidebar_sections`), `header_footer`, `pagination`, `ats`.
Paper size follows the locale (`en-US`/`en-CA` Letter, others A4) unless `--paper` is given.

## Automatic selection (configurable)

Order (first match wins) — implemented in `resume_design/templates.py`, overridable via `templates/selection-rules.json`:
1. user explicitly names a template → that template;
2. online / ATS submission (`--ats-submission`) → `ats-clean`;
3. role contains management keywords (director, manager, 总监, 经理, …) → `management`;
4. role contains creative keywords (designer, 设计师, …) → `creative` (and recommend an extra `ats-clean` file);
5. role contains technical keywords (engineer, developer, 工程师, 开发, …) → `technical`;
6. otherwise → `modern-business`.
Management is checked before technical so "Engineering Manager" is treated as management.

## Rules of thumb
- Name 20–28 pt, headings 11–12.5 pt, body 10–10.5 pt; never below 9.5 pt.
- 1 page for <10 years in US/Canada, otherwise ≤2 pages; check `preferences.page_limit` against the PDF page count.
- Single column + standard headings for anything uploaded to an ATS; columns/tables only for human-read files.
- Contact info in the body, not in headers/footers (parsers skip them).
- Two-column (table) layouts must not use keep-with-next inside cells: Word then moves the entire row to the next page (fixed in 0.1.2, regression-tested with a real Word export).
- Layout defects are caught by PDF verification (e.g. a long word broken in a narrow sidebar) — read the warnings.
