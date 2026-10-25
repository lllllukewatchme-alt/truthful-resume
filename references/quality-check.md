# Quality check procedure

Run after every generation: 
`python scripts/validate_resume.py --input <data> --docx <file.docx> [--pdf <file.pdf>] [--report out/check.json]`

## Reading the report
- `status` — draft / needs_review / validated / ready_to_submit (rules: core/quality-rules.md).
- **[A]** findings: `error` blocks (exit 5), `warning` should be resolved or explained, `info` is advice.
  Ids: `schema`, `required.*`, `placeholder`, `date.*`, `empty.*`, `duplicate.paragraph`, `format.*`, `lang.mismatch`,
  `fabrication.certificate`, `docx.*`, `pdf.verify`, `compare.*`.
- **[B]** list: present each item to the user as a question; record answers in the data (`confirmation_status`, `evidence`,
  `meta.review.*`). Never tick them yourself.
- **[C]** list: state limits plainly (e.g. "page count unverified: no PDF backend").

## Typical fixes
| Finding | Action |
|---|---|
| `placeholder` | ask the user for the value or confirm removal; do not guess |
| `date.format` / `date.order` | confirm the real dates with the user |
| `duplicate.paragraph` | merge or rewrite; keep both only if truly distinct |
| `docx.cjk_loss` / `pdf.verify` CJK missing | font problem: check installed CJK fonts (`inspect_environment.py`) |
| PDF warning "fonts not embedded" | use Word backend/embeddable fonts; report as limitation |
| `page limit exceeded` | trim older bullets (with user consent), reduce template density, or accept 2 pages |
| `compare.*` | versions drifted: fix the data, never "average" the differences |

## Before telling the user it is ready
1. status is `validated` (or `ready_to_submit` after explicit user confirmations);
2. every B item was shown to the user; 3. C limits were stated; 4. for PDF: status `passed`, not `blocked_by_environment`.
