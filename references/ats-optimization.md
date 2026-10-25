# ATS and JD tailoring

## JD workflow
1. Save the JD to a file; run `python scripts/match_jd.py --input resume.json --jd jd.md`.
2. Present three groups: **satisfied** (all keywords found), **partial**, **missing_evidence**
   (+ `needs_human` for requirements with no extractable keyword). Say clearly: the matcher is a heuristic.
3. For `partial`/`missing_evidence` ask: "Do you have real experience with X that is not in the resume?"
   Add it only on a yes, with their wording; otherwise leave the gap and suggest honest alternatives (adjacent experience, learning plan outside the resume).
4. Reorder sections/bullets and mirror the JD's terminology **only** where the user's experience truly matches.
5. Produce `ats-clean` for upload plus the designed version for humans; run both through `validate_resume.py`.

## ATS-friendly file checklist
- Single column, no tables/text boxes/images for content; standard headings (Summary, Experience, Education, Skills).
- Contact details in the body; real text (not images); common fonts; consistent dates; bullets as real list items.
- Use the exact job-title/skill terms the user genuinely holds; spell out acronyms once.
- DOCX or text-selectable PDF; avoid scanned/graphic-only PDFs.

## Honest limits
Offline validation cannot reproduce a specific employer's parser (category C). The `ats-clean` template removes the
most common causes of parse errors; it does not guarantee a result. Keyword stuffing and hidden text are not done.
