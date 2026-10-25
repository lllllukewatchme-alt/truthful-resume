import json
import re
import unittest
import zipfile

from helpers import ROOT, TempCase, docx_xml, en, run, sha, zh

from resume_design import mdio, templates
from resume_design.docx_writer import inspect_docx
from resume_design.model import normalize
from resume_design.pipeline import resolve_context
from resume_design.schema_check import validate_schema


class MarkdownTests(TempCase):
    def test_markdown_roundtrip_preserves_facts(self):
        data, _, _ = __import__("resume_design.pipeline", fromlist=["x"]).load_resume(ROOT / "examples" / "sample_resume.md")
        ctx = resolve_context(data)
        md = mdio.to_markdown(ctx["data"], ctx["lang"], ctx["rules"], ctx["order"], ctx["labels"])
        back = mdio.parse_markdown(md)
        for sec in ("experience", "education", "projects"):
            self.assertEqual(len(back[sec]), len(data[sec]))
            for a, b in zip(data[sec], back[sec]):
                for f in ("organization", "role", "start", "end", "location", "bullets", "evidence", "confirmation_status"):
                    self.assertEqual(a[f], b[f], f"{sec}.{f}")
        self.assertEqual(back["basics"]["email"], data["basics"]["email"])
        self.assertEqual(back["skills"], data["skills"])

    def test_markdown_template_render_en_labels_and_dates(self):
        ctx = resolve_context(en())
        md = mdio.to_markdown(ctx["data"], "en", ctx["rules"], ctx["order"], ctx["labels"])
        self.assertIn("## Experience", md)
        self.assertIn("Mar 2020 – Present", md)

    def test_markdown_zh_dates(self):
        ctx = resolve_context(zh())
        md = mdio.to_markdown(ctx["data"], "zh", ctx["rules"], ctx["order"], ctx["labels"])
        self.assertIn("2020.03 – 至今", md)

    def test_date_forms_parse(self):
        md = "# T\n- email: a@b.co\n## 工作经历\n### X | Y | 2019年7月 – 至今\n- a\n### Z | W | Jul 2015 – 2018/06\n- b\n"
        d = mdio.parse_markdown(md)
        self.assertEqual((d["experience"][0]["start"], d["experience"][0]["end"]), ("2019-07", "present"))
        self.assertEqual((d["experience"][1]["start"], d["experience"][1]["end"]), ("2015-07", "2018-06"))


class SchemaTests(unittest.TestCase):
    def test_valid_sample(self):
        d = json.loads((ROOT / "examples" / "sample_resume.json").read_text(encoding="utf-8"))
        self.assertEqual(validate_schema(d), [])

    def test_errors_have_paths(self):
        errs = dict(validate_schema({"basics": {"name": 5}, "experience": [{"role": "x"}], "preferences": {"page_limit": 0}}))
        self.assertIn("basics.name", errs)
        self.assertIn("experience[0].organization", errs)
        self.assertIn("preferences.page_limit", errs)


class GenerateTests(TempCase):
    def test_json_to_md_docx(self):
        src = self.write_json("r.json", zh())
        before = sha(src)
        p = self.gen(src, "--formats", "md,docx")
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        out = self.tmp / "out"
        self.assertTrue((out / "r.md").stat().st_size > 0)
        info = inspect_docx(out / "r.docx")
        self.assertIn("测试用户", info["text"])
        self.assertIn("虚构科技有限公司", info["text"])
        self.assertIn("Java", info["text"])
        self.assertGreaterEqual(info["heading1"], 3)
        self.assertGreaterEqual(info["bullets"], 2)
        self.assertEqual(sha(src), before, "input must be unchanged")

    def test_docx_is_real_ooxml_zip(self):
        src = self.write_json("e.json", en())
        self.assertEqual(self.gen(src, "--formats", "docx").returncode, 0)
        f = self.tmp / "out" / "e.docx"
        self.assertTrue(zipfile.is_zipfile(f))
        with zipfile.ZipFile(f) as z:
            names = z.namelist()
            self.assertEqual(names[0], "[Content_Types].xml")
            for req in ("word/document.xml", "word/styles.xml", "word/numbering.xml", "_rels/.rels"):
                self.assertIn(req, names)
            self.assertIsNone(z.testzip())
        self.assertIn("Alex Test", docx_xml(f))
        self.assertIn('w:pStyle w:val="Heading1"', docx_xml(f))
        self.assertIn("<w:numPr>", docx_xml(f, "word/styles.xml"))

    def test_md_input_sample_all_formats_md_docx(self):
        p = self.gen(ROOT / "examples" / "sample_resume.md", "--formats", "md,docx")
        self.assertEqual(p.returncode, 0, p.stderr)
        rep = json.loads((self.tmp / "out" / "sample_resume.report.json").read_text(encoding="utf-8"))
        self.assertEqual(rep["status"], "validated")
        self.assertTrue(rep["input_unchanged"])
        self.assertEqual(rep["pdf_status"], "not_tested")

    def test_creates_nested_output_dir(self):
        src = self.write_json("r.json", en())
        p = run("generate_resume.py", "--input", src, "--output-dir", self.tmp / "a" / "b" / "c", "--formats", "md")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue((self.tmp / "a" / "b" / "c" / "r.md").is_file())

    def test_name_conflict_never_overwrites(self):
        src = self.write_json("r.json", en())
        self.assertEqual(self.gen(src, "--formats", "md,docx").returncode, 0)
        first = sha(self.tmp / "out" / "r.docx")
        data = en()
        data["basics"]["name"] = "Second Person"
        src2 = self.write_json("r.json", data)
        self.assertEqual(self.gen(src2, "--formats", "md,docx").returncode, 0)
        self.assertEqual(sha(self.tmp / "out" / "r.docx"), first, "existing file untouched")
        self.assertTrue((self.tmp / "out" / "r-1.docx").is_file())
        self.assertIn("Second Person", docx_xml(self.tmp / "out" / "r-1.docx"))

    def test_force_overwrites_only_target(self):
        src = self.write_json("r.json", en())
        self.assertEqual(self.gen(src, "--formats", "md,docx").returncode, 0)
        bystander = self.tmp / "out" / "keep.txt"
        bystander.write_text("keep", encoding="utf-8")
        data = en()
        data["basics"]["name"] = "Forced Name"
        src = self.write_json("r.json", data)
        self.assertEqual(self.gen(src, "--formats", "md,docx", "--force", "--report", self.tmp / "out" / "rep.json").returncode, 0)
        self.assertIn("Forced Name", docx_xml(self.tmp / "out" / "r.docx"))
        self.assertFalse((self.tmp / "out" / "r-1.docx").exists())
        self.assertEqual(bystander.read_text(), "keep")

    def test_dry_run_writes_nothing(self):
        src = self.write_json("r.json", en())
        p = run("generate_resume.py", "--input", src, "--output-dir", self.tmp / "nope", "--dry-run")
        self.assertEqual(p.returncode, 0)
        self.assertFalse((self.tmp / "nope").exists())
        self.assertIn("would write", p.stdout)

    def test_invalid_inputs_exit_2(self):
        self.assertEqual(self.gen(self.tmp / "missing.json").returncode, 2)
        bad = self.tmp / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        self.assertEqual(self.gen(bad).returncode, 2)
        arr = self.tmp / "arr.json"
        arr.write_text("[1,2]", encoding="utf-8")
        self.assertEqual(self.gen(arr).returncode, 2)
        odd = self.tmp / "x.pdf"
        odd.write_bytes(b"%PDF")
        self.assertEqual(self.gen(odd).returncode, 2)
        src = self.write_json("r.json", en())
        self.assertEqual(self.gen(src, "--formats", "html").returncode, 2)
        self.assertEqual(self.gen(src, "--template", "nonexistent").returncode, 2)
        self.assertEqual(run("generate_resume.py").returncode, 2)  # missing required --input
        self.assertEqual(self.gen(src, "--bogus-flag").returncode, 2)

    def test_markdown_without_title_is_input_error(self):
        md = self.tmp / "n.md"
        md.write_text("## 工作经历\n### A | B | 2020-01\n- x\n", encoding="utf-8")
        self.assertEqual(self.gen(md).returncode, 2)

    def test_validation_error_blocks_generation_exit_5(self):
        data = en()
        data["basics"]["name"] = ""
        src = self.write_json("r.json", data)
        p = self.gen(src, "--formats", "md,docx")
        self.assertEqual(p.returncode, 5, p.stderr)
        self.assertEqual([f.name for f in (self.tmp / "out").iterdir()], ["r.report.json"])
        rep = json.loads((self.tmp / "out" / "r.report.json").read_text(encoding="utf-8"))
        self.assertEqual(rep["status"], "draft")
        p2 = self.gen(src, "--formats", "md", "--allow-draft")
        self.assertEqual(p2.returncode, 0)

    def test_placeholders_kept_and_reported(self):
        data = zh()
        data["basics"]["phone"] = "{{MISSING:phone}}"
        data["experience"][0]["bullets"].append("成果：{{MISSING:experience[0].metric}}")
        src = self.write_json("r.json", data)
        p = self.gen(src, "--formats", "md,docx")
        self.assertEqual(p.returncode, 0, p.stderr)
        rep = json.loads((self.tmp / "out" / "r.report.json").read_text(encoding="utf-8"))
        self.assertEqual(rep["status"], "needs_review")
        ids = [f["id"] for f in rep["A_automated"]["findings"]]
        self.assertEqual(ids.count("placeholder"), 2)
        self.assertIn("{{MISSING:phone}}", docx_xml(self.tmp / "out" / "r.docx"))
        self.assertIn('w:highlight w:val="yellow"', docx_xml(self.tmp / "out" / "r.docx"))
        self.assertIn("{{MISSING:phone}}", (self.tmp / "out" / "r.md").read_text(encoding="utf-8"))

    def test_status_never_ready_without_user_confirmation(self):
        data = en()
        for t in ("md,docx",):
            src = self.write_json("r.json", data)
            self.gen(src, "--formats", t)
        rep = json.loads((self.tmp / "out" / "r.report.json").read_text(encoding="utf-8"))
        self.assertEqual(rep["status"], "validated")
        data["meta"] = {"review": {"facts_confirmed": True, "contact_confirmed": True, "target_confirmed": True}}
        src = self.write_json("c.json", data)
        self.assertEqual(self.gen(src, "--formats", "md,docx").returncode, 0)
        rep = json.loads((self.tmp / "out" / "c.report.json").read_text(encoding="utf-8"))
        self.assertEqual(rep["status"], "validated", "data flags alone must not make a resume ready (P1-4)")
        self.assertEqual(self.gen(src, "--formats", "md,docx", "--confirm-ready").returncode, 0)
        rep = json.loads((self.tmp / "out" / "c-1.report.json").read_text(encoding="utf-8"))
        self.assertEqual(rep["status"], "ready_to_submit")

    def test_templates_differ_in_real_properties(self):
        sigs = {}
        for t in templates.list_templates():
            src = self.write_json(f"{t}.json", zh())
            self.assertEqual(self.gen(src, "--formats", "docx", "--template", t).returncode, 0, t)
            f = self.tmp / "out" / f"{t}.docx"
            doc, st = docx_xml(f), docx_xml(f, "word/styles.xml")
            sig = (re.search(r'<w:pgMar w:top="(\d+)" w:right="(\d+)"', doc).groups(),
                   re.search(r'w:ascii="([^"]+)"', st).group(1),
                   re.search(r'w:styleId="Heading1".*?<w:color w:val="(\w+)"', st).group(1),
                   re.search(r'w:line="(\d+)"', st).group(1),
                   "<w:tbl>" in doc)
            sigs[t] = sig
            style = templates.load_style(t)
            wants_table = style["layout"].get("columns", 1) == 2 or style.get("header", {}).get("style") == "band"
            self.assertEqual(sig[4], wants_table, f"{t}: table presence must follow the style config")
        self.assertEqual(len(set(sigs.values())), len(sigs), sigs)
        self.assertGreaterEqual(len(sigs), 11)
        for key in range(4):  # each of margins/fonts/colour/line spacing varies across templates
            self.assertGreater(len({s[key] for s in sigs.values()}), 1, key)

    def test_locale_paper_and_language(self):
        src = self.write_json("e.json", en())
        self.gen(src, "--formats", "docx")
        self.assertIn('w:pgSz w:w="12240"', docx_xml(self.tmp / "out" / "e.docx"))   # en-US Letter
        data = en()
        data["target"]["locale"] = "en-GB"
        src = self.write_json("g.json", data)
        self.gen(src, "--formats", "docx")
        self.assertIn('w:pgSz w:w="11906"', docx_xml(self.tmp / "out" / "g.docx"))   # A4
        src = self.write_json("z.json", zh())
        self.gen(src, "--formats", "docx")
        self.assertIn("w:eastAsia=\"zh-CN\"", docx_xml(self.tmp / "out" / "z.docx", "word/styles.xml"))

    def test_template_selection_rules(self):
        c = templates.choose_template
        self.assertEqual(c("Software Engineer")[0], "technical")
        self.assertEqual(c("后端开发工程师")[0], "technical")
        self.assertEqual(c("Engineering Manager")[0], "management")
        self.assertEqual(c("UI Designer")[0], "creative")
        self.assertEqual(c("Sales Associate")[0], "modern-business")
        self.assertEqual(c("Software Engineer", ats_submission=True)[0], "ats-clean")
        self.assertEqual(c("Software Engineer", explicit="management", ats_submission=True)[0], "management")
        self.assertEqual(c("x", rules={"default": "ats-clean"})[0], "ats-clean")  # configurable

    def test_creative_warns_not_ats_safe(self):
        src = self.write_json("c.json", zh())
        self.gen(src, "--formats", "docx", "--template", "creative")
        rep = json.loads((self.tmp / "out" / "c.report.json").read_text(encoding="utf-8"))
        self.assertTrue(any(f["id"] == "template.not_ats_safe" for f in rep["A_automated"]["findings"]))
        self.assertTrue(any(i["id"] == "layout_ats" for i in rep["C_environment_unverifiable"]))

    def test_clean_metadata(self):
        src = self.write_json("e.json", en())
        self.gen(src, "--formats", "docx", "--clean-metadata")
        core = docx_xml(self.tmp / "out" / "e.docx", "docProps/core.xml")
        self.assertNotIn("dcterms:created", core)
        self.assertIn("<dc:creator></dc:creator>", core)

    def test_bilingual_pair_consistency(self):
        a = self.write_json("zh.json", zh())
        zh_data = zh()
        en_data = en()
        en_data["basics"].update(email=zh_data["basics"]["email"], phone=zh_data["basics"]["phone"])
        b = self.write_json("en.json", en_data)
        p = run("validate_resume.py", "--input", a, "--compare", b)
        self.assertEqual(p.returncode, 0, p.stdout)
        en_data["experience"][0]["start"] = "2019-01"
        b = self.write_json("en.json", en_data)
        p = run("validate_resume.py", "--input", a, "--compare", b)
        self.assertEqual(p.returncode, 5)
        self.assertIn("compare.date", p.stdout)


if __name__ == "__main__":
    unittest.main()
