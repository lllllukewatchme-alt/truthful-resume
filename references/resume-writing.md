# Resume writing reference

Load when drafting or improving content.

## Bullet pattern
`Verb + what/scope + how (tool/method) + result` — only parts the user can support.
- Weak: "Responsible for order system." → Stronger (no new facts): "Designed and iterated the order-center service."
- Add scale/result **only** from the user: ask "How many orders/users/servers? Before → after? Source?"
- If unknown, keep the plain statement and add a visible `{{MISSING:experience[0].bullets[0].metric}}` only when the user wants to supply it.

## Improving an existing resume
1. Fix grammar/typos/inconsistent tense; unify date format and punctuation.
2. Merge duplicates; split bullets that carry 2+ ideas; remove filler ("hard-working", "team player") unless evidenced.
3. Flag vague/unsupported lines to the user as questions, do not "fix" them by inventing.
4. Keep `original` text for rewritten bullets (object bullets) and mark them `ai_suggested`.
5. Provide a short before/after diff list (what changed, why) and call out anything that touches a fact.

## Section guidance
- Summary: 2–4 lines: role identity, years (if given), 2–3 proven strengths, target direction.
- Experience: reverse chronological; 3–6 bullets recent, 1–3 older; gaps in dates are the user's to explain.
- Projects: name, role, stack, outcome; skip if experience already covers it.
- Skills: group by category; list only tools the user actually uses; never pad with JD keywords the user lacks.
- Education: new graduates first; include GPA/ranking only if user provides it.
- Certificates/awards: name, issuer, date; fabricated or unverifiable items are refused.

## Career situations
- New graduate: education first (`meta.section_order`), projects/internships carry the page.
- Career changer: summary states the transition honestly; lead with transferable, evidenced work.
- Executive: scope (team, budget, P&L) with user-confirmed numbers; 2 pages max.
- Gaps: do not hide or invent; neutral dates, user decides the explanation.

## Refusal pattern (fake credentials/metrics)
Say what cannot be done and why in one sentence, then offer: list as "in progress", describe the real related work,
mark `{{MISSING:…}}` until proof exists, or suggest legitimate ways to earn it. Never write it into the data.
