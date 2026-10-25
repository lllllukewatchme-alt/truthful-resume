"""Shared test helpers. All data is fictional; all files live in temp directories."""
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(ROOT))

from resume_design import envinfo  # noqa: E402

NO_BACKENDS = {envinfo.DISABLE_ENV: "word,libreoffice"}

FICTION_ZH = {
    "basics": {"name": "测试用户", "email": "tester@example.com", "phone": "139-1111-2222",
               "location": "北京", "summary": "五年后端开发经验，熟悉分布式系统。"},
    "target": {"role": "后端开发工程师", "locale": "zh-CN", "language": "zh"},
    "experience": [{"organization": "虚构科技有限公司", "role": "后端工程师", "start": "2020-03", "end": "present",
                    "bullets": ["负责订单服务的设计与迭代", "将接口响应时间降低到 120ms"],
                    "evidence": ["用户陈述：性能报告"], "confirmation_status": "user_confirmed"}],
    "education": [{"organization": "虚构大学", "role": "计算机科学 本科", "start": "2015-09", "end": "2019-06"}],
    "skills": [{"category": "语言", "items": ["Java", "Go", "Python"]}],
}
FICTION_EN = {
    "basics": {"name": "Alex Test", "email": "alex@example.com", "phone": "+1 555 010 0000", "location": "Austin, TX",
               "summary": "Backend engineer with five years of experience."},
    "target": {"role": "Backend Engineer", "locale": "en-US", "language": "en"},
    "experience": [{"organization": "Fictional Tech Inc.", "role": "Backend Engineer", "start": "2020-03", "end": "present",
                    "bullets": ["Designed and iterated the order service", "Reduced API latency to 120ms"],
                    "confirmation_status": "user_confirmed"}],
    "education": [{"organization": "Fictional University", "role": "B.S. Computer Science", "start": "2015-09", "end": "2019-06"}],
    "skills": [{"category": "Languages", "items": ["Java", "Go", "Python"]}],
}


def zh():
    return copy.deepcopy(FICTION_ZH)


def en():
    return copy.deepcopy(FICTION_EN)


def sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(script, *args, env=None, cwd=None, timeout=300):
    e = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    e.update(env or {})
    p = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)], capture_output=True,
                       encoding="utf-8", errors="replace", env=e, cwd=cwd, timeout=timeout)
    return p


def docx_xml(path, part="word/document.xml") -> str:
    with zipfile.ZipFile(path) as z:
        return z.read(part).decode("utf-8")


def make_min_pdf(text="Hello Resume Toolkit") -> bytes:
    """A tiny but valid single-page PDF with extractable Latin text and no embedded font."""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>",
            "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
            "/Resources << /Font << /F1 5 0 R >> >> >>"]
    stream = f"BT /F1 18 Tf 72 700 Td ({text}) Tj ET"
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


class TempCase(unittest.TestCase):
    """TestCase with a per-test temporary directory (cleaned up automatically)."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory(prefix="rd-test-")
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)

    def write_json(self, name, data) -> Path:
        p = self.tmp / name
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return p

    def gen(self, input_path, *extra, env=None, out="out"):
        return run("generate_resume.py", "--input", input_path, "--output-dir", self.tmp / out, *extra, env=env)


def requires_backend(name: str):
    """Environment-matrix gate: records an explicit 'blocked_by_environment' skip, never a silent pass."""
    info = envinfo.find_word() if name == "word" else envinfo.find_libreoffice()
    return unittest.skipUnless(info["available"], f"blocked_by_environment: {name} not available")
