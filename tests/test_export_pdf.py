"""PDF tests use an environment matrix:

| environment                     | expectation                                              |
| no PDF backend (simulated)      | exit 4, blocked_by_environment report, no PDF file       |
| LibreOffice installed           | real export + verification                               |
| Microsoft Word installed        | real export + verification (Chinese text, fonts, pages)  |
Tests needing a missing backend are skipped with 'blocked_by_environment: ...' (counted separately in reports).
"""
import json
import os
import sys
import unittest
from pathlib import Path

from helpers import NO_BACKENDS, ROOT, TempCase, en, make_min_pdf, requires_backend, run, zh

from resume_design import envinfo
from resume_design import pdf as pdfmod


class VerifyPdfUnit(TempCase):
    def test_minimal_valid_pdf_passes_structure_and_text(self):
        f = self.tmp / "ok.pdf"
        f.write_bytes(make_min_pdf("Hello Resume Toolkit"))
        r = pdfmod.verify_pdf(f, expected_text="Hello Resume Toolkit", page_limit=1)
        if not envinfo.find_pdftotext()["available"] and not envinfo.python_modules()["pypdf"]:
            self.assertEqual(r["text_check"], "blocked_by_environment")
        else:
            self.assertEqual(r["status"], "passed", r)
            self.assertEqual(r["text_check"], "passed")
        self.assertEqual(r["pages"], 1)
        self.assertFalse(r["errors"])
        self.assertFalse(r["fonts_all_embedded"] is True)  # Helvetica not embedded: must not be claimed

    def test_fake_empty_and_truncated_pdfs_fail(self):
        for name, data in {"empty.pdf": b"", "fake.pdf": b"%PDF-1.4\n" + b"x" * 600, "text.pdf": b"hello world" * 100,
                           "trunc.pdf": make_min_pdf()[:-30],
                           "noheader.pdf": make_min_pdf().replace(b"%PDF-1.4", b"JUNK-1.4")}.items():
            f = self.tmp / name
            f.write_bytes(data)
            r = pdfmod.verify_pdf(f)
            self.assertEqual(r["status"], "failed", name)
            self.assertTrue(r["errors"], name)
        self.assertEqual(pdfmod.verify_pdf(self.tmp / "missing.pdf")["status"], "failed")

    def test_expected_text_mismatch_fails(self):
        if not envinfo.find_pdftotext()["available"]:
            self.skipTest("blocked_by_environment: pdftotext not available")
        f = self.tmp / "ok.pdf"
        f.write_bytes(make_min_pdf("Hello Resume Toolkit"))
        r = pdfmod.verify_pdf(f, expected_text="Completely different sentence about Kubernetes clusters")
        self.assertEqual(r["status"], "failed")


class NoBackend(TempCase):
    """CI / machine without Word or LibreOffice (simulated through the documented env switch)."""

    def make_docx(self):
        src = self.write_json("r.json", zh())
        p = run("generate_resume.py", "--input", src, "--output-dir", self.tmp / "o", "--formats", "docx")
        self.assertEqual(p.returncode, 0, p.stderr)
        return self.tmp / "o" / "r.docx"

    def test_export_pdf_exit_4_with_report_and_no_pdf(self):
        docx = self.make_docx()
        rep = self.tmp / "pdf-report.json"
        p = run("export_pdf.py", "--input", docx, "--output-dir", self.tmp / "o", "--report", rep, env=NO_BACKENDS)
        self.assertEqual(p.returncode, 4, p.stderr)
        self.assertEqual(list((self.tmp / "o").glob("*.pdf")), [])
        self.assertEqual(list((self.tmp / "o").glob(".rd-*")), [], "no temp files left")
        r = json.loads(rep.read_text(encoding="utf-8"))
        self.assertEqual(r["status"], "blocked_by_environment")
        self.assertEqual({a["backend"] for a in r["attempts"]}, {"word", "libreoffice"})
        self.assertTrue(all(a["result"] == "unavailable" for a in r["attempts"]))
        self.assertTrue(r["alternatives"])
        self.assertIn("alternative", p.stderr)

    def test_generate_with_pdf_reports_partial_success(self):
        src = self.write_json("r.json", zh())
        p = run("generate_resume.py", "--input", src, "--output-dir", self.tmp / "o", "--formats", "md,docx,pdf", env=NO_BACKENDS)
        self.assertEqual(p.returncode, 4)
        self.assertIn("PARTIAL SUCCESS", p.stderr)
        self.assertTrue((self.tmp / "o" / "r.md").is_file() and (self.tmp / "o" / "r.docx").is_file())
        self.assertFalse((self.tmp / "o" / "r.pdf").exists())
        rep = json.loads((self.tmp / "o" / "r.report.json").read_text(encoding="utf-8"))
        self.assertEqual(rep["pdf_status"], "blocked_by_environment")
        self.assertEqual(rep["failed_stage"], "pdf")
        self.assertTrue(rep["partial_success"])
        self.assertNotEqual(rep["status"], "ready_to_submit")

    def test_pdf_only_cleans_intermediate_docx(self):
        src = self.write_json("r.json", zh())
        run("generate_resume.py", "--input", src, "--output-dir", self.tmp / "o", "--formats", "pdf", env=NO_BACKENDS)
        self.assertEqual([f.name for f in (self.tmp / "o").iterdir() if f.suffix in (".docx", ".pdf")], [])

    def test_explicit_backend_unavailable(self):
        docx = self.make_docx()
        p = run("export_pdf.py", "--input", docx, "--backend", "libreoffice", env=NO_BACKENDS)
        self.assertEqual(p.returncode, 4)
        p = run("export_pdf.py", "--input", docx, "--backend", "nonsense")
        self.assertEqual(p.returncode, 2)

    def test_bad_inputs(self):
        self.assertEqual(run("export_pdf.py", "--input", self.tmp / "missing.docx").returncode, 2)
        txt = self.tmp / "x.docx"
        txt.write_text("not a docx", encoding="utf-8")
        self.assertEqual(run("export_pdf.py", "--input", txt).returncode, 2)
        js = self.write_json("r.json", zh())
        self.assertEqual(run("export_pdf.py", "--input", js).returncode, 2)

    def test_dry_run_detects_only(self):
        docx = self.make_docx()
        p = run("export_pdf.py", "--input", docx, "--dry-run", env=NO_BACKENDS)
        self.assertEqual(p.returncode, 0)
        self.assertIn("NOT available", p.stdout)
        self.assertEqual(list((self.tmp / "o").glob("*.pdf")), [])


class BackendFailureHandling(TempCase):
    def test_failing_stub_soffice_gives_exit_4_not_fake_pdf(self):
        """A LibreOffice-like executable that fails must produce failure, never a PDF."""
        if sys.platform != "win32":
            self.skipTest("stub uses a .cmd file")
        stub = self.tmp / "soffice.cmd"
        stub.write_text("@echo off\r\necho simulated conversion failure 1>&2\r\nexit /b 7\r\n")
        src = self.write_json("r.json", en())
        self.assertEqual(run("generate_resume.py", "--input", src, "--output-dir", self.tmp / "o", "--formats", "docx").returncode, 0)
        code = (
            "import sys; sys.path.insert(0, %r)\n"
            "from resume_design import pdf, envinfo\n"
            "from pathlib import Path\n"
            "envinfo.find_libreoffice = lambda: {'name':'libreoffice','available':True,'path':%r,'version':None,'note':''}\n"
            "envinfo.find_word = lambda: {'name':'word','available':False,'path':None,'version':None,'note':'off'}\n"
            "try:\n"
            "    pdf.export_pdf(Path(%r), Path(%r))\n"
            "    print('NO-ERROR')\n"
            "except Exception as e:\n"
            "    print('ERR', getattr(e,'code',None), e.result['status'], e.result['attempts'][-1]['result'])\n"
        ) % (str(ROOT), str(stub), str(self.tmp / "o" / "r.docx"), str(self.tmp / "o" / "r.pdf"))
        import subprocess
        p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertIn("ERR 4 failed error", p.stdout, p.stdout + p.stderr)
        self.assertFalse((self.tmp / "o" / "r.pdf").exists())
        self.assertEqual(list((self.tmp / "o").glob(".rd-*")), [])

    def test_existing_pdf_not_overwritten_logic(self):
        existing = self.tmp / "keep.pdf"
        existing.write_bytes(make_min_pdf("keep"))
        from resume_design.common import ToolError, commit_file, tmp_path_for
        t = tmp_path_for(existing)
        t.write_bytes(make_min_pdf("new"))
        with self.assertRaises(ToolError):
            commit_file(t, existing, force=False)
        self.assertIn(b"keep", existing.read_bytes())
        t.unlink()


class RealWord(TempCase):
    @requires_backend("word")
    def test_word_exports_verified_pdf_chinese_and_fonts(self):
        src = self.write_json("r.json", zh())
        out = self.tmp / "o"
        p = run("generate_resume.py", "--input", src, "--output-dir", out, "--formats", "md,docx,pdf", "--pdf-backend", "word")
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        pdf = out / "r.pdf"
        data = pdf.read_bytes()
        self.assertTrue(data.startswith(b"%PDF-") and len(data) > 5000)
        rep = json.loads((out / "r.report.json").read_text(encoding="utf-8"))
        v = rep["artifacts"]["pdf"]["verification"]
        self.assertEqual(rep["pdf_status"], "passed")
        self.assertEqual(rep["artifacts"]["pdf"]["backend"], "word")
        self.assertGreaterEqual(v["pages"], 1)
        self.assertEqual(v["cjk_missing"], 0)
        self.assertTrue(v["fonts"])
        self.assertTrue(v["fonts_all_embedded"])
        self.assertIn(v["text_check"], ("passed", "blocked_by_environment"))
        if envinfo.find_pdftotext()["available"]:
            self.assertEqual(v["text_check"], "passed")
            text = pdfmod.extract_text(pdf)[0]
            for token in ("测试用户", "虚构科技有限公司", "Java"):
                self.assertIn(token, text.replace(" ", ""))

    @requires_backend("word")
    def test_word_export_standalone_cli_and_no_overwrite(self):
        src = self.write_json("e.json", en())
        out = self.tmp / "o"
        self.assertEqual(run("generate_resume.py", "--input", src, "--output-dir", out, "--formats", "docx").returncode, 0)
        r1 = run("export_pdf.py", "--input", out / "e.docx", "--backend", "word")
        self.assertEqual(r1.returncode, 0, r1.stderr + r1.stdout)
        first = (out / "e.pdf").read_bytes()
        r2 = run("export_pdf.py", "--input", out / "e.docx")
        self.assertEqual(r2.returncode, 0, r2.stderr)
        self.assertEqual((out / "e.pdf").read_bytes(), first)
        self.assertTrue((out / "e-1.pdf").is_file())

    @requires_backend("word")
    def test_all_templates_render_via_word(self):
        from resume_design import templates
        for t in templates.list_templates():
            src = self.write_json(f"{t}.json", zh())
            p = run("generate_resume.py", "--input", src, "--output-dir", self.tmp / "o", "--formats", "docx,pdf",
                    "--template", t, "--pdf-backend", "word")
            self.assertEqual(p.returncode, 0, f"{t}: {p.stderr}")


class RealLibreOffice(TempCase):
    @requires_backend("libreoffice")
    def test_libreoffice_exports_verified_pdf(self):
        src = self.write_json("r.json", zh())
        p = run("generate_resume.py", "--input", src, "--output-dir", self.tmp / "o", "--formats", "docx,pdf", "--pdf-backend", "libreoffice")
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        rep = json.loads((self.tmp / "o" / "r.report.json").read_text(encoding="utf-8"))
        self.assertEqual(rep["pdf_status"], "passed")
        self.assertEqual(rep["artifacts"]["pdf"]["verification"]["cjk_missing"], 0)


if __name__ == "__main__":
    unittest.main()
