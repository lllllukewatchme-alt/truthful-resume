"""Regression tests for the audit findings P0-1 .. P0-4 (see audit-2026-10-25/audit-report.md F1, F2, F3, F6).
Written before the fixes: each test failed against 0.1.0."""
import contextlib
import importlib.util
import io
import json
import sys
import unittest
from unittest import mock

from helpers import ROOT, SCRIPTS, TempCase, docx_xml, en, run, sha, zh

from resume_design.docx_writer import inspect_docx


def load_script(name):
    spec = importlib.util.spec_from_file_location(f"rg_{name}", SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def no_traceback(case, p):
    case.assertNotIn("Traceback (most recent call last)", p.stdout + p.stderr)


class P01InputProtection(TempCase):
    """P0-1: a target (output or report) that is the input file must be refused, with or without --force."""

    def test_force_md_input_same_as_target_refused(self):
        src = self.tmp / "me.md"
        src.write_text((ROOT / "examples/sample_resume.md").read_text(encoding="utf-8") + "\n## 开源贡献\n- 维护者\n", encoding="utf-8")
        before = sha(src)
        for extra in ([], ["--force"]):
            p = run("generate_resume.py", "--input", src, "--output-dir", self.tmp, "--formats", "md", *extra)
            if extra:
                self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
                self.assertIn("input", p.stderr.lower())
            self.assertEqual(sha(src), before, f"input modified with {extra}")
        self.assertIn("开源贡献", src.read_text(encoding="utf-8"))

    def test_force_json_input_same_as_report_refused(self):
        src = self.write_json("r.json", en())
        before = sha(src)
        for extra in ([], ["--force"]):
            p = run("generate_resume.py", "--input", src, "--output-dir", self.tmp / "o", "--formats", "md", "--report", src, *extra)
            self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
            self.assertEqual(sha(src), before)

    def test_case_variant_of_same_path_refused_on_windows(self):
        if sys.platform != "win32":
            self.skipTest("case-insensitive file system semantics are Windows-specific")
        src = self.tmp / "me.md"
        src.write_text((ROOT / "examples/sample_resume.md").read_text(encoding="utf-8"), encoding="utf-8")
        before = sha(src)
        p = run("generate_resume.py", "--input", src, "--output-dir", str(self.tmp).upper(), "--prefix", "ME", "--formats", "md", "--force")
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertEqual(sha(src), before)

    def test_other_scripts_refuse_report_equal_to_input(self):
        src = self.write_json("r.json", en())
        jd = self.tmp / "jd.md"
        jd.write_text("# Role\n## Requirements\n- Java\n", encoding="utf-8")
        docx_dir = self.tmp / "o"
        run("generate_resume.py", "--input", src, "--output-dir", docx_dir, "--formats", "docx")
        cases = [("validate_resume.py", ["--input", src, "--report", src, "--force"], src),
                 ("match_jd.py", ["--input", src, "--jd", jd, "--report", src, "--force"], src),
                 ("match_jd.py", ["--input", src, "--jd", jd, "--report", jd, "--force"], jd),
                 ("export_pdf.py", ["--input", docx_dir / "r.docx", "--report", docx_dir / "r.docx", "--force"], docx_dir / "r.docx")]
        for script, args, victim in cases:
            before = sha(victim)
            p = run(script, *args)
            self.assertEqual(p.returncode, 2, f"{script}: {p.stdout}{p.stderr}")
            self.assertEqual(sha(victim), before, script)

    def test_inspect_environment_report_refuses_existing_file_without_force(self):
        victim = self.tmp / "keep.json"
        victim.write_text("{}", encoding="utf-8")
        before = sha(victim)
        run("inspect_environment.py", "--report", victim)
        self.assertEqual(sha(victim), before)


class P02UnknownSections(TempCase):
    """P0-2: content that cannot be rendered must be reported and must keep the status below 'validated'."""

    def make(self):
        text = (ROOT / "examples/sample_resume.md").read_text(encoding="utf-8") + "\n## 开源贡献\n- 维护某开源项目\n\n## Hobbies\n- Chess\n"
        src = self.tmp / "us.md"
        src.write_text(text, encoding="utf-8")
        return src

    def test_generate_reports_unknown_sections(self):
        p = self.gen(self.make(), "--formats", "md,docx")
        self.assertEqual(p.returncode, 0, p.stderr)
        rep = json.loads((self.tmp / "out/us.report.json").read_text(encoding="utf-8"))
        finds = [f for f in rep["A_automated"]["findings"] if f["id"] == "section.unknown"]
        self.assertEqual(len(finds), 2)
        self.assertIn("开源贡献", json.dumps(finds, ensure_ascii=False))
        self.assertEqual(rep["status"], "needs_review")
        self.assertIn("section.unknown", p.stdout)  # visible in the console report, not only in JSON

    def test_validate_reports_unknown_sections(self):
        p = run("validate_resume.py", "--input", self.make())
        self.assertIn("section.unknown", p.stdout)
        self.assertIn("needs_review", p.stdout)
        self.assertEqual(run("validate_resume.py", "--input", self.make(), "--strict").returncode, 5)

    def test_known_sections_unaffected(self):
        p = run("validate_resume.py", "--input", ROOT / "examples/sample_resume.md")
        self.assertNotIn("section.unknown", p.stdout)


class P03ValidateGenerateConsistency(TempCase):
    """P0-3: accepted input must generate; the Markdown round-trip guard must not block DOCX."""

    def with_exp(self, **kw):
        d = zh()
        d["experience"][0].update(kw)
        return d

    def test_lenient_dates_generate_and_are_normalised(self):
        for st, en_ in (("2020-5", "2021-6"), ("May 2020", "Jun 2021"), ("2020/05", "2021/06")):
            src = self.write_json("d.json", self.with_exp(start=st, end=en_))
            self.assertEqual(run("validate_resume.py", "--input", src).returncode, 0, st)
            p = self.gen(src, "--formats", "md,docx", "--force")
            self.assertEqual(p.returncode, 0, f"{st}: {p.stderr}")
            md = (self.tmp / "out/d.md").read_text(encoding="utf-8")
            self.assertIn("2020.05 – 2021.06", md, st)
            self.assertIn("2020.05", inspect_docx(self.tmp / "out/d.docx")["text"], st)

    def test_newlines_in_fields(self):
        d = zh()
        d["basics"]["summary"] = "第一段\n\n\n第二段"
        d["experience"][0]["bullets"] = ["line one\nline two\n\n\nline three", "- looks like a bullet\n## looks like heading"]
        src = self.write_json("n.json", d)
        p = self.gen(src, "--formats", "md,docx")
        self.assertEqual(p.returncode, 0, p.stderr)
        text = inspect_docx(self.tmp / "out/n.docx")["text"]
        for frag in ("line one", "line two", "line three", "looks like a bullet", "第二段"):
            self.assertIn(frag, text)
        md = (self.tmp / "out/n.md").read_text(encoding="utf-8")
        from resume_design import mdio
        back = mdio.parse_markdown(md)
        self.assertEqual(len(back["experience"][0]["bullets"]), 2)

    def test_pipe_in_names_round_trips(self):
        d = zh()
        d["experience"][0].update(organization="Acme | Labs", role="Lead | Platform", location="A|B")
        d["certificates"] = [{"name": "X | Y", "issuer": "Z | W", "date": "2019-11"}]
        src = self.write_json("p.json", d)
        p = self.gen(src, "--formats", "md,docx")
        self.assertEqual(p.returncode, 0, p.stderr)
        from resume_design import mdio
        back = mdio.parse_markdown((self.tmp / "out/p.md").read_text(encoding="utf-8"))
        e = back["experience"][0]
        self.assertEqual((e["organization"], e["role"], e["location"]), ("Acme | Labs", "Lead | Platform", "A|B"))
        self.assertEqual((back["certificates"][0]["name"], back["certificates"][0]["issuer"]), ("X | Y", "Z | W"))
        self.assertIn("Acme | Labs", inspect_docx(self.tmp / "out/p.docx")["text"])

    def test_validate_ok_implies_generate_ok(self):
        variants = [self.with_exp(start="2020", end="2021"), self.with_exp(start="2020-5", end=""),
                    self.with_exp(bullets=["a\nb"]), self.with_exp(organization="A | B")]
        for i, d in enumerate(variants):
            src = self.write_json(f"v{i}.json", d)
            if run("validate_resume.py", "--input", src).returncode == 0:
                p = self.gen(src, "--formats", "md,docx")
                self.assertEqual(p.returncode, 0, f"variant {i}: {p.stderr}")

    def test_markdown_guard_failure_does_not_block_docx(self):
        gen = load_script("generate_resume")
        src = self.write_json("g.json", zh())
        out = self.tmp / "out"
        bad = zh()
        bad["experience"][0]["start"] = "1999-01"       # simulated lossy markdown serialisation
        from resume_design.pipeline import load_resume
        real = load_resume(src)[0]
        bad_back = json.loads(json.dumps(real))
        bad_back["experience"][0]["start"] = "1999-01"
        buf_o, buf_e = io.StringIO(), io.StringIO()
        with mock.patch.object(gen, "parse_markdown", return_value=bad_back), contextlib.redirect_stdout(buf_o), contextlib.redirect_stderr(buf_e):
            rc = gen.main(["--input", str(src), "--output-dir", str(out), "--formats", "md,docx"])
        self.assertEqual(rc, 4)
        self.assertTrue((out / "g.docx").is_file(), "DOCX must still be produced")
        self.assertFalse((out / "g.md").exists(), "lossy Markdown must not be written")
        rep = json.loads((out / "g.report.json").read_text(encoding="utf-8"))
        self.assertTrue(rep["partial_success"])
        self.assertEqual(rep["failed_stage"], "md")
        self.assertIn("PARTIAL SUCCESS", buf_e.getvalue())


class P04NoUnhandledCrashes(TempCase):
    """P0-4: every failure is an exit code from {2,4,5} with a one-line message, never a Traceback / exit 1."""

    def check_rc(self, d, name, allowed=(2, 5)):
        src = self.write_json(f"{name}.json", d)
        p = self.gen(src, "--formats", "md,docx")
        no_traceback(self, p)
        self.assertIn(p.returncode, allowed, f"{name}: rc={p.returncode} {p.stderr[-200:]}")
        self.assertEqual(sorted(f.name for f in (self.tmp / "out").glob("*.md")) if (self.tmp / "out").exists() else [], [])
        v = run("validate_resume.py", "--input", src)
        no_traceback(self, v)
        self.assertIn(v.returncode, allowed)

    def test_wrong_types(self):
        mutations = {"experience-int": lambda d: d.__setitem__("experience", 5), "skills-int": lambda d: d.__setitem__("skills", 5),
                     "education-str": lambda d: d.__setitem__("education", "abc"), "name-int": lambda d: d["basics"].__setitem__("name", 123),
                     "basics-list": lambda d: d.__setitem__("basics", []), "bullets-str": lambda d: d["experience"][0].__setitem__("bullets", "x"),
                     "certs-int": lambda d: d.__setitem__("certificates", 3), "prefs-str": lambda d: d.__setitem__("preferences", "x"),
                     "meta-str": lambda d: d.__setitem__("meta", "x"), "target-int": lambda d: d.__setitem__("target", 1)}
        for name, mut in mutations.items():
            d = en()
            mut(d)
            with self.subTest(name):
                self.check_rc(d, name)

    def test_lone_surrogate(self):
        src = self.tmp / "sur.json"
        src.write_bytes(b'{"basics":{"name":"A\\ud800B","email":"a@b.co"},"education":[{"organization":"U"}]}')
        for script, args in (("generate_resume.py", ["--input", src, "--output-dir", self.tmp / "o", "--formats", "md,docx"]),
                             ("validate_resume.py", ["--input", src])):
            p = run(script, *args)
            no_traceback(self, p)
            self.assertIn(p.returncode, (2, 5), f"{script}: {p.stderr[-200:]}")

    def test_locked_target_with_force(self):
        if sys.platform != "win32":
            self.skipTest("file locking semantics are Windows-specific")
        src = self.write_json("r.json", en())
        self.assertEqual(self.gen(src, "--formats", "md,docx").returncode, 0)
        target = self.tmp / "out/r.docx"
        before = sha(target)
        with open(target, "rb"):
            p = self.gen(src, "--formats", "md,docx", "--force")
        no_traceback(self, p)
        self.assertEqual(p.returncode, 4, p.stderr)
        self.assertIn("r.docx", p.stderr)
        self.assertEqual(sha(target), before)
        self.assertEqual([f.name for f in (self.tmp / "out").iterdir() if f.name.startswith(".rd-")], [])

    def test_unexpected_exception_is_mapped_to_exit_4(self):
        for script, patch_target, args in (("generate_resume", "resolve_context", ["--input", "{src}", "--output-dir", "{out}"]),
                                            ("validate_resume", "resolve_context", ["--input", "{src}"]),
                                            ("match_jd", "load_resume", ["--input", "{src}", "--jd", "{src}"])):
            mod = load_script(script)
            src = self.write_json("b.json", en())
            argv = [a.format(src=src, out=self.tmp / "o") for a in args]
            e, o = io.StringIO(), io.StringIO()
            with mock.patch.object(mod, patch_target, side_effect=RuntimeError("boom with tester@example.com")), \
                    contextlib.redirect_stderr(e), contextlib.redirect_stdout(o):
                rc = mod.main(argv)
            self.assertEqual(rc, 4, script)
            self.assertIn("unexpected", e.getvalue().lower())
            self.assertNotIn("Traceback", e.getvalue())
            self.assertNotIn("tester@example.com", e.getvalue())


class P16SkillWording(unittest.TestCase):
    """P1-6: behavioural rules that must be explicit in both SKILL.md files."""

    FILES = ["adapters/claude-code/SKILL.md", "adapters/codex/SKILL.md"]

    def test_rules_present(self):
        for f in self.FILES:
            t = (ROOT / f).read_text(encoding="utf-8")
            flat = " ".join(t.split())
            self.assertIn("core/workflow.md", flat.split("Generate")[0], f"{f}: must require reading workflow before generating")
            self.assertRegex(flat, r"(?i)read .*core/workflow\.md.*before", f)
            self.assertRegex(flat, r"(?i)only .*`generated:`", f)                       # report files only if the script printed it
            self.assertRegex(flat, r"(?i)non-zero exit", f)                               # any non-zero exit = failure
            self.assertRegex(flat, r"(?i)never .*`--force` .*unless the user", f)         # no --force on own initiative


class P11CreativeLayout(TempCase):
    """P1-1: two-column (table) layout must flow across pages. Root cause (verified in Word): keepNext chains inside
    table cells made Word move the whole row to page 2, leaving page 1 with only the header."""

    def long_data(self):
        d = en()
        d["experience"] = [{"organization": f"Fictional Corp {i}", "role": "Engineer", "start": f"{2024 - i}-01", "end": f"{2024 - i}-12",
                            "bullets": [f"Delivered milestone {j} for platform {i} with cross-team coordination and documented rollout" for j in range(6)]}
                           for i in range(10)]
        d["certificates"] = [{"name": f"Certificate {i}", "issuer": "Example Authority", "date": "2019-11"} for i in range(3)]
        return d

    def test_no_keep_with_next_inside_table_cells(self):
        src = self.write_json("c.json", self.long_data())
        self.assertEqual(self.gen(src, "--formats", "docx", "--template", "creative").returncode, 0)
        import re
        xml = docx_xml(self.tmp / "out/c.docx")
        tbl = re.search(r"<w:tbl>.*</w:tbl>", xml, re.S).group(0)
        self.assertNotIn("<w:keepNext/>", tbl)
        paras = re.findall(r"<w:p>.*?</w:p>", tbl, re.S)
        styled = [p for p in paras if 'w:pStyle w:val="Heading' in p]
        self.assertTrue(styled)
        self.assertTrue(all('<w:keepNext w:val="0"/>' in p for p in styled), "headings in cells must switch keepNext off")
        outside = xml.replace(tbl, "")
        self.assertIn("<w:keepNext/>", docx_xml(self.tmp / "out/c.docx", "word/styles.xml") + outside)  # other templates/areas unchanged

    def test_single_column_templates_keep_their_keep_with_next(self):
        src = self.write_json("m.json", self.long_data())
        self.assertEqual(self.gen(src, "--formats", "docx", "--template", "modern-business").returncode, 0)
        self.assertIn("<w:keepNext/>", docx_xml(self.tmp / "out/m.docx"))
        self.assertNotIn('<w:keepNext w:val="0"/>', docx_xml(self.tmp / "out/m.docx"))

    def test_sidebar_certificates_are_stacked_not_wrapped_mid_date(self):
        src = self.write_json("c.json", self.long_data())
        self.assertEqual(self.gen(src, "--formats", "docx", "--template", "creative").returncode, 0)
        text = inspect_docx(self.tmp / "out/c.docx")["text"]
        self.assertIn("Certificate 0\nExample Authority · Nov 2019", text)

    def test_word_first_page_is_filled(self):
        from helpers import requires_backend
        from resume_design import envinfo
        if not envinfo.find_word()["available"]:
            self.skipTest("blocked_by_environment: word not available")
        if not envinfo.find_pdftotext()["available"]:
            self.skipTest("blocked_by_environment: pdftotext not available")
        import subprocess
        src = self.write_json("c.json", self.long_data())
        p = self.gen(src, "--formats", "docx,pdf", "--template", "creative", "--pdf-backend", "word")
        self.assertEqual(p.returncode, 0, p.stderr)
        text = subprocess.run(["pdftotext", "-enc", "UTF-8", str(self.tmp / "out/c.pdf"), "-"], capture_output=True,
                              encoding="utf-8", errors="replace").stdout.split("\f")
        page1 = [l for l in text[0].splitlines() if l.strip()]
        self.assertGreaterEqual(len(page1), 25, f"page 1 nearly empty: {page1[:6]}")
        self.assertIn("Fictional Corp 0", text[0])


class P12DateFieldDetection(unittest.TestCase):
    """P1-2: only a field that is entirely a date (range) is the date; a year inside a role/location is just text."""

    def parse(self, head):
        from resume_design import mdio
        d = mdio.parse_markdown(f"# T\n- email: a@b.co\n## Experience\n### {head}\n- x\n")
        return d["experience"][0]

    def test_year_inside_role_or_location_is_not_a_date(self):
        e = self.parse("Acme | Lead of 2021 Migration | 2020.01 – 2022.03")
        self.assertEqual((e["role"], e["start"], e["end"]), ("Lead of 2021 Migration", "2020-01", "2022-03"))
        e = self.parse("Acme | 2021 Platform Lead | 2020.01 – present | Shanghai 2nd Campus 2020")
        self.assertEqual((e["role"], e["start"], e["end"], e["location"]), ("2021 Platform Lead", "2020-01", "present", "Shanghai 2nd Campus 2020"))
        e = self.parse("Acme | FY2021 Owner | 2020.01 – 2021.12")
        self.assertEqual((e["role"], e["start"]), ("FY2021 Owner", "2020-01"))

    def test_real_date_forms_still_recognised(self):
        for head, start, end in (("A | R | 2019年7月 – 至今", "2019-07", "present"), ("A | R | Jul 2015 – 2018/06", "2015-07", "2018-06"),
                                 ("A | R | 2020 – 2022", "2020", "2022"), ("A | R | 2018.06 - present", "2018-06", "present"),
                                 ("A | R | 2020-01 ~ 2020-12", "2020-01", "2020-12"), ("A | 2019.07 – Present", "2019-07", "present"),
                                 ("A | R | 2020", "2020", ""), ("A | R | 2019-07 to 2021-02", "2019-07", "2021-02")):
            e = self.parse(head)
            self.assertEqual((e["start"], e["end"]), (start, end), head)

    def test_end_to_end_role_with_year_validates_and_round_trips(self):
        import tempfile, pathlib
        with tempfile.TemporaryDirectory() as td:
            src = pathlib.Path(td) / "y.md"
            src.write_text("# 李四\n- email: li@example.com\n## 工作经历\n### 乙公司 | Lead of 2021 Migration | 2020.01 – 2022.03\n- 做事\n", encoding="utf-8")
            self.assertEqual(run("validate_resume.py", "--input", src).returncode, 0)
            p = run("generate_resume.py", "--input", src, "--output-dir", pathlib.Path(td) / "o", "--formats", "md,docx")
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn("Lead of 2021 Migration", (pathlib.Path(td) / "o/y.md").read_text(encoding="utf-8"))

    def test_json_org_with_pipe_and_role_with_year_round_trips(self):
        d = zh()
        d["experience"][0].update(organization="Acme | Labs", role="2021 Migration Lead")
        with __import__("tempfile").TemporaryDirectory() as td:
            import pathlib
            src = pathlib.Path(td) / "j.json"
            src.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            p = run("generate_resume.py", "--input", src, "--output-dir", pathlib.Path(td) / "o", "--formats", "md,docx")
            self.assertEqual(p.returncode, 0, p.stderr)


def make_pdf_pages(n: int, text: str = "Backend Engineer") -> bytes:
    """Minimal valid n-page PDF with extractable text (no fonts embedded)."""
    kids = " ".join(f"{3 + i} 0 R" for i in range(n))
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", f"<< /Type /Pages /Kids [{kids}] /Count {n} >>"]
    first_page_obj = 3
    content_start = first_page_obj + n
    font_obj = content_start + n
    for i in range(n):
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents {content_start + i} 0 R /Resources << /Font << /F1 {font_obj} 0 R >> >> >>")
    for i in range(n):
        stream = f"BT /F1 18 Tf 72 700 Td (Page {i + 1} {text}) Tj ET"
        objs.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
    objs.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out = b"%PDF-1.4\n"
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


class P13PageLimit(TempCase):
    """P1-3: a PDF longer than the user's page_limit must not be reported as 'validated'."""

    def test_status_logic(self):
        from resume_design import validate as V
        findings = [V._f("pdf.page_limit", "warning", "A", "rendered PDF has 3 pages, limit is 2")]
        status, reasons = V.compute_status(findings, en(), "passed", True)
        self.assertEqual(status, "needs_review")
        self.assertIn("page", " ".join(reasons).lower())

    def test_validate_pdf_longer_than_limit(self):
        d = {"basics": {"name": "Alex Test", "email": "a@example.com"}, "education": [{"organization": "Fictional University"}],
             "preferences": {"page_limit": 2}}
        words = "Alex Test a@example.com Fictional University"
        src = self.write_json("r.json", d)
        pdf3 = self.tmp / "three.pdf"
        pdf3.write_bytes(make_pdf_pages(3, words))
        p = run("validate_resume.py", "--input", src, "--pdf", pdf3)
        self.assertIn("pdf.page_limit", p.stdout)
        self.assertIn("needs_review", p.stdout)
        pdf2 = self.tmp / "two.pdf"
        pdf2.write_bytes(make_pdf_pages(2, words))
        p = run("validate_resume.py", "--input", src, "--pdf", pdf2)
        self.assertNotIn("pdf.page_limit", p.stdout)

    def test_strict_fails_on_page_overflow(self):
        d = en()
        d["preferences"] = {"page_limit": 1}
        src = self.write_json("r.json", d)
        pdf3 = self.tmp / "three.pdf"
        pdf3.write_bytes(make_pdf_pages(3))
        self.assertEqual(run("validate_resume.py", "--input", src, "--pdf", pdf3, "--strict").returncode, 5)

    def test_word_generate_long_resume_is_needs_review(self):
        from resume_design import envinfo
        if not envinfo.find_word()["available"]:
            self.skipTest("blocked_by_environment: word not available")
        d = en()
        d["preferences"] = {"page_limit": 1}
        d["experience"] = [{"organization": f"Fictional Corp {i}", "role": "Engineer", "start": f"{2024 - i}-01", "end": f"{2024 - i}-12",
                            "bullets": [f"Delivered milestone {j} for platform {i} with documented rollout" for j in range(6)]} for i in range(10)]
        src = self.write_json("long.json", d)
        p = self.gen(src, "--formats", "docx,pdf", "--pdf-backend", "word")
        self.assertEqual(p.returncode, 0, p.stderr)
        rep = json.loads((self.tmp / "out/long.report.json").read_text(encoding="utf-8"))
        self.assertEqual(rep["status"], "needs_review")
        self.assertTrue(any("page" in r.lower() for r in rep["status_reasons"]), rep["status_reasons"])


class P14ConfirmReady(TempCase):
    """P1-4: ready_to_submit needs a human action at the command line (--confirm-ready); data flags alone cap at 'validated'."""

    CONFIRMED = {"review": {"facts_confirmed": True, "contact_confirmed": True, "target_confirmed": True}}

    def data(self, **meta):
        d = en()
        d["meta"] = meta or self.CONFIRMED
        return d

    def status_of(self, out="out", name="r"):
        return json.loads((self.tmp / out / f"{name}.report.json").read_text(encoding="utf-8"))

    def test_data_flags_alone_are_not_enough(self):
        src = self.write_json("r.json", self.data())
        self.assertEqual(self.gen(src, "--formats", "md,docx").returncode, 0)
        rep = self.status_of()
        self.assertEqual(rep["status"], "validated")
        self.assertIn("--confirm-ready", " ".join(rep["status_reasons"]))

    def test_flag_plus_data_flags_gives_ready(self):
        src = self.write_json("r.json", self.data())
        self.assertEqual(self.gen(src, "--formats", "md,docx", "--confirm-ready").returncode, 0)
        rep = self.status_of()
        self.assertEqual(rep["status"], "ready_to_submit")
        self.assertTrue(rep.get("confirmed_via_cli"))

    def test_flag_without_data_flags_is_not_ready(self):
        src = self.write_json("r.json", en())
        self.assertEqual(self.gen(src, "--formats", "md,docx", "--confirm-ready").returncode, 0)
        rep = self.status_of()
        self.assertEqual(rep["status"], "validated")
        self.assertIn("meta.review", " ".join(rep["status_reasons"]))

    def test_flag_never_overrides_blockers(self):
        d = self.data()
        d["basics"]["phone"] = "{{MISSING:phone}}"
        src = self.write_json("r.json", d)
        self.assertEqual(self.gen(src, "--formats", "md,docx", "--confirm-ready").returncode, 0)
        self.assertEqual(self.status_of()["status"], "needs_review")
        d = self.data()
        d["basics"]["name"] = ""
        src = self.write_json("e.json", d)
        self.assertEqual(self.gen(src, "--formats", "md", "--confirm-ready").returncode, 5)

    def test_validate_resume_same_rule(self):
        src = self.write_json("r.json", self.data())
        self.assertIn("validated", run("validate_resume.py", "--input", src).stdout.split("\n")[0])
        self.assertIn("ready_to_submit", run("validate_resume.py", "--input", src, "--confirm-ready").stdout.split("\n")[0])

    def test_skill_files_forbid_unprompted_flag(self):
        for f in ("adapters/claude-code/SKILL.md", "adapters/codex/SKILL.md"):
            flat = " ".join((ROOT / f).read_text(encoding="utf-8").split())
            self.assertRegex(flat, r"(?i)never .*`--confirm-ready`.*unless the user", f)


class P15Language(TempCase):
    """P1-5: unsupported languages are rejected, not silently rendered with English labels; unknown locale is visible."""

    def test_unsupported_lang_rejected(self):
        src = self.write_json("r.json", en())
        p = self.gen(src, "--formats", "md", "--lang", "fr")
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("fr", p.stderr)
        self.assertIn("zh", p.stderr)          # tells the user what is supported
        self.assertFalse((self.tmp / "out").exists() and any((self.tmp / "out").iterdir()))

    def test_unsupported_language_in_data_rejected(self):
        d = en()
        d["target"]["language"] = "fr"
        src = self.write_json("r.json", d)
        self.assertEqual(self.gen(src, "--formats", "md").returncode, 2)
        self.assertEqual(run("validate_resume.py", "--input", src).returncode, 2)
        self.assertEqual(run("validate_resume.py", "--input", self.write_json("ok.json", en()), "--lang", "fr").returncode, 2)

    def test_supported_variants_accepted(self):
        for lang in ("zh", "en", "zh-CN", "en-GB", "EN"):
            src = self.write_json("r.json", en())
            p = self.gen(src, "--formats", "md", "--lang", lang, "--force")
            self.assertEqual(p.returncode, 0, f"{lang}: {p.stderr}")

    def test_unknown_locale_is_visible(self):
        src = self.write_json("r.json", en())
        p = run("validate_resume.py", "--input", src, "--locale", "xx-YY")
        self.assertEqual(p.returncode, 0)
        self.assertIn("locale.unknown", p.stdout)
        p = self.gen(src, "--formats", "md", "--locale", "xx-YY")
        self.assertIn("locale.unknown", p.stdout)


if __name__ == "__main__":
    unittest.main()
