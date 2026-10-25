#!/usr/bin/env python3
"""Inspect the local environment for resume-design capabilities. Read-only; installs nothing."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from resume_design.common import setup_console  # noqa: E402
from resume_design import __version__, envinfo  # noqa: E402
from resume_design.common import (EXIT_DEPENDENCY, EXIT_OK, ToolError, redact, report_unexpected,  # noqa: E402
                                  write_json_report)


def build_parser():
    p = argparse.ArgumentParser(
        prog="inspect_environment.py",
        description="Report Python, optional packages, PDF backends (Word/LibreOffice), PDF text tools and CJK fonts. "
                    "Prints venv install commands for missing optional dependencies; never installs globally.",
        epilog="Exit codes: 0 DOCX/Markdown generation possible, 3 required runtime missing.")
    p.add_argument("--json", action="store_true", help="print JSON")
    p.add_argument("--report", default="", help="also write the JSON report to this path")
    p.add_argument("--force", action="store_true", help="overwrite --report if it exists")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv=None) -> int:
    setup_console()
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except ToolError as e:
        print(f"error: {redact(str(e))}", file=sys.stderr)
        return e.code
    except Exception as e:  # last-resort: no traceback, documented exit code
        return report_unexpected(e)


def run(args) -> int:
    if sys.version_info < (3, 9):
        print("error: Python 3.9+ required", file=sys.stderr)
        return EXIT_DEPENDENCY
    rep = envinfo.environment_report()
    if args.report:
        write_json_report(Path(args.report), rep, args.force)
    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
        return EXIT_OK
    py = rep["python"]
    print(f"OS: {rep['os']} [{rep['arch']}]\nPython: {py['version']} ({py['executable']})")
    print("Optional Python packages:", ", ".join(f"{k}={'yes' if v else 'no'}" for k, v in rep["python_modules"].items()))
    for b in rep["pdf_backends"]:
        print(f"PDF backend {b['name']}: " + (f"available ({b['path']}, version {b['version']})" if b["available"]
                                              else f"not available - {b['note']}"))
    t = rep["pdf_text_tools"]
    print(f"pdftotext: {t['pdftotext']['path'] or 'not found'}; pdffonts: {t['pdffonts']['path'] or 'not found'}")
    print(f"CJK fonts: {rep['fonts']['cjk_fonts'] if rep['fonts']['detectable'] else 'could not detect'}")
    cap = rep["capabilities"]
    print(f"Capabilities: markdown={cap['markdown']} docx={cap['docx']} pdf={cap['pdf']} "
          f"({', '.join(cap['pdf_backends_usable']) or 'no backend'}) pdf_text_check={cap['pdf_text_check']}")
    missing = [k for k, v in rep["python_modules"].items() if not v and k in ("docx", "pypdf")]
    if missing:
        print("\nOptional extras are not required. To add them inside a virtual environment (not global):")
        print("  python -m venv .venv && .venv\\Scripts\\activate && pip install -e .[extras]   # Windows")
    if not cap["pdf"]:
        print("\nNo PDF backend: PDF export exits with code 4 and a failure report. Install Word or LibreOffice "
              "yourself (this tool never installs software).")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
