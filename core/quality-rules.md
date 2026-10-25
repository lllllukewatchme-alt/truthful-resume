# Quality rules

## Truthfulness (hard rules)

1. Never invent employers, titles, dates, degrees, certificates, metrics, tools, team sizes or achievements.
2. A rewrite may change wording, order and emphasis, **not** facts. "Participated in deployment" must not become
   "led deployment of 500 terminals" unless the user supplied that fact.
3. Quantified claims need a source from the user (`evidence` or user-confirmed). Without it: keep a
   `{{MISSING:...metric}}` placeholder or the plain statement, and ask.
4. If asked to add a fake certificate/job/degree/metric: refuse, explain briefly, offer legitimate options
   (list the course/"in progress" if true, describe real related work, take the exam, ask for the real credential).
5. JD tailoring reorders/emphasises existing, true content. Gaps are reported as gaps.
6. Do not convert degrees to foreign equivalents, and do not add visa/work-permit/nationality, unless the user states it.

## Three-tier reporting (never merged)

- **A automated** — placeholders, dates (format, start ≤ end, future), required sections/contact, duplicates, empty
  bullets, schema, language sanity, DOCX package + text + CJK retention, PDF header/pages/text/fonts, overwrite protection,
  cross-version consistency (`--compare`).
- **B manual** — truth of every fact, evidence for numbers, exaggeration, JD match, keyword naturalness,
  translation fidelity, omissions, contact details and final version. Always listed; never auto-passed.
- **C environment** — real pagination without PDF, other Word versions/WPS, the target ATS, missing fonts.

## Status model

| Status | Rule (computed by `validate.compute_status`) |
|---|---|
| `draft` | any blocking error (missing name/contact/sections, bad dates, fabricated certificate, invalid DOCX…) |
| `needs_review` | no errors, but unresolved `{{MISSING:…}}`, unrendered sections, `ai_suggested`/`unconfirmed` items, or a verified PDF longer than `preferences.page_limit` |
| `validated` | all applicable automatic checks pass and nothing above is pending (B items may remain) |
| `ready_to_submit` | `validated` **and** `meta.review.facts_confirmed`, `contact_confirmed`, `target_confirmed` all true in the data **and** the human passed `--confirm-ready` on the command line (a flag inside a data file can be written by anyone, so it is not enough alone) **and** (if a PDF was requested) PDF status `passed` |

The model sets `meta.review.*` only after the user explicitly confirmed in chat, and `--confirm-ready` is passed only on the user's say-so. Generated files never change status by themselves.

## PDF status vocabulary

`passed` · `failed` (backend ran/available but result unusable) · `blocked_by_environment` (no backend) · `not_tested`.
`blocked_by_environment` is never reported as success.

## Style (content)

Reverse-chronological; 3–6 bullets per role; verb-first, one idea per bullet; consistent tense; no first-person pronouns;
no photos/age/marital status unless the user's market expects it and they provide it (v1 does not embed photos).
Details: `references/resume-writing.md`.
