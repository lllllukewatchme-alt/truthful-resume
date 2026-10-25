"""PDF export (Word COM / LibreOffice) and verification. Never installs software."""
from __future__ import annotations

import locale
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
import zlib
from pathlib import Path

from . import envinfo
from .common import EXIT_DEPENDENCY, EXIT_GENERATION, ToolError, commit_file

CJK = re.compile(r"[一-鿿]")
BACKENDS = ["word", "libreoffice"]
HANG_ENV = "RESUME_DESIGN_TEST_WORD_HANG"   # test hook: make the Word backend hang after opening the document
WORD_PS = r"""
$ErrorActionPreference = 'Stop'
$word = $null; $doc = $null
try {
  $before = @(Get-Process WINWORD -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
  $word = New-Object -ComObject Word.Application
  # record the Word process THIS script started, so the caller can clean it up if we are killed on timeout
  $mine = @(Get-Process WINWORD -ErrorAction SilentlyContinue | Where-Object { $before -notcontains $_.Id } | ForEach-Object { $_.Id })
  if ($env:RD_PIDFILE) { Set-Content -LiteralPath $env:RD_PIDFILE -Value ($mine -join ',') -Encoding ascii }
  $word.Visible = $false
  $word.DisplayAlerts = 0
  $doc = $word.Documents.Open($env:RD_IN, $false, $true)
  if ($env:RD_HANG) { Start-Sleep -Seconds 300 }   # test hook: simulate a hung Word
  $doc.ExportAsFixedFormat($env:RD_OUT, 17)
} finally {
  if ($doc -ne $null) { $doc.Close(0) }
  if ($word -ne $null) { $word.Quit() }
}
"""


# ------------------------------------------------------------------ backends
def _tasklist(*flt) -> list[list[str]]:
    r = subprocess.run(["tasklist", *flt, "/FO", "CSV", "/NH"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    rows = []
    for line in r.stdout.splitlines():
        cells = [c.strip('"') for c in line.split('","')]
        if len(cells) >= 2 and cells[1].isdigit():
            rows.append(cells)
    return rows


def _word_pids() -> set[int]:
    if sys.platform != "win32":
        return set()
    return {int(c[1]) for c in _tasklist("/FI", "IMAGENAME eq WINWORD.EXE") if c[0].upper() == "WINWORD.EXE"}


def _kill_tree(pid: int, proc=None) -> None:
    """Kill a process and its children (a plain kill would leave grandchildren such as soffice.bin running)."""
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    elif proc is not None:
        proc.kill()


def _run_killing_tree(cmd, timeout, env=None) -> subprocess.CompletedProcess:
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
                            encoding=locale.getpreferredencoding(False), errors="replace")
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(proc.pid, proc)
        proc.communicate()
        raise
    return subprocess.CompletedProcess(cmd, proc.returncode, out, err)


def _cleanup_word_after_timeout(pidfile: Path, before: set[int]) -> None:
    """Close only the Word process this export started: the PID the script recorded, or (if it was killed before
    recording one) a new, windowless Word that was not running before. Anything else - e.g. the user's own Word - is left alone."""
    mine: set[int] = set()
    try:
        mine = {int(x) for x in pidfile.read_text(encoding="ascii").split(",") if x.strip().isdigit()}
    except OSError:
        pass
    if not mine:  # fallback: give a half-started Word a moment to appear, then take only new windowless instances
        time.sleep(2)
        for pid in _word_pids() - before:
            rows = _tasklist("/V", "/FI", f"PID eq {pid}")
            if rows and rows[0][-1].strip().upper() in ("N/A", ""):   # no window title = started by automation
                mine.add(pid)
    for pid in mine:
        if pid in _word_pids() and pid not in before:
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)


def _export_word(docx: Path, out_pdf: Path, info: dict, timeout: int) -> None:
    fd, pidfile_name = tempfile.mkstemp(prefix="rd-wordpid-", suffix=".txt")
    os.close(fd)
    pidfile = Path(pidfile_name)
    env = {**os.environ, "RD_IN": str(docx), "RD_OUT": str(out_pdf), "RD_PIDFILE": str(pidfile)}
    if os.environ.get(HANG_ENV):
        env["RD_HANG"] = "1"
    before = _word_pids()
    try:
        r = _run_killing_tree(["powershell", "-NoProfile", "-NonInteractive", "-Command", WORD_PS], timeout, env)
    except subprocess.TimeoutExpired:
        _cleanup_word_after_timeout(pidfile, before)
        raise
    finally:
        pidfile.unlink(missing_ok=True)
    if r.returncode != 0:
        raise RuntimeError("Word COM export failed: " + _short(r.stderr or r.stdout))


def _export_soffice(docx: Path, out_pdf: Path, info: dict, timeout: int) -> None:
    with tempfile.TemporaryDirectory(prefix="rd-lo-") as td:
        profile = Path(td, "profile").resolve().as_uri()
        outdir = Path(td, "out")
        outdir.mkdir()
        r = _run_killing_tree([info["path"], f"-env:UserInstallation={profile}", "--headless", "--convert-to", "pdf",
                               "--outdir", str(outdir), str(docx)], timeout)
        produced = outdir / (docx.stem + ".pdf")
        if r.returncode != 0 or not produced.is_file():
            raise RuntimeError("LibreOffice conversion failed: " + _short(r.stderr or r.stdout))
        shutil.copyfile(produced, out_pdf)


def _short(s: str, n: int = 300) -> str:
    s = " ".join((s or "").split())
    return s[:n] + ("..." if len(s) > n else "")


def alternatives(docx: Path, reason: str) -> list[str]:
    return [
        f'Open "{docx.name}" in Microsoft Word / WPS and use File > Save As > PDF (manual).',
        "Install LibreOffice yourself (e.g. winget install TheDocumentFoundation.LibreOffice), then rerun: "
        f'python scripts/export_pdf.py --input "{docx.name}" --backend libreoffice',
        "Use the DOCX/Markdown deliverables only; PDF is not produced by this tool without a backend.",
    ]


# ------------------------------------------------------------------ verification
def _objects(data: bytes):
    """Yield raw text chunks: plain objects plus inflated streams (covers object streams)."""
    yield data.decode("latin-1")
    for m in re.finditer(rb"stream\r?\n", data):
        start = m.end()
        end = data.find(b"endstream", start)
        if end < 0:
            continue
        try:
            yield zlib.decompress(data[start:end].strip(b"\r\n")).decode("latin-1")
        except (zlib.error, ValueError):
            continue


def scan_pdf(data: bytes) -> dict:
    pages, fonts = 0, {}
    for chunk in _objects(data):
        pages += len(re.findall(r"/Type\s*/Page(?![s\w])", chunk))
        for m in re.finditer(r"<<([^<>]*?/Type\s*/FontDescriptor[^<>]*?)>>", chunk):
            body = m.group(1)
            nm = re.search(r"/FontName\s*/([^\s/\[\]<>()]+)", body)
            if not nm:
                continue
            name = nm.group(1)
            fonts[name] = {"name": name, "embedded": bool(re.search(r"/FontFile[23]?\b", body)),
                           "subset": bool(re.match(r"[A-Z]{6}\+", name))}
    return {"pages": pages, "fonts": sorted(fonts.values(), key=lambda f: f["name"])}


def extract_text(pdf: Path) -> tuple[str | None, str]:
    """Return (text or None, tool used)."""
    tool = envinfo.find_pdftotext()
    if tool["available"]:
        r = subprocess.run([tool["path"], "-enc", "UTF-8", str(pdf), "-"], capture_output=True, timeout=60)
        if r.returncode == 0:
            return r.stdout.decode("utf-8", "replace"), "pdftotext"
    try:
        import pypdf  # optional
        rd = pypdf.PdfReader(str(pdf))
        return "\n".join(p.extract_text() or "" for p in rd.pages), "pypdf"
    except Exception:
        pass
    return None, "none"


def verify_pdf(pdf: Path, expected_text: str | None = None, page_limit: int | None = None) -> dict:
    res = {"path_name": pdf.name, "status": "failed", "errors": [], "warnings": []}
    if not pdf.is_file():
        res["errors"].append("PDF file does not exist")
        return res
    data = pdf.read_bytes()
    res["size_bytes"] = len(data)
    if len(data) < 500:
        res["errors"].append("PDF is empty or implausibly small")
    if not data.startswith(b"%PDF-"):
        res["errors"].append("missing %PDF- header")
    if b"%%EOF" not in data[-2048:]:
        res["errors"].append("missing %%EOF trailer")
    scan = scan_pdf(data)
    res["pages"] = scan["pages"]
    res["fonts"] = scan["fonts"]
    if scan["pages"] < 1:
        res["errors"].append("no pages found in PDF structure")
    if scan["fonts"]:
        res["fonts_all_embedded"] = all(f["embedded"] for f in scan["fonts"])
        if not res["fonts_all_embedded"]:
            res["warnings"].append("some fonts are not embedded: "
                                   + ", ".join(f["name"] for f in scan["fonts"] if not f["embedded"]))
    else:
        res["fonts_all_embedded"] = None
        res["warnings"].append("font information could not be read from PDF")
    if page_limit and scan["pages"] > page_limit:
        res["warnings"].append(f"page count {scan['pages']} exceeds page_limit {page_limit}")
        res["page_limit_exceeded"] = True
    text, tool = extract_text(pdf)
    res["text_tool"] = tool
    if text is None:
        res["text_check"] = "blocked_by_environment"
        res["warnings"].append("no PDF text extraction tool (pdftotext/pypdf) available; text not verified")
    else:
        res["text_check"] = "passed" if text.strip() else "failed"
        res["text_chars"] = len(text)
        if not text.strip():
            res["errors"].append("no extractable text in PDF")
        if expected_text:
            want = set(CJK.findall(expected_text))
            if want:
                have = set(CJK.findall(text))
                lost = want - have
                res["cjk_expected"], res["cjk_missing"] = len(want), len(lost)
                if len(lost) / len(want) > 0.02:
                    res["errors"].append(f"{len(lost)}/{len(want)} CJK characters missing from PDF text")
                    res["text_check"] = "failed"
            ascii_words = set(re.findall(r"[A-Za-z]{4,}", expected_text))
            if ascii_words:
                have_w = set(re.findall(r"[A-Za-z]{4,}", text))
                miss = len(ascii_words - have_w) / len(ascii_words)
                if miss > 0.10:
                    res["errors"].append(f"{miss:.0%} of Latin words missing from PDF text")
                    res["text_check"] = "failed"
    res["status"] = "failed" if res["errors"] else "passed"
    return res


# ------------------------------------------------------------------ orchestration
def choose_backends(explicit: str | None) -> list[dict]:
    allb = {b["name"]: b for b in envinfo.pdf_backends()}
    if explicit:
        if explicit not in allb:
            raise ToolError(f"unknown backend '{explicit}' (choose from {', '.join(BACKENDS)})", 2)
        return [allb[explicit]]
    return [allb[n] for n in BACKENDS]


def export_pdf(docx: Path, dest: Path, *, backend: str | None = None, force: bool = False,
               expected_text: str | None = None, page_limit: int | None = None, timeout: int = 180) -> dict:
    """Export + verify. Returns result dict; raises ToolError(code 3/4) when no PDF produced."""
    docx, dest = Path(docx).resolve(), Path(dest).resolve()  # backends run with another cwd
    candidates = choose_backends(backend)
    attempts = []
    detected = [{k: b.get(k) for k in ("name", "available", "path", "version", "note")} for b in envinfo.pdf_backends()]
    for b in candidates:
        if not b["available"]:
            attempts.append({"backend": b["name"], "result": "unavailable", "detail": b.get("note", "")})
            continue
        tmp = dest.parent / f".rd-{uuid.uuid4().hex[:10]}.pdf"
        try:
            (_export_word if b["name"] == "word" else _export_soffice)(docx, tmp, b, timeout)
            ver = verify_pdf(tmp, expected_text, page_limit)
            if ver["status"] != "passed":
                attempts.append({"backend": b["name"], "result": "verification_failed", "detail": "; ".join(ver["errors"])})
                tmp.unlink(missing_ok=True)
                continue
            final = commit_file(tmp, dest, force)
            ver["path_name"] = final.name
            attempts.append({"backend": b["name"], "result": "ok"})
            return {"status": "passed", "backend": b["name"], "output": str(final), "verification": ver,
                    "attempts": attempts, "detected_backends": detected}
        except ToolError:
            tmp.unlink(missing_ok=True)
            raise
        except subprocess.TimeoutExpired:
            attempts.append({"backend": b["name"], "result": "timeout", "detail": f"no result within {timeout}s"})
        except (RuntimeError, OSError) as e:
            attempts.append({"backend": b["name"], "result": "error", "detail": _short(str(e))})
        finally:
            tmp.unlink(missing_ok=True)
    any_available = any(b["available"] for b in candidates)
    code = EXIT_GENERATION if any_available else EXIT_GENERATION
    status = "failed" if any_available else "blocked_by_environment"
    err = ToolError("PDF export failed: " + ("; ".join(f"{a['backend']}: {a['result']}" for a in attempts)), code)
    err.result = {"status": status, "attempts": attempts, "detected_backends": detected,
                  "alternatives": alternatives(docx, status)}
    raise err
