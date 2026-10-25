# 任务场景测试记录 / Skill scenarios

范围说明：本文件记录 10 个任务场景对**工具链**（真实 CLI）的验证。涉及模型对话的部分（提问、改写、口头拒绝）需要真实模型，**未测试**。
未做 with/without Skill 的基线比较（无法在此环境对模型运行评测）。

通过 10/10

## S01 Create a Chinese technical resume from scratch — ✅ 通过

- 输入：zh JSON (role=后端开发工程师), no template given
- 预期：exit 0; auto template=technical; DOCX has Chinese + English text; status validated
- 实际：exit 0; template=technical; status=validated
- 范围备注：Model dialogue/behaviour not tested (needs a live model); toolchain behaviour tested.

## S02 Improve existing experience without changing facts — ✅ 通过

- 输入：sample resume; wording rewrite (ai_suggested) vs. a rewrite that adds '500 台终端'
- 预期：faithful rewrite: no fact drift, status needs_review (unapproved); invented number -> compare.numbers error
- 实际：drift errors=0; status=needs_review; invented-number errors=['compare.numbers']
- 范围备注：Model dialogue/behaviour not tested (needs a live model); toolchain behaviour tested.

## S03 Tailor to a JD (sample JD requires Rust/C++ which the resume lacks) — ✅ 通过

- 输入：sample_resume.md + sample_job_description.md; generate ATS version
- 预期：Rust/C++ requirement reported as missing_evidence; generated resume does not contain Rust/C++
- 实际：counts={'satisfied': 4, 'partial': 0, 'missing_evidence': 3, 'needs_human': 0}; 'Rust' in output=False; template=ats-clean
- 范围备注：Model dialogue/behaviour not tested (needs a live model); toolchain behaviour tested.

## S04 Chinese + English versions of the same facts — ✅ 通过

- 输入：zh.json, en.json (same dates/contacts/numbers); then en with a changed number
- 预期：both generate with their own labels/date style; --compare passes; changed number -> exit 5
- 实际：gen=0,0; compare=0; drifted compare=5
- 范围备注：Model dialogue/behaviour not tested (needs a live model); toolchain behaviour tested.

## S05 ATS-clean and modern-business versions from one data file — ✅ 通过

- 输入：same zh.json, two templates
- 预期：both succeed; same content; ATS has no tables, CAPS headings, no shading; modern uses shaded section bands
- 实际：exit 0,0; tables 0,0; ats caps=True
- 范围备注：Model dialogue/behaviour not tested (needs a live model); toolchain behaviour tested.

## S06 Missing contact details stay as placeholders — ✅ 通过

- 输入：phone/email = {{MISSING:...}}
- 预期：generated draft keeps both placeholders (highlighted), listed in report, status needs_review (not ready)
- 实际：exit 0; placeholders=2; status=needs_review
- 范围备注：Model dialogue/behaviour not tested (needs a live model); toolchain behaviour tested.

## S07 No PDF backend available (simulated: Word and LibreOffice disabled) — ✅ 通过

- 输入：generate --formats md,docx,pdf
- 预期：exit 4; partial success reported (md+docx exist); pdf_status=blocked_by_environment; no PDF file; alternatives printed
- 实际：exit 4; pdf_status=blocked_by_environment; failed_stage=pdf; alternatives printed=True
- 范围备注：Backend absence is simulated via RESUME_DESIGN_DISABLE_BACKENDS; Model dialogue/behaviour not tested (needs a live model); toolchain behaviour tested.

## S08 Malformed input — ✅ 通过

- 输入：bad JSON, .pdf as input, missing file, --formats xls, impossible date
- 预期：exit 2 for input/arg errors; exit 5 for validation failure (invalid date)
- 实际：{'malformed json': 2, 'unsupported extension': 2, 'missing file': 2, 'bad format arg': 2, 'invalid date': 5}
- 范围备注：Model dialogue/behaviour not tested (needs a live model); toolchain behaviour tested.

## S09 User asks to add a certificate they do not hold — ✅ 通过

- 输入：certificate entered as ai_suggested/unconfirmed (what a non-compliant draft would look like)
- 预期：validation error fabrication.certificate: exit 5, no resume files; after removal generation succeeds
- 实际：exit 5; files=['r.report.json']; after removal exit 0
- 范围备注：The refusal wording and the offer of honest alternatives are model behaviour and are NOT tested. Tested: the toolchain refuses to render an unconfirmed certificate.

## S10 Overwrite protection and privacy-safe logs — ✅ 通过

- 输入：generate twice into the same folder
- 预期：first outputs untouched; second run uses r-1.*; no email/phone in stdout/stderr/report
- 实际：original unchanged=True; r-1.docx exists=True; leaked=[]
- 范围备注：Model dialogue/behaviour not tested (needs a live model); toolchain behaviour tested.
