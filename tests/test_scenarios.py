"""The ten real-task scenarios from the project brief, executed against the real CLI toolchain.

Scope note (recorded in the report): the *dialogue* part of each scenario (the model asking questions, refusing a fake
certificate in words, rewriting text) needs a live model and is NOT tested here. These tests feed the toolchain the data a
compliant model would produce, and check that the toolchain accepts good data and blocks/flags bad data.
"""
import copy
import json
import unittest

from helpers import NO_BACKENDS, ROOT, TempCase, docx_xml, en, run, sha, zh

from resume_design import validate as V
from resume_design.docx_writer import inspect_docx
from resume_design.pipeline import load_resume

SCENARIOS = []  # filled while tests run; consumed by scripts/run_acceptance.py
DIALOGUE_NOT_TESTED = "Model dialogue/behaviour not tested (needs a live model); toolchain behaviour tested."


def record(sid, title, inp, expected, actual, passed, note=DIALOGUE_NOT_TESTED):
    SCENARIOS.append({"id": sid, "title": title, "input": inp, "expected": expected, "actual": actual,
                      "passed": bool(passed), "note": note})


def report_of(case, name="r", out="out"):
    return json.loads((case.tmp / out / f"{name}.report.json").read_text(encoding="utf-8"))


class Scenarios(TempCase):
    def test_s01_create_chinese_technical_resume(self):
        src = self.write_json("r.json", zh())
        p = self.gen(src, "--formats", "md,docx")
        rep = report_of(self)
        text = inspect_docx(self.tmp / "out" / "r.docx")["text"]
        ok = p.returncode == 0 and rep["artifacts"]["template"] == "technical"
        ok = ok and "测试用户" in text and "Java" in text and rep["status"] == "validated"
        record("S01", "Create a Chinese technical resume from scratch", "zh JSON (role=后端开发工程师), no template given",
               "exit 0; auto template=technical; DOCX has Chinese + English text; status validated",
               f"exit {p.returncode}; template={rep['artifacts']['template']}; status={rep['status']}", ok)
        self.assertTrue(ok)

    def test_s02_optimize_without_changing_facts(self):
        original, _, _ = load_resume(ROOT / "examples" / "sample_resume.md")
        improved = copy.deepcopy(original)
        e = improved["experience"][0]
        e["bullets"] = [{"text": "主导设计并迭代订单中心服务，支撑日均 200 万笔订单处理", "original": e["bullets"][0], "status": "ai_suggested"}] + e["bullets"][1:]
        diff = [f for f in V.compare_versions(original, improved) if f["level"] == "error"]
        status = V.build_report(V.check_data(improved), improved, input_name="x", input_sha=None, pdf_status="not_tested",
                                pdf_required=False, ats_safe=True, missing_fonts=[], fonts_detectable=True)["status"]
        # a rewrite that invents a number must be caught
        invented = copy.deepcopy(original)
        invented["experience"][0]["bullets"][1] = "将订单查询接口 P99 延迟由 800ms 优化至 120ms，并负责 500 台终端的自动化部署"
        caught = [f["id"] for f in V.compare_versions(original, invented) if f["level"] == "error"]
        ok = not diff and status == "needs_review" and "compare.numbers" in caught
        record("S02", "Improve existing experience without changing facts",
               "sample resume; wording rewrite (ai_suggested) vs. a rewrite that adds '500 台终端'",
               "faithful rewrite: no fact drift, status needs_review (unapproved); invented number -> compare.numbers error",
               f"drift errors={len(diff)}; status={status}; invented-number errors={caught}", ok)
        self.assertTrue(ok)

    def test_s03_tailor_to_jd_without_fabrication(self):
        out = run("match_jd.py", "--input", ROOT / "examples" / "sample_resume.md", "--jd", ROOT / "examples" / "sample_job_description.md", "--json")
        res = json.loads(out.stdout)
        missing = [r for r in res["results"] if r["status"] == "missing_evidence"]
        gen = self.gen(ROOT / "examples" / "sample_resume.md", "--formats", "md,docx", "--ats-submission", "--prefix", "tailored")
        txt = inspect_docx(self.tmp / "out" / "tailored.docx")["text"]
        ok = (out.returncode == 0 and gen.returncode == 0 and any("Rust" in r["requirement"] for r in missing)
              and "Rust" not in txt and "C++" not in txt
              and report_of(self, "tailored")["artifacts"]["template"] == "ats-clean")
        record("S03", "Tailor to a JD (sample JD requires Rust/C++ which the resume lacks)",
               "sample_resume.md + sample_job_description.md; generate ATS version",
               "Rust/C++ requirement reported as missing_evidence; generated resume does not contain Rust/C++",
               f"counts={res['counts']}; 'Rust' in output={'Rust' in txt}; template={report_of(self, 'tailored')['artifacts']['template']}", ok)
        self.assertTrue(ok)

    def test_s04_bilingual_versions(self):
        zh_d, en_d = zh(), en()
        en_d["basics"].update(email=zh_d["basics"]["email"], phone=zh_d["basics"]["phone"])
        a, b = self.write_json("zh.json", zh_d), self.write_json("en.json", en_d)
        r1, r2 = self.gen(a, "--formats", "md,docx"), self.gen(b, "--formats", "md,docx")
        cmp_ok = run("validate_resume.py", "--input", a, "--compare", b)
        en_md = (self.tmp / "out" / "en.md").read_text(encoding="utf-8")
        zh_md = (self.tmp / "out" / "zh.md").read_text(encoding="utf-8")
        ok = (r1.returncode == r2.returncode == cmp_ok.returncode == 0 and "## Experience" in en_md and "Mar 2020 – Present" in en_md
              and "## 工作经历" in zh_md and "2020.03 – 至今" in zh_md)
        en_d["experience"][0]["bullets"][1] = "Reduced API latency to 180ms"
        drift = run("validate_resume.py", "--input", a, "--compare", self.write_json("en2.json", en_d))
        ok = ok and drift.returncode == 5
        record("S04", "Chinese + English versions of the same facts", "zh.json, en.json (same dates/contacts/numbers); then en with a changed number",
               "both generate with their own labels/date style; --compare passes; changed number -> exit 5",
               f"gen={r1.returncode},{r2.returncode}; compare={cmp_ok.returncode}; drifted compare={drift.returncode}", ok)
        self.assertTrue(ok)

    def test_s05_ats_vs_modern_business(self):
        d = zh()
        src = self.write_json("r.json", d)
        a = self.gen(src, "--formats", "docx", "--template", "ats-clean", "--prefix", "ats")
        m = self.gen(src, "--formats", "docx", "--template", "modern-business", "--prefix", "mod")
        ia, im = inspect_docx(self.tmp / "out" / "ats.docx"), inspect_docx(self.tmp / "out" / "mod.docx")
        sa, sm = docx_xml(self.tmp / "out" / "ats.docx", "word/styles.xml"), docx_xml(self.tmp / "out" / "mod.docx", "word/styles.xml")
        same_content = ia["text"].replace(" ", "").lower() != "" and "虚构科技有限公司" in ia["text"] and "虚构科技有限公司" in im["text"]
        ok = (a.returncode == m.returncode == 0 and ia["tables"] == 0 and im["tables"] == 0 and "<w:caps/>" in sa
              and 'w:fill="' in sm and "w:fill=" not in sa.split('w:styleId="Heading1"')[1].split("</w:style>")[0] and same_content)
        record("S05", "ATS-clean and modern-business versions from one data file", "same zh.json, two templates",
               "both succeed; same content; ATS has no tables, CAPS headings, no shading; modern uses shaded section bands",
               f"exit {a.returncode},{m.returncode}; tables {ia['tables']},{im['tables']}; ats caps={'<w:caps/>' in sa}", ok)
        self.assertTrue(ok)

    def test_s06_missing_contact_keeps_placeholder(self):
        d = zh()
        d["basics"]["phone"] = "{{MISSING:phone}}"
        d["basics"]["email"] = "{{MISSING:email}}"
        p = self.gen(self.write_json("r.json", d), "--formats", "md,docx")
        rep = report_of(self)
        ph = [f for f in rep["A_automated"]["findings"] if f["id"] == "placeholder"]
        ok = (p.returncode == 0 and len(ph) == 2 and rep["status"] == "needs_review" and "{{MISSING:phone}}" in docx_xml(self.tmp / "out" / "r.docx"))
        record("S06", "Missing contact details stay as placeholders", "phone/email = {{MISSING:...}}",
               "generated draft keeps both placeholders (highlighted), listed in report, status needs_review (not ready)",
               f"exit {p.returncode}; placeholders={len(ph)}; status={rep['status']}", ok)
        self.assertTrue(ok)

    def test_s07_pdf_backend_missing_fails_correctly(self):
        src = self.write_json("r.json", zh())
        p = self.gen(src, "--formats", "md,docx,pdf", env=NO_BACKENDS)
        rep = report_of(self)
        ok = (p.returncode == 4 and rep["pdf_status"] == "blocked_by_environment" and rep["failed_stage"] == "pdf"
              and not (self.tmp / "out" / "r.pdf").exists() and (self.tmp / "out" / "r.docx").exists())
        record("S07", "No PDF backend available (simulated: Word and LibreOffice disabled)", "generate --formats md,docx,pdf",
               "exit 4; partial success reported (md+docx exist); pdf_status=blocked_by_environment; no PDF file; alternatives printed",
               f"exit {p.returncode}; pdf_status={rep['pdf_status']}; failed_stage={rep['failed_stage']}; alternatives printed={'alternative' in p.stderr}", ok,
               note="Backend absence is simulated via RESUME_DESIGN_DISABLE_BACKENDS; " + DIALOGUE_NOT_TESTED)
        self.assertTrue(ok)

    def test_s08_bad_input_error_codes(self):
        bad_json = self.tmp / "bad.json"
        bad_json.write_text("{oops", encoding="utf-8")
        wrong_ext = self.tmp / "resume.pdf"
        wrong_ext.write_bytes(b"%PDF-1.4")
        d = zh()
        d["experience"][0]["start"] = "2031-99"
        codes = {"malformed json": self.gen(bad_json).returncode, "unsupported extension": self.gen(wrong_ext).returncode,
                 "missing file": self.gen(self.tmp / "none.json").returncode, "bad format arg": self.gen(self.write_json("r.json", zh()), "--formats", "xls").returncode,
                 "invalid date": self.gen(self.write_json("d.json", d)).returncode}
        ok = codes == {"malformed json": 2, "unsupported extension": 2, "missing file": 2, "bad format arg": 2, "invalid date": 5}
        record("S08", "Malformed input", "bad JSON, .pdf as input, missing file, --formats xls, impossible date",
               "exit 2 for input/arg errors; exit 5 for validation failure (invalid date)", str(codes), ok)
        self.assertTrue(ok)

    def test_s09_fake_certificate_blocked(self):
        d = zh()
        d["certificates"] = [{"name": "PMP", "issuer": "PMI", "confirmation_status": "ai_suggested"}]
        p = self.gen(self.write_json("r.json", d), "--formats", "md,docx")
        files = sorted(f.name for f in (self.tmp / "out").iterdir())
        d["certificates"] = []
        p2 = self.gen(self.write_json("r2.json", d), "--formats", "md,docx")
        ok = p.returncode == 5 and not any(f.endswith((".md", ".docx")) for f in files) and p2.returncode == 0
        record("S09", "User asks to add a certificate they do not hold", "certificate entered as ai_suggested/unconfirmed (what a non-compliant draft would look like)",
               "validation error fabrication.certificate: exit 5, no resume files; after removal generation succeeds",
               f"exit {p.returncode}; files={files}; after removal exit {p2.returncode}", ok,
               note="The refusal wording and the offer of honest alternatives are model behaviour and are NOT tested. "
                    "Tested: the toolchain refuses to render an unconfirmed certificate.")
        self.assertTrue(ok)

    def test_s10_overwrite_protection_and_privacy_logs(self):
        src = self.write_json("r.json", zh())
        self.gen(src, "--formats", "md,docx")
        before = sha(self.tmp / "out" / "r.docx")
        p = self.gen(src, "--formats", "md,docx")
        all_text = p.stdout + p.stderr + (self.tmp / "out" / "r-1.report.json").read_text(encoding="utf-8")
        leaked = [s for s in ("tester@example.com", "139-1111-2222") if s in all_text]
        ok = sha(self.tmp / "out" / "r.docx") == before and (self.tmp / "out" / "r-1.docx").exists() and not leaked
        record("S10", "Overwrite protection and privacy-safe logs", "generate twice into the same folder",
               "first outputs untouched; second run uses r-1.*; no email/phone in stdout/stderr/report",
               f"original unchanged={sha(self.tmp / 'out' / 'r.docx') == before}; r-1.docx exists={(self.tmp / 'out' / 'r-1.docx').exists()}; leaked={leaked}", ok)
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
