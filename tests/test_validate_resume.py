import json
import unittest
import zipfile

from helpers import ROOT, TempCase, en, run, zh

from resume_design import jd
from resume_design import validate as V
from resume_design.model import find_placeholders, normalize


def ids(findings, level=None):
    return [f["id"] for f in findings if level is None or f["level"] == level]


class DataChecks(unittest.TestCase):
    def check(self, data, **kw):
        return V.check_data(data, **kw)

    def test_clean_data_has_no_errors(self):
        self.assertEqual(ids(self.check(zh()), "error"), [])

    def test_placeholder_detection_paths(self):
        d = zh()
        d["basics"]["phone"] = "{{MISSING:phone}}"
        d["experience"][0]["bullets"][0] = "x {{MISSING:metric}}"
        phs = find_placeholders(normalize(d))
        self.assertEqual({p["field"] for p in phs}, {"phone", "metric"})
        self.assertEqual(ids(self.check(d)).count("placeholder"), 2)

    def test_required_fields(self):
        d = {"basics": {"name": ""}}
        got = ids(self.check(d), "error")
        for needed in ("required.name", "required.contact", "required.sections"):
            self.assertIn(needed, got)

    def test_placeholder_contact_counts_as_present(self):
        d = zh()
        d["basics"]["email"] = "{{MISSING:email}}"
        d["basics"]["phone"] = ""
        self.assertNotIn("required.contact", ids(self.check(d)))

    def test_date_checks(self):
        d = zh()
        d["experience"][0]["start"] = "2023-13"
        self.assertIn("date.format", ids(self.check(d), "error"))
        d["experience"][0].update(start="2022-05", end="2021-01")
        self.assertIn("date.order", ids(self.check(d), "error"))
        d["experience"][0].update(start="sometime", end="2021-01")
        self.assertIn("date.format", ids(self.check(d), "error"))
        d["experience"][0].update(start="2099-01", end="")
        self.assertIn("date.format", ids(self.check(d), "error"))  # year out of range
        d["experience"][0].update(start="", end="")
        self.assertIn("date.missing", ids(self.check(d), "warning"))

    def test_duplicate_and_empty(self):
        d = zh()
        d["experience"][0]["bullets"] = ["负责订单服务的设计与迭代工作", "负责订单服务的设计与迭代工作", "   "]
        got = ids(self.check(d))
        self.assertIn("duplicate.paragraph", got)
        self.assertIn("empty.paragraph", got)

    def test_contact_format_and_lang(self):
        d = en()
        d["basics"]["email"] = "not-an-email"
        d["basics"]["phone"] = "12"
        got = ids(self.check(d))
        self.assertIn("format.email", got)
        self.assertIn("format.phone", got)
        d = zh()
        self.assertIn("lang.mismatch", ids(self.check(d, lang="en")))
        self.assertNotIn("lang.mismatch", ids(self.check(d, lang="zh")))

    def test_fabricated_certificate_is_blocking(self):
        d = zh()
        d["certificates"] = [{"name": "PMP", "issuer": "PMI", "confirmation_status": "ai_suggested"}]
        self.assertIn("fabrication.certificate", ids(self.check(d), "error"))
        d["certificates"][0]["confirmation_status"] = "user_confirmed"
        self.assertNotIn("fabrication.certificate", ids(self.check(d)))

    def test_invalid_status_value(self):
        d = zh()
        d["experience"][0]["confirmation_status"] = "trust_me"
        got = ids(self.check(d), "error")
        self.assertTrue("schema" in got or "status.invalid" in got)

    def test_photo_flag_warns(self):
        d = zh()
        d["preferences"] = {"photo": True}
        self.assertIn("preferences.photo", ids(self.check(d)))


class StatusAndTiers(unittest.TestCase):
    def report(self, data, pdf="not_tested", req=False, confirm=False):
        f = V.check_data(data)
        return V.build_report(f, data, input_name="x.json", input_sha="0", pdf_status=pdf, pdf_required=req,
                              ats_safe=True, missing_fonts=[], fonts_detectable=True, confirm_ready=confirm)

    def test_status_ladder(self):
        d = zh()
        self.assertEqual(self.report(d)["status"], "validated")
        d["basics"]["phone"] = "{{MISSING:phone}}"
        self.assertEqual(self.report(d)["status"], "needs_review")
        d = zh()
        d["experience"][0]["confirmation_status"] = "ai_suggested"
        self.assertEqual(self.report(d)["status"], "needs_review")
        d = zh()
        d["basics"]["name"] = ""
        self.assertEqual(self.report(d)["status"], "draft")
        d = zh()
        d["meta"] = {"review": {"facts_confirmed": True, "contact_confirmed": True, "target_confirmed": True}}
        self.assertEqual(self.report(d)["status"], "validated")                      # data flags alone: not ready (P1-4)
        self.assertEqual(self.report(d, confirm=True)["status"], "ready_to_submit")
        self.assertEqual(self.report(d, pdf="blocked_by_environment", req=True, confirm=True)["status"], "validated")
        self.assertEqual(self.report(d, pdf="passed", req=True, confirm=True)["status"], "ready_to_submit")
        d["meta"]["review"]["contact_confirmed"] = False
        self.assertEqual(self.report(d, confirm=True)["status"], "validated")

    def test_three_tiers_present_and_manual_never_passed(self):
        r = self.report(zh())
        self.assertTrue(r["B_manual_review"])
        self.assertTrue(r["C_environment_unverifiable"])
        self.assertTrue(all("status" not in item and "passed" not in json.dumps(item) for item in r["B_manual_review"]))
        self.assertIn("pagination", [i["id"] for i in r["C_environment_unverifiable"]])
        r2 = self.report(zh(), pdf="passed")
        self.assertNotIn("pagination", [i["id"] for i in r2["C_environment_unverifiable"]])

    def test_metric_and_exaggeration_flags(self):
        d = zh()
        d["experience"][0]["evidence"] = []
        d["experience"][0]["confirmation_status"] = "user_provided"
        d["experience"][0]["bullets"] = ["性能提升 300%", "精通所有数据库，行业领先"]
        items = {i["id"]: i for i in V.manual_review_items(d, False)}
        self.assertEqual(items["metrics"]["count"], 1)
        self.assertEqual(items["exaggeration"]["count"], 1)
        d["experience"][0]["evidence"] = ["绩效报告"]
        items = {i["id"]: i for i in V.manual_review_items(d, False)}
        self.assertEqual(items["metrics"]["count"], 0)


class CliValidate(TempCase):
    def test_exit_codes_and_json_report(self):
        good = self.write_json("g.json", zh())
        rp = self.tmp / "rep.json"
        p = run("validate_resume.py", "--input", good, "--report", rp)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        rep = json.loads(rp.read_text(encoding="utf-8"))
        self.assertEqual(rep["status"], "validated")
        # report is never overwritten silently
        p = run("validate_resume.py", "--input", good, "--report", rp)
        self.assertEqual(p.returncode, 0)
        self.assertTrue((self.tmp / "rep-1.json").exists())
        bad = zh()
        bad["experience"][0]["start"] = "2025-02"
        bad["experience"][0]["end"] = "2020-01"
        self.assertEqual(run("validate_resume.py", "--input", self.write_json("b.json", bad)).returncode, 5)
        self.assertEqual(run("validate_resume.py", "--input", self.tmp / "none.json").returncode, 2)

    def test_strict_fails_on_placeholders(self):
        d = zh()
        d["basics"]["phone"] = "{{MISSING:phone}}"
        src = self.write_json("p.json", d)
        self.assertEqual(run("validate_resume.py", "--input", src).returncode, 0)
        self.assertEqual(run("validate_resume.py", "--input", src, "--strict").returncode, 5)

    def test_docx_validation_valid_corrupt_and_placeholder(self):
        d = zh()
        d["basics"]["phone"] = "{{MISSING:phone}}"
        src = self.write_json("p.json", d)
        self.assertEqual(run("generate_resume.py", "--input", src, "--output-dir", self.tmp / "o", "--formats", "docx").returncode, 0)
        docx = self.tmp / "o" / "p.docx"
        p = run("validate_resume.py", "--input", src, "--docx", docx)
        self.assertIn("docx.placeholder", p.stdout)
        self.assertEqual(p.returncode, 0)
        # docx-only mode
        self.assertEqual(run("validate_resume.py", "--input", docx).returncode, 0)
        # corrupt package
        broken = self.tmp / "broken.docx"
        broken.write_bytes(b"PK\x03\x04 this is not a docx")
        p = run("validate_resume.py", "--input", src, "--docx", broken)
        self.assertEqual(p.returncode, 5)
        self.assertIn("docx.invalid", p.stdout)
        # plain text renamed to .docx
        fake = self.tmp / "fake.docx"
        fake.write_text("<html>not office</html>", encoding="utf-8")
        self.assertEqual(run("validate_resume.py", "--input", src, "--docx", fake).returncode, 5)
        # zip without word/document.xml
        nodoc = self.tmp / "nodoc.docx"
        with zipfile.ZipFile(nodoc, "w") as z:
            z.writestr("hello.txt", "x")
        self.assertEqual(run("validate_resume.py", "--input", src, "--docx", nodoc).returncode, 5)

    def test_docx_cjk_loss_detected(self):
        src = self.write_json("p.json", zh())
        self.assertEqual(run("generate_resume.py", "--input", src, "--output-dir", self.tmp / "o", "--formats", "docx").returncode, 0)
        other = zh()
        other["basics"]["name"] = "完全不同"
        other["experience"][0]["organization"] = "另一家公司"
        src2 = self.write_json("q.json", other)
        p = run("validate_resume.py", "--input", src2, "--docx", self.tmp / "o" / "p.docx")
        self.assertEqual(p.returncode, 5)
        self.assertIn("docx.", p.stdout)


class JdMatching(unittest.TestCase):
    def test_sample_match(self):
        data = json.loads((ROOT / "examples" / "sample_resume.json").read_text(encoding="utf-8"))
        text = "# Backend\n## Requirements\n- Strong Java or Go experience\n- Kubernetes and Docker\n- Rust or C++ experience preferred\n"
        res = jd.match(data, text)
        by = {r["requirement"]: r for r in res["results"]}
        self.assertEqual(by["Kubernetes and Docker"]["status"], "satisfied")
        self.assertEqual(by["Rust or C++ experience preferred"]["status"], "missing_evidence")
        self.assertTrue(by["Rust or C++ experience preferred"]["preferred"])
        self.assertIn(by["Strong Java or Go experience"]["status"], ("satisfied", "partial"))
        self.assertIn("never add skills", res["note"])

    def test_chinese_jd_cli(self):
        p = run("match_jd.py", "--input", ROOT / "examples" / "sample_resume.md", "--jd", ROOT / "examples" / "sample_job_description.md", "--json")
        self.assertEqual(p.returncode, 0, p.stderr)
        res = json.loads(p.stdout)
        self.assertGreaterEqual(res["counts"]["satisfied"], 3)
        self.assertGreaterEqual(res["counts"]["missing_evidence"], 1)
        self.assertEqual(run("match_jd.py", "--input", ROOT / "examples" / "sample_resume.md", "--jd", "nope.md").returncode, 2)


if __name__ == "__main__":
    unittest.main()
