# Workflow (platform-independent core)

Every platform adapter points here. The model supplies language and judgement; the Python engine
(`scripts/`) supplies deterministic generation, validation and export.

## 1. Classify the request

| Intent | Typical user words | Mode |
|---|---|---|
| create | "help me write a resume", "I have no resume" | A. Create from scratch |
| improve | "polish / optimise my resume" (pastes text or file) | B. Improve existing |
| tailor | "for this job", pastes a JD | C. Tailor to JD |
| restyle | "make it prettier", "ATS version", "change template" | D. Restyle (no content change) |
| translate | "English version", "bilingual" | E. Translate / localise |
| export | "give me Word/PDF" | F. Export only |
| check | "is this ready to send?" | G. Quality check |

If the user only has an old DOCX/PDF: extract the text yourself (or ask them to paste it), tell them layout
will not be preserved, then continue as B. v1 does not read DOCX/PDF automatically.

## 2. Collect facts (create / gaps)

Ask short, grouped questions; never demand everything at once. Priority order:
1. name + at least one contact (email or phone) + target role;
2. most recent 1-2 experiences (organisation, title, dates, what they did, any numbers they can *prove*);
3. education; 4. skills; 5. optional: projects, certificates, languages, awards.

Rules
- Anything the user did not give becomes a placeholder `{{MISSING:<field>}}`. Never invent it.
- If the user declines an optional item ("skip"), remove it; do not ask again.
- Record where numbers come from in `evidence`; set `confirmation_status` (see data-model.md).

## 3. Build the structured data

Write `resume.json` (preferred) or `resume.md` in the working folder. Keep **one** data source; all templates
and languages are renderings of it. Original wording stays in `bullets[].original` when you rewrite
(object bullets), rewrites start as `ai_suggested` until the user approves.

## 4. Choose template

Order: explicit user choice → online/ATS submission (`ats-clean`) → role-based rules in
`templates/selection-rules.json` / `references/visual-design.md` → default `modern-business`.
Creative template: always also offer an `ats-clean` file.

## 5. Generate

```
python scripts/generate_resume.py --input resume.json --output-dir out --formats md,docx[,pdf] \
       [--template NAME] [--lang zh|en] [--locale zh-CN|en-US|en-GB] [--ats-submission]
```
Read the printed report. Exit codes: 0 ok, 2 bad input/args, 3 missing dependency, 4 generation/export failed
(partial success is announced), 5 validation errors.

## 6. Check and report

`python scripts/validate_resume.py --input resume.json --docx out/<file>.docx [--pdf out/<file>.pdf]`

Report to the user in three blocks, never merged:
- **A automated** results (errors / warnings / placeholders);
- **B needs your confirmation** (facts, metrics, wording, JD match, translation, final contact check);
- **C cannot be verified here** (pagination without PDF, other Word versions, the employer's ATS, missing fonts).

## 7. Status

`draft` → `needs_review` → `validated` → `ready_to_submit` (rules in quality-rules.md). Say the status in
plain words. Never say "ready to submit" because a file was produced.

## 8. Iterate

Edit the data (not the generated files), regenerate. Facts (dates, titles, numbers) must not change between
versions unless the user says so; for bilingual pairs run
`validate_resume.py --input a.json --compare b.json`.
