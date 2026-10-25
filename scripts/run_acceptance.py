#!/usr/bin/env python3
"""Run the full test suite + ten task scenarios and write reports/acceptance-report.md and skill-scenarios.md."""
import argparse
import datetime as dt
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from resume_design import __version__, envinfo  # noqa: E402
from resume_design.common import setup_console  # noqa: E402


class Collect(unittest.TextTestResult):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.rows = []

    def _add(self, test, outcome, detail=""):
        self.rows.append({"test": test.id().replace("test_", "", 1) if False else test.id(), "outcome": outcome, "detail": detail})

    def addSuccess(self, test):
        super().addSuccess(test)
        self._add(test, "passed")

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._add(test, "failed", self._exc_info_to_string(err, test)[-600:])

    def addError(self, test, err):
        super().addError(test, err)
        self._add(test, "error", self._exc_info_to_string(err, test)[-600:])

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._add(test, "blocked_by_environment" if reason.startswith("blocked_by_environment") else "skipped", reason)


def build_parser():
    p = argparse.ArgumentParser(prog="run_acceptance.py", description="Run all tests and scenarios and write the acceptance reports (reports/).")
    p.add_argument("--output-dir", default=str(ROOT / "reports"), help="where to write reports (default: reports/)")
    p.add_argument("--force", action="store_true", help="overwrite existing report files")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def unique(path: Path, force: bool) -> Path:
    if force or not path.exists():
        return path
    i = 1
    while path.with_name(f"{path.stem}-{i}{path.suffix}").exists():
        i += 1
    return path.with_name(f"{path.stem}-{i}{path.suffix}")


def pdf_demo() -> list[dict]:
    """Real PDF exports of the fictional sample with every template (only if a backend exists)."""
    from helpers import run
    from resume_design import templates
    rows = []
    with tempfile.TemporaryDirectory(prefix="rd-acc-") as td:
        for t in templates.list_templates():
            p = run("generate_resume.py", "--input", ROOT / "examples" / "sample_resume.md", "--output-dir", td,
                    "--formats", "docx,pdf", "--template", t, "--prefix", t)
            rep = json.loads((Path(td) / f"{t}.report.json").read_text(encoding="utf-8"))
            pdf = rep.get("artifacts", {}).get("pdf", {})
            v = pdf.get("verification", {})
            rows.append({"template": t, "exit": p.returncode, "pdf_status": rep["pdf_status"], "backend": pdf.get("backend"),
                         "pages": v.get("pages"), "size": v.get("size_bytes"), "text_check": v.get("text_check"),
                         "cjk": f"{v.get('cjk_expected', 0) - v.get('cjk_missing', 0)}/{v.get('cjk_expected', 0)}" if v else "-",
                         "fonts": ", ".join(sorted({f["name"].split("+")[-1] for f in v.get("fonts", [])})) or "-",
                         "embedded": v.get("fonts_all_embedded")})
    return rows


def main(argv=None) -> int:
    setup_console()
    args = build_parser().parse_args(argv)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    start = time.time()
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT / "tests"))
    runner = unittest.TextTestRunner(resultclass=Collect, verbosity=1, stream=sys.stderr)
    res = runner.run(suite)
    dur = time.time() - start
    rows = res.rows
    count = lambda k: sum(1 for r in rows if r["outcome"] == k)
    env = envinfo.environment_report()
    demo = pdf_demo() if env["capabilities"]["pdf"] else []

    import test_scenarios
    sc = sorted(test_scenarios.SCENARIOS, key=lambda s: s["id"])
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")

    L = [f"# 验收报告 / Acceptance report — resume-design {__version__}", "",
         f"生成时间：{now}；环境：{env['os']} [{env['arch']}]，Python {env['python']['version']}。**全部使用虚构数据。**", "",
         "## 1. 测试结果", "", "运行命令：`python scripts/run_acceptance.py`（内部执行 `unittest discover -s tests`；本机未安装 pytest，未运行 pytest）。", "",
         f"| 总数 | 通过 | 失败 | 错误 | 环境阻断(blocked_by_environment) | 其它跳过 | 耗时 |", "|---|---|---|---|---|---|---|",
         f"| {len(rows)} | {count('passed')} | {count('failed')} | {count('error')} | {count('blocked_by_environment')} | {count('skipped')} | {dur:.0f}s |", ""]
    blocked = [r for r in rows if r["outcome"] in ("blocked_by_environment", "skipped")]
    bad = [r for r in rows if r["outcome"] in ("failed", "error")]
    if bad:
        L += ["### 失败项", ""] + [f"- `{r['test']}`: {r['detail'][-300:]!r}" for r in bad] + [""]
    if blocked:
        L += ["### 环境阻断/跳过的测试（**不计为通过**）", ""] + [f"- `{r['test']}` — {r['detail']}" for r in blocked] + [""]
    L += ["## 2. 环境与 PDF 后端检测", "", "| 后端 | 可用 | 路径 | 版本/备注 |", "|---|---|---|---|"]
    for b in env["pdf_backends"]:
        L.append(f"| {b['name']} | {'是' if b['available'] else '否'} | {Path(b['path']).name if b.get('path') else '-'} | {b.get('version') or b.get('note') or '-'} |")
    t = env["pdf_text_tools"]
    L += ["", f"- pdftotext：{Path(t['pdftotext']['path']).name if t['pdftotext']['path'] else '无'}（{t['pdftotext'].get('version') or '-'}）；pdffonts：{Path(t['pdffonts']['path']).name if t['pdffonts']['path'] else '无'}（字体检查改用内置 PDF 扫描器）",
          f"- 可选 Python 包：{env['python_modules']}",
          f"- 中文字体：{env['fonts']['cjk_fonts']}", ""]
    L += ["## 3. 实际 PDF 导出结果", ""]
    if demo:
        L += ["对虚构示例 `examples/sample_resume.md` 用 5 个模板分别导出并核验：", "",
              "| 模板 | 退出码 | PDF 状态 | 后端 | 页数 | 字节 | 文本可提取 | 中文字符保留 | 字体(嵌入全部=%s) |" % "是/否", "|---|---|---|---|---|---|---|---|---|"]
        for d in demo:
            L.append(f"| {d['template']} | {d['exit']} | {d['pdf_status']} | {d['backend']} | {d['pages']} | {d['size']} | {d['text_check']} | {d['cjk']} | {d['fonts']} ({'全部嵌入' if d['embedded'] else '未全部嵌入/未知'}) |")
        lo = [b for b in env["pdf_backends"] if b["name"] == "libreoffice"][0]
        if not lo["available"]:
            L += ["", "LibreOffice 路径：**blocked_by_environment**（本机未安装；代码路径已实现，仅用失败桩程序验证了错误处理，**未做真实 LibreOffice 导出**）。"]
    else:
        L += ["本机没有可用 PDF 后端：PDF 功能状态 **blocked_by_environment**；仅验证了失败路径（退出码 4 + 报告）。"]
    L += ["", "## 4. 平台兼容矩阵（摘自 core/platform-capabilities.md）", "",
          "| 平台 | 状态 |", "|---|---|",
          "| 引擎（Markdown/DOCX） | 已实际测试（Windows 11 / Python 3.12） |",
          "| PDF — Microsoft Word COM | " + ("已实际测试" if demo and any(d['backend'] == 'word' for d in demo) else "未能在本机测试") + " |",
          "| PDF — LibreOffice | blocked_by_environment（未安装） |" if not [b for b in env["pdf_backends"] if b["name"] == "libreoffice" and b["available"]] else "| PDF — LibreOffice | 见测试结果 |",
          "| Claude Code | 依据官方规范实现；静态检查通过；**未在 Claude Code 内实际调用** |",
          "| OpenAI Codex | 依据官方规范实现；静态检查通过；**本机无 Codex CLI，未实际调用** |",
          "| DeepSeek / 豆包 / 其他 | 人工流程，**未实测** |", "",
          "## 5. 未完成项与环境阻断", "",
          "- 平台内实测（Claude Code / Codex / DeepSeek / 豆包）：未做，需要用户在对应平台运行。",
          "- LibreOffice 真实导出：本机未安装。", "- macOS/Linux：未测试。", "- 分页、其他 Word 版本差异、目标 ATS 解析：无法离线验证（报告 C 类）。",
          "- 十个任务场景中的**模型对话行为**（提问、措辞、口头拒绝）未测试，仅测试了工具链；见 skill-scenarios.md。",
          "- 未执行与 Skill Creator 的基线对比（本机/本环境未使用该工具）。", "",
          "## 6. 安装、调用与升级", "", "见 docs/USAGE.md 第 7–9、17、23 节。安装预览：`python scripts/install_skill.py --target claude-code-user --dry-run`。", ""]
    rp = unique(out / "acceptance-report.md", args.force)
    rp.write_text("\n".join(L), encoding="utf-8")

    S = ["# 任务场景测试记录 / Skill scenarios", "",
         "范围说明：本文件记录 10 个任务场景对**工具链**（真实 CLI）的验证。涉及模型对话的部分（提问、改写、口头拒绝）需要真实模型，**未测试**。",
         "未做 with/without Skill 的基线比较（无法在此环境对模型运行评测）。", "",
         f"通过 {sum(s['passed'] for s in sc)}/{len(sc)}", ""]
    for s in sc:
        S += [f"## {s['id']} {s['title']} — {'✅ 通过' if s['passed'] else '❌ 未通过'}", "",
              f"- 输入：{s['input']}", f"- 预期：{s['expected']}", f"- 实际：{s['actual']}", f"- 范围备注：{s['note']}", ""]
    sp = unique(out / "skill-scenarios.md", args.force)
    sp.write_text("\n".join(S), encoding="utf-8")
    print(f"tests: total={len(rows)} passed={count('passed')} failed={count('failed')} error={count('error')} "
          f"blocked_by_environment={count('blocked_by_environment')} skipped={count('skipped')}")
    print(f"scenarios: {sum(s['passed'] for s in sc)}/{len(sc)} passed")
    print(f"reports: {rp}\n         {sp}")
    return 0 if not bad and all(s["passed"] for s in sc) and len(sc) == 10 else 5


if __name__ == "__main__":
    sys.exit(main())
