"""P1-7 / P1-8: test gaps found by the 2026-10-24 audit (see audit-2026-10-25/audit-report.md section 4).
Each class says which defect category it guards. Tests that need Word / pdftotext are skipped with an explicit
'blocked_by_environment' reason, never silently passed."""
import json
import os
import subprocess
import sys
import unittest
import zipfile

from helpers import ROOT, SCRIPTS, TempCase, docx_xml, en, make_min_pdf, run, sha, zh

from resume_design import envinfo
from resume_design import pdf as pdfmod

WIN = sys.platform == "win32"


def word_pids() -> set:
    if not WIN:
        return set()
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq WINWORD.EXE", "/FO", "CSV", "/NH"], capture_output=True, text=True,
                         encoding="utf-8", errors="replace").stdout
    return {int(line.split(",")[1].strip('"')) for line in out.splitlines() if line.lower().startswith('"winword.exe"')}


def no_tb(case, p):
    case.assertNotIn("Traceback (most recent call last)", p.stdout + p.stderr)


# ---------------------------------------------------------------- category: "PDF generation fails but is reported as success"
class StubBackend(TempCase):
    """A LibreOffice-like program that exits 0 but produces nothing / junk / the wrong text must never yield a PDF."""

    def run_stub(self, mode: str, expected_text=None):
        if not WIN:
            self.skipTest("stub backend is a .cmd file")
        stub_py = self.tmp / "stub.py"
        stub_py.write_text(
            "import sys, os, pathlib\n"
            "args = sys.argv[1:]\n"
            "outdir = pathlib.Path(args[args.index('--outdir') + 1]); src = pathlib.Path(args[-1])\n"
            "mode = os.environ['STUB_MODE']\n"
            "if mode == 'junk': (outdir / (src.stem + '.pdf')).write_bytes(b'%PDF-1.4 junk ' + b'x' * 800)\n"
            "elif mode == 'wrongtext': (outdir / (src.stem + '.pdf')).write_bytes(open(os.environ['STUB_PDF'], 'rb').read())\n"
            "elif mode == 'empty': (outdir / (src.stem + '.pdf')).write_bytes(b'')\n", encoding="utf-8")
        stub = self.tmp / "soffice.cmd"
        stub.write_text(f'@echo off\r\n"{sys.executable}" "{stub_py}" %*\r\nexit /b 0\r\n')
        wrong = self.tmp / "wrong.pdf"
        wrong.write_bytes(make_min_pdf("Completely unrelated sentence about gardening tools"))
        src = self.write_json("r.json", en())
        self.assertEqual(run("generate_resume.py", "--input", src, "--output-dir", self.tmp / "o", "--formats", "docx").returncode, 0)
        code = (
            "import sys; sys.path.insert(0, %r)\n"
            "from resume_design import pdf, envinfo\n"
            "from resume_design.docx_writer import inspect_docx\n"
            "from pathlib import Path\n"
            "envinfo.find_libreoffice = lambda: {'name':'libreoffice','available':True,'path':%r,'version':None,'note':''}\n"
            "envinfo.find_word = lambda: {'name':'word','available':False,'path':None,'version':None,'note':'off'}\n"
            "d = Path(%r); txt = inspect_docx(d)['text']\n"
            "try:\n"
            "    pdf.export_pdf(d, Path(%r), expected_text=txt)\n"
            "    print('NO-ERROR')\n"
            "except Exception as e:\n"
            "    print('ERR', getattr(e, 'code', None), e.result['status'], e.result['attempts'][-1]['result'])\n"
        ) % (str(ROOT), str(stub), str(self.tmp / "o/r.docx"), str(self.tmp / "o/r.pdf"))
        p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env={**os.environ, "STUB_MODE": mode, "STUB_PDF": str(wrong), "PYTHONDONTWRITEBYTECODE": "1"})
        return p

    def assert_failed_cleanly(self, p, result):
        self.assertIn(result, p.stdout, p.stdout + p.stderr)
        self.assertNotIn("NO-ERROR", p.stdout)
        self.assertFalse((self.tmp / "o/r.pdf").exists(), "no PDF may be left behind")
        self.assertEqual([f.name for f in (self.tmp / "o").iterdir() if f.name.startswith(".rd-")], [])

    def test_exit_zero_without_output_file(self):
        self.assert_failed_cleanly(self.run_stub("none"), "ERR 4 failed error")

    def test_exit_zero_with_empty_pdf(self):
        self.assert_failed_cleanly(self.run_stub("empty"), "ERR 4 failed verification_failed")

    def test_exit_zero_with_junk_pdf(self):
        self.assert_failed_cleanly(self.run_stub("junk"), "ERR 4 failed verification_failed")

    def test_valid_pdf_with_wrong_text(self):
        if not envinfo.find_pdftotext()["available"] and not envinfo.python_modules()["pypdf"]:
            self.skipTest("blocked_by_environment: no PDF text extraction tool")
        self.assert_failed_cleanly(self.run_stub("wrongtext"), "ERR 4 failed verification_failed")


class PdfTextLoss(TempCase):
    """PDF opens but the (Chinese) text is gone: must be 'failed', with the loss reported."""

    def need_text_tool(self):
        if not envinfo.find_pdftotext()["available"] and not envinfo.python_modules()["pypdf"]:
            self.skipTest("blocked_by_environment: no PDF text extraction tool")

    def test_all_cjk_missing_fails(self):
        self.need_text_tool()
        f = self.tmp / "latin.pdf"
        f.write_bytes(make_min_pdf("Backend Engineer Fictional University"))
        r = pdfmod.verify_pdf(f, expected_text="后端开发工程师 虚构大学 Backend Engineer Fictional University")
        self.assertEqual(r["status"], "failed")
        self.assertTrue(any("CJK" in e for e in r["errors"]), r["errors"])
        self.assertEqual(r["cjk_missing"], r["cjk_expected"])
        self.assertEqual(r["text_check"], "failed")

    def test_no_cjk_expected_is_not_penalised(self):
        self.need_text_tool()
        f = self.tmp / "latin.pdf"
        f.write_bytes(make_min_pdf("Backend Engineer Fictional University"))
        r = pdfmod.verify_pdf(f, expected_text="Backend Engineer Fictional University")
        self.assertEqual(r["status"], "passed", r)

    def test_missing_text_tool_is_reported_not_passed(self):
        f = self.tmp / "latin.pdf"
        f.write_bytes(make_min_pdf("Backend Engineer"))
        with unittest_mock_patch(pdfmod, "extract_text", lambda p: (None, "none")):
            r = pdfmod.verify_pdf(f, expected_text="后端 Backend Engineer")
        self.assertEqual(r["text_check"], "blocked_by_environment")
        self.assertTrue(any("not verified" in w for w in r["warnings"]))


def unittest_mock_patch(obj, name, value):
    from unittest import mock
    return mock.patch.object(obj, name, value)


# ---------------------------------------------------------------- category: "installer dry-run modifies the target"
def tree_fp(root):
    return sorted((str(p.relative_to(root)), sha(p)) for p in root.rglob("*") if p.is_file()) if root.exists() else None


class InstallerDryRun(TempCase):
    def inst(self, *a):
        return run("install_skill.py", *a)

    def test_dry_run_leaves_existing_install_and_siblings_untouched(self):
        home = self.tmp / "h"
        self.assertEqual(self.inst("--target", "claude-code-user", "--home", home).returncode, 0)
        (home / ".claude/skills/other-skill").mkdir()
        (home / ".claude/skills/other-skill/SKILL.md").write_text("keep", encoding="utf-8")
        before = tree_fp(home)
        dirs_before = sorted(str(p.relative_to(home)) for p in home.rglob("*") if p.is_dir())
        for extra in ([], ["--backup"]):
            p = self.inst("--target", "claude-code-user", "--home", home, "--dry-run", *extra)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn("nothing written", p.stdout)
            self.assertEqual(tree_fp(home), before)
            self.assertEqual(sorted(str(p.relative_to(home)) for p in home.rglob("*") if p.is_dir()), dirs_before)

    def test_dry_run_project_targets_do_not_create_dot_folders(self):
        proj = self.tmp / "proj"
        proj.mkdir()
        for t in ("claude-code-project", "codex-project"):
            self.assertEqual(self.inst("--target", t, "--project-dir", proj, "--dry-run").returncode, 0)
        self.assertEqual(list(proj.iterdir()), [])

    def test_destination_is_a_file(self):
        home = self.tmp / "h"
        (home / ".claude/skills").mkdir(parents=True)
        (home / ".claude/skills/resume-design").write_text("i am a file", encoding="utf-8")
        p = self.inst("--target", "claude-code-user", "--home", home)
        no_tb(self, p)
        self.assertEqual(p.returncode, 2)
        self.assertEqual((home / ".claude/skills/resume-design").read_text(encoding="utf-8"), "i am a file")

    def test_bad_project_dir(self):
        p = self.inst("--target", "codex-project", "--project-dir", self.tmp / "nope")
        no_tb(self, p)
        self.assertEqual(p.returncode, 2)

    def test_installed_copy_skill_md_matches_adapter(self):
        home = self.tmp / "h"
        self.assertEqual(self.inst("--target", "claude-code-user", "--home", home).returncode, 0)
        self.assertEqual(sha(home / ".claude/skills/resume-design/SKILL.md"), sha(ROOT / "adapters/claude-code/SKILL.md"))
        self.assertEqual(self.inst("--target", "codex-user", "--home", home).returncode, 0)
        self.assertEqual(sha(home / ".agents/skills/resume-design/SKILL.md"), sha(ROOT / "adapters/codex/SKILL.md"))


# ---------------------------------------------------------------- category: "wrong exit code / crash"
class ExitCodeContract(TempCase):
    """Every script, fed hostile input, answers with a documented code (0/2/3/4/5), a one-line message, no Traceback."""

    def assert_contract(self, script, *args, allowed=(2, 3, 4, 5)):
        p = run(script, *args)
        no_tb(self, p)
        self.assertIn(p.returncode, allowed, f"{script} {args}: rc={p.returncode} {p.stderr[-200:]}")
        return p

    def test_hostile_inputs_for_every_script(self):
        binary = self.tmp / "bin.json"
        binary.write_bytes(bytes(range(256)) * 10)
        empty = self.tmp / "empty.json"
        empty.write_bytes(b"")
        zero_docx = self.tmp / "zero.docx"
        zero_docx.write_bytes(b"")
        trunc = self.tmp / "trunc.docx"
        run("generate_resume.py", "--input", self.write_json("ok.json", en()), "--output-dir", self.tmp / "o", "--formats", "docx")
        trunc.write_bytes((self.tmp / "o/ok.docx").read_bytes()[:300])
        directory = self.tmp / "adir"
        directory.mkdir()
        nul = "bad\x00name.json"
        for inp in (binary, empty, directory, self.tmp / "missing.json"):
            self.assert_contract("generate_resume.py", "--input", inp, "--output-dir", self.tmp / "g")
            self.assert_contract("validate_resume.py", "--input", inp)
            self.assert_contract("match_jd.py", "--input", inp, "--jd", inp)
        ok = self.write_json("good.json", en())
        for docx in (zero_docx, trunc, directory, binary):
            self.assert_contract("export_pdf.py", "--input", docx)
            self.assert_contract("validate_resume.py", "--input", ok, "--docx", docx)
        for pdf in (binary, directory, empty):
            self.assert_contract("validate_resume.py", "--input", ok, "--pdf", pdf)
        self.assert_contract("validate_resume.py", "--input", ok, "--compare", binary)
        self.assert_contract("match_jd.py", "--input", ok, "--jd", binary)
        self.assert_contract("match_jd.py", "--input", ok, "--jd", directory)

    def test_report_path_problems(self):
        ok = self.write_json("good.json", en())
        blocker = self.tmp / "afile"
        blocker.write_text("x")
        for rp in (blocker / "sub" / "r.json", "Z:\\no_such_drive\\r.json"):
            for script, args in (("validate_resume.py", ["--input", ok, "--report", rp]),
                                 ("generate_resume.py", ["--input", ok, "--output-dir", self.tmp / "o", "--formats", "md", "--report", rp]),
                                 ("inspect_environment.py", ["--report", rp])):
                p = run(script, *args)
                no_tb(self, p)
                self.assertIn(p.returncode, (2, 4), f"{script} {rp}: rc={p.returncode} {p.stderr[-160:]}")
                self.assertNotIn("unexpected", p.stderr.lower(), "must be a clear message, not the last-resort handler")

    def test_timeout_argument_validated(self):
        docx = self.tmp / "d.docx"
        run("generate_resume.py", "--input", self.write_json("ok.json", en()), "--output-dir", self.tmp, "--formats", "docx", "--prefix", "d")
        for bad in ("0", "-5", "abc", "1.5"):
            p = run("export_pdf.py", "--input", docx, "--timeout", bad, "--dry-run")
            no_tb(self, p)
            self.assertEqual(p.returncode, 2, f"--timeout {bad}: rc={p.returncode}")

    def test_unknown_and_missing_arguments_exit_2(self):
        for s in ("generate_resume.py", "validate_resume.py", "export_pdf.py", "match_jd.py", "install_skill.py"):
            self.assertEqual(run(s).returncode, 2, s)
            self.assertEqual(run(s, "--no-such-flag").returncode, 2, s)

    def test_inspect_environment_json_is_valid(self):
        p = run("inspect_environment.py", "--json")
        self.assertEqual(p.returncode, 0)
        data = json.loads(p.stdout)
        self.assertIn("capabilities", data)


# ---------------------------------------------------------------- category: "template layout broken for longer resumes"
class AllTemplatesLongResume(TempCase):
    def test_word_page_one_is_filled_for_every_template(self):
        if not envinfo.find_word()["available"] or not envinfo.find_pdftotext()["available"]:
            self.skipTest("blocked_by_environment: Word and/or pdftotext not available")
        from resume_design import templates
        d = en()
        d["experience"] = [{"organization": f"Fictional Corp {i}", "role": "Engineer", "start": f"{2024 - i}-01", "end": f"{2024 - i}-12",
                            "bullets": [f"Delivered milestone {j} for platform {i} with documented rollout" for j in range(6)]} for i in range(8)]
        for t in templates.list_templates():
            with self.subTest(t):
                src = self.write_json(f"{t}.json", d)
                p = self.gen(src, "--formats", "docx,pdf", "--template", t, "--pdf-backend", "word")
                self.assertEqual(p.returncode, 0, p.stderr)
                pages = subprocess.run(["pdftotext", "-enc", "UTF-8", str(self.tmp / f"out/{t}.pdf"), "-"], capture_output=True,
                                       encoding="utf-8", errors="replace").stdout.split("\f")
                # pdftotext folds right-aligned dates into one block, so count entries, not text lines
                on_page1 = [i for i in range(8) if f"Fictional Corp {i}" in pages[0]]
                self.assertGreaterEqual(len(on_page1), 3, f"{t}: only {on_page1} of the 8 jobs are on page 1")
                self.assertGreaterEqual(len(pages) - 1, 2, f"{t}: long resume should span several pages")


# ---------------------------------------------------------------- P1-8: Word timeout must not leave an orphan WINWORD
class WordTimeoutCleanup(TempCase):
    def test_hung_word_is_cleaned_up_after_timeout(self):
        if not WIN or not envinfo.find_word()["available"]:
            self.skipTest("blocked_by_environment: Microsoft Word not available")
        before = word_pids()

        def kill_new():                       # never leave test garbage behind, even when the assertion fails
            for pid in word_pids() - before:
                subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
        self.addCleanup(kill_new)
        run("generate_resume.py", "--input", self.write_json("ok.json", en()), "--output-dir", self.tmp, "--formats", "docx", "--prefix", "d")
        p = run("export_pdf.py", "--input", self.tmp / "d.docx", "--backend", "word", "--timeout", "15", "--output-dir", self.tmp / "o",
                env={pdfmod.HANG_ENV: "1"}, timeout=120)
        no_tb(self, p)
        self.assertEqual(p.returncode, 4, p.stdout + p.stderr)
        self.assertIn("timeout", p.stderr.lower())
        self.assertFalse(list((self.tmp / "o").glob("*.pdf")) if (self.tmp / "o").exists() else [])
        import time
        deadline = time.time() + 10
        while time.time() < deadline and word_pids() - before:
            time.sleep(0.5)
        self.assertEqual(word_pids() - before, set(), "export left an orphan WINWORD process behind after the timeout")

    def test_pre_existing_word_instance_is_never_killed(self):
        """The cleanup may only touch the process this export started."""
        if not WIN or not envinfo.find_word()["available"]:
            self.skipTest("blocked_by_environment: Microsoft Word not available")
        if word_pids():
            self.skipTest("a Word process is already running (possibly the user's); not testing against it")
        ps = ("$w = New-Object -ComObject Word.Application; $w.Visible = $false; $d = $w.Documents.Add(); "
              "$d.Content.Text = 'AUDIT-OWN-DOC'; Write-Output ('PID=' + (Get-Process WINWORD | Select-Object -First 1).Id); "
              "Start-Sleep -Seconds 40")
        holder = subprocess.Popen(["powershell", "-NoProfile", "-Command", ps], stdout=subprocess.PIPE, text=True)
        self.addCleanup(lambda: (holder.kill(), [subprocess.run(["taskkill", "/PID", str(x), "/F"], capture_output=True) for x in word_pids()]))
        line = holder.stdout.readline()
        self.assertTrue(line.startswith("PID="), line)
        mine = int(line.strip().split("=")[1])
        run("generate_resume.py", "--input", self.write_json("ok.json", en()), "--output-dir", self.tmp, "--formats", "docx", "--prefix", "d")
        p = run("export_pdf.py", "--input", self.tmp / "d.docx", "--backend", "word", "--timeout", "15", "--output-dir", self.tmp / "o",
                env={pdfmod.HANG_ENV: "1"}, timeout=120)
        self.assertEqual(p.returncode, 4, p.stderr)
        self.assertIn(mine, word_pids(), "the pre-existing Word instance must survive the cleanup")


if __name__ == "__main__":
    unittest.main()
