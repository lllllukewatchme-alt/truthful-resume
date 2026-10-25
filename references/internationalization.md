# Internationalisation

`lang` = language of the text (`zh`, `en`; add more labels in `templates/i18n.json`).
`locale` = target market (`zh-CN`, `en-US`, `en-GB`, …) — controls dates, name order, paper, warnings.

| Locale | Date style | Name order | Paper | Length hint | Notes |
|---|---|---|---|---|---|
| zh-CN / zh-TW | `2021.03` | family+given | A4 | 2 pp | Photos customary in some sectors; never added without user input |
| en-US | `Mar 2021` | given family | Letter | 1 p (<10 yrs) | No photo/age/marital status/ID |
| en-GB / en-AU / en-SG | `Mar 2021` | given family | A4 | 2 pp | "CV" wording; no photo |
| en-CA | `Mar 2021` | given family | Letter | 2 pp | |
| other | ISO `2021-03` | given family | A4 | 2 pp | generic; confirm conventions with the user |

## Rules
- Do not translate degree names into "equivalent" foreign degrees on your own; show the original name (+ literal translation) and ask.
- Never add visa status, work authorisation, nationality, age, gender, marital status, ID numbers, or photo unless the user asks and the market expects it.
- Phone numbers are kept as given. For overseas applications the validator suggests adding a country code (info only).
- Keep company/school proper names in the original language the first time; add a translation in parentheses only if user confirms.
- Titles with no direct equivalent (e.g. 事业部总经理): propose 1–2 options, ask which the user's employer uses.
- Bilingual output = two renderings of two aligned data files; run `validate_resume.py --input zh.json --compare en.json`
  to prove dates, entry counts, numbers and contacts did not drift.
- `name_parts` + locale `name_order` controls display order (`林 远` family+given for zh; `Yuan Lin` for en).
- Uncertain culture-specific content → ask, do not guess.
