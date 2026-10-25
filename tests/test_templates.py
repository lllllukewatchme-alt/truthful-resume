"""Tests for the template catalogue: every style file is complete, each new layout feature is present in the DOCX XML,
ATS flags are honest, and (when Word is available) every template renders both rich samples without losing text."""
import json
import re
import subprocess
import unittest

from helpers import ROOT, TempCase, docx_xml, en, run, zh

from resume_design import envinfo, templates
from resume_design.docx_writer import inspect_docx

RICH_JSON = ROOT / "examples" / "sample_resume_rich.json"
RICH_MD = ROOT / "examples" / "sample_resume_rich.md"
NEW = ["harvard", "banner", "sidebar-dark", "timeline", "date-left", "developer-mono"]


class Catalogue(unittest.TestCase):
    def test_eleven_templates_each_with_content_file(self):
        names = set(templates.list_templates())
        self.assertEqual(len(names), 11)
        self.assertTrue(set(NEW) <= names)
        for n in names:
            self.assertTrue((ROOT / f"templates/content/{n}.md").is_file(), n)
            cfg = templates.load_content_template(n)
            self.assertTrue(cfg["section_order"], n)

    def test_ats_flag_is_honest(self):
        """A style that uses a table, a heading prefix, or a date column must not claim to be ATS-safe."""
        for n in templates.list_templates():
            s = templates.load_style(n)
            risky = (s["layout"].get("columns", 1) == 2 or s.get("header", {}).get("style") == "band"
                     or bool(s.get("heading", {}).get("prefix")) or s["layout"].get("entry_style") == "date_left")
            if risky:
                self.assertFalse(s["ats"]["safe"], f"{n} has layout features that parsers can trip over")
            self.assertEqual(s["ats"]["use_tables"], s["layout"].get("columns", 1) == 2 or s.get("header", {}).get("style") == "band", n)

    def test_auto_selection_for_academic_roles(self):
        for role in ("Assistant Professor of Physics", "Postdoctoral Fellow", "高校讲师", "助理教授"):
            self.assertEqual(templates.choose_template(role)[0], "harvard", role)
        self.assertEqual(templates.choose_template("Software Engineer")[0], "technical")
        for t in ("banner", "sidebar-dark", "timeline", "date-left", "developer-mono"):   # never auto-picked
            self.assertNotEqual(templates.choose_template("anything at all")[0], t)

    def test_rich_samples_validate(self):
        for f in (RICH_JSON, RICH_MD):
            p = run("validate_resume.py", "--input", f)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertIn("validated", p.stdout.splitlines()[0])
            self.assertNotIn("WARNING", p.stdout)


class LayoutFeatures(TempCase):
    def docx(self, template, source=RICH_JSON):
        prefix = f"{template}-{source.suffix[1:]}"
        p = run("generate_resume.py", "--input", source, "--output-dir", self.tmp / "o", "--formats", "docx", "--template", template, "--prefix", prefix)
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        return self.tmp / "o" / f"{prefix}.docx"

    def test_banner_is_a_full_width_shaded_cell_with_white_text(self):
        f = self.docx("banner")
        xml = docx_xml(f)
        first_tbl = re.search(r"<w:tbl>.*?</w:tbl>", xml, re.S).group(0)
        self.assertIn('w:fill="1F3A5F"', first_tbl)
        self.assertIn('<w:tblInd w:w="0"', first_tbl)
        self.assertIn("Maya Chen", first_tbl)
        self.assertIn('<w:color w:val="FFFFFF"/>', first_tbl)
        self.assertEqual(xml.count("<w:tbl>"), 1)
        self.assertIn("Maya Chen", inspect_docx(f)["text"])

    def test_sidebar_dark_recolours_every_sidebar_run_in_schema_order(self):
        f = self.docx("sidebar-dark")
        xml = docx_xml(f)
        tbl = re.search(r"<w:tbl>.*?</w:tbl>", xml, re.S).group(0)
        side = tbl.split("</w:tc>")[0]
        self.assertIn('w:fill="263238"', side)
        self.assertIn("Contact", inspect_docx(f)["text"])   # contact moved into the sidebar
        runs = re.findall(r"<w:r>.*?</w:r>", side, re.S)
        self.assertTrue(runs)
        for r in runs:
            self.assertRegex(r, r'<w:color w:val="(ECEFF1|FFCA28)"/>')
        for rpr in re.findall(r"<w:rPr>(.*?)</w:rPr>", side, re.S):   # color must precede sz/szCs/highlight (OOXML element order)
            if "<w:sz" in rpr and "<w:color" in rpr:
                self.assertLess(rpr.index("<w:color"), rpr.index("<w:sz"))
        main = tbl.split("</w:tc>")[1]
        self.assertNotIn('w:val="ECEFF1"', main)

    def test_timeline_has_a_continuous_left_bar_on_every_entry_paragraph(self):
        xml = docx_xml(self.docx("timeline"))
        bar = '<w:pBdr><w:left w:val="single" w:sz="18" w:space="10" w:color="00796B"/></w:pBdr>'
        self.assertGreater(xml.count(bar), 15)
        heading_style = docx_xml(self.docx("timeline"), "word/styles.xml")
        self.assertIn('w:left w:val="single" w:sz="36"', heading_style)       # bar-style section headings
        ind = set(re.findall(r'<w:p><w:pPr><w:pStyle w:val="Heading2"/><w:keepNext/>' + re.escape(bar) + r'<w:tabs>.*?<w:ind w:left="(\d+)"', xml))
        self.assertEqual(ind, {"300"})

    def test_date_left_uses_tab_and_hanging_indent_not_a_table(self):
        f = self.docx("date-left")
        xml = docx_xml(f)
        self.assertNotIn("<w:tbl>", xml)
        col = round(40 * 56.693)
        self.assertIn(f'<w:tab w:val="left" w:pos="{col}"/>', xml)
        self.assertIn(f'w:left="{col}" w:hanging="{col}"', xml)
        text = inspect_docx(f)["text"]
        self.assertRegex(text, r"Feb 2021 – Present\tNorthwind Analytics")

    def test_developer_mono_headings_carry_the_prefix(self):
        text = inspect_docx(self.docx("developer-mono"))["text"]
        for h in ("// Summary", "// Experience", "// Skills"):
            self.assertIn(h, text)

    def test_harvard_puts_summary_then_education_first_and_centres_the_header(self):
        f = self.docx("harvard")
        text = inspect_docx(f)["text"]
        self.assertLess(text.index("Education"), text.index("Experience"))
        self.assertIn('<w:jc w:val="center"/>', docx_xml(f))
        self.assertIn('w:ascii="Times New Roman"', docx_xml(f, "word/styles.xml"))

    def test_every_new_template_keeps_all_source_text_zh_and_en(self):
        for src in (RICH_JSON, RICH_MD):
            for t in NEW:
                with self.subTest(t=t, src=src.name):
                    text = inspect_docx(self.docx(t, src))["text"]
                    for token in (("Maya Chen", "Northwind Analytics", "Contoso Retail Labs", "Open Design Tokens", "University of Washington", "Figma")
                                  if src == RICH_JSON else ("周明", "北辰数据科技有限公司", "统一指标平台", "示例理工大学", "Kubernetes")):
                        self.assertIn(token, text)


class WordRendering(TempCase):
    """Real Word export of both rich samples with every new template."""

    def test_word_renders_every_new_template_with_all_text(self):
        if not envinfo.find_word()["available"]:
            self.skipTest("blocked_by_environment: Microsoft Word not available")
        for src in (RICH_JSON, RICH_MD):
            for t in NEW:
                with self.subTest(t=t, src=src.name):
                    p = run("generate_resume.py", "--input", src, "--output-dir", self.tmp / "o", "--formats", "docx,pdf", "--template", t,
                            "--prefix", f"{t}-{src.suffix[1:]}", "--pdf-backend", "word")
                    self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
                    rep = json.loads((self.tmp / "o" / f"{t}-{src.suffix[1:]}.report.json").read_text(encoding="utf-8"))
                    v = rep["artifacts"]["pdf"]["verification"]
                    self.assertEqual(rep["pdf_status"], "passed")
                    self.assertTrue(v["fonts_all_embedded"])
                    self.assertGreaterEqual(v["pages"], 1)
                    self.assertLessEqual(v["pages"], 3, "a 'rich' sample should fit in at most 3 pages")
                    if src == RICH_MD:
                        self.assertEqual(v.get("cjk_missing", 0), 0)


if __name__ == "__main__":
    unittest.main()
