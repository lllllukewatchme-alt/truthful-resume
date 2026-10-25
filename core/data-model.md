# Data model

Single source of truth: `schemas/resume.schema.json` (draft-07 subset, validated by the engine itself).
Markdown and JSON are two serialisations of the same model; templates never hold data.

## JSON shape (abridged)

```json
{
  "basics":  {"name":"", "name_parts":{"given":"","family":""}, "headline":"", "email":"", "phone":"",
              "location":"", "website":"", "summary":""},
  "target":  {"role":"", "industry":"", "locale":"", "language":"", "job_description":""},
  "education": [], "experience": [], "projects": [],
  "skills": [{"category":"", "items":[""]}],
  "certificates": [{"name":"", "issuer":"", "date":"", "evidence":"", "confirmation_status":""}],
  "languages": [{"language":"", "level":""}],
  "awards": [{"name":"", "date":"", "description":""}],
  "preferences": {"template":"", "page_limit":2, "photo":false},
  "meta": {"section_order":[], "review":{"facts_confirmed":false, "contact_confirmed":false, "target_confirmed":false}}
}
```

`lang` (`target.language`, CLI `--lang`) is the language of the resume text and section labels.
`locale` (`target.locale`, `--locale`) is the target market and drives date style, name order, paper size
and warnings (`templates/i18n.json`). Example: `lang=en`, `locale=zh-CN` is an English resume for a China-based
employer. Unknown locales fall back to generic rules plus an info finding.

### Entry (education / experience / projects)

| Field | Meaning |
|---|---|
| organization | employer / school / project name (required) |
| role | title / degree / project role |
| location, start, end | `start`/`end` stored as `YYYY`, `YYYY-MM` or `present`; input also accepts `2019.07`, `2019/7`, `2019年7月`, `Jul 2019`, `至今`, `Present` |
| description | optional one-paragraph summary |
| bullets | strings, or `{text, original, status}` objects when rewritten |
| evidence | list of strings: where the user's claim comes from (document, statement) |
| confirmation_status | `user_provided` (default), `ai_suggested`, `user_confirmed`, `unconfirmed` |

Original vs suggested vs confirmed: raw user text = `user_provided`; your rewrite = `ai_suggested` (keep
the original in `original`); after the user approves = `user_confirmed`. `ai_suggested` / `unconfirmed`
content keeps the resume at `needs_review`; `ai_suggested` **certificates are a blocking error**.

## Placeholder (the one standard)

`{{MISSING:field}}` — e.g. `{{MISSING:phone}}`, `{{MISSING:experience[0].bullets[1].metric}}`.
Shown highlighted in DOCX, listed in every report, and they keep the status at `needs_review`.
No other placeholder syntax is used or recognised.

## Markdown dialect

```markdown
---
template: technical        # optional front matter: template, lang, locale, page_limit, role, industry
---
# Name
> optional headline
- email: a@b.com           # email/phone/location/website (zh or en labels accepted)

## Summary                 # section headings map via aliases in templates/i18n.json (zh/en)
text

## Experience
### Organisation | Title | 2021.03 – present | City   (the date is the last field that is entirely a date/range)
- bullet
<!-- evidence: payroll record provided by user -->
<!-- status: user_confirmed -->

## Skills
- Category: item, item
## Certifications
- Name | Issuer | 2019-11
## Languages
- English: CET-6
## Awards
- Name | 2020 | description
```
Round trip: `parse_markdown(to_markdown(x))` preserves entries, dates, bullets, contacts (tested). Unknown
sections are reported as warning `section.unknown` (and keep the status at `needs_review`); they are **not rendered**.
A literal `|` inside an organisation/role/location/certificate name is written `\|` in Markdown. Dates are canonicalised
(`2020-5`, `May 2020`, `2020/05` → `2020-05`) and line breaks inside single-line fields (bullets, summary, names) are collapsed
to one space before rendering; wording is never changed.
Not carried in Markdown: per-bullet `status`/`original` objects (use JSON for that).

## Traceability

Facts trace to the user's input via `evidence` + `confirmation_status`; reports store only redacted excerpts.
