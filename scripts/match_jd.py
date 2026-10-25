#!/usr/bin/env python3
"""Compare a resume with a job description: requirement extraction and keyword coverage. Read-only."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from resume_design.common import setup_console  # noqa: E402
from resume_design import __version__, jd  # noqa: E402
from resume_design.common import (EXIT_INPUT, EXIT_OK, ToolError, read_text_file, redact, refuse_if_protected,
                                  report_unexpected, write_json_report)  # noqa: E402
from resume_design.pipeline import load_resume  # noqa: E402

ICON = {"satisfied": "[x]", "partial": "[~]", "missing_evidence": "[ ]", "needs_human": "[?]"}


def build_parser():
    p = argparse.ArgumentParser(
        prog="match_jd.py",
        description="Extract requirements from a job description (.md/.txt) and classify each as satisfied / partial / "
                    "missing_evidence / needs_human against the resume text. Heuristic and offline; never edits the resume.",
        epilog="Exit codes: 0 ok, 2 input/arg error.")
    p.add_argument("--input", required=True, help="resume source (.md or .json)")
    p.add_argument("--jd", required=True, help="job description file (.md or .txt)")
    p.add_argument("--report", default="", help="write the JSON result to this path")
    p.add_argument("--force", action="store_true", help="overwrite --report if it exists")
    p.add_argument("--json", action="store_true", help="print JSON")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv=None) -> int:
    setup_console()
    args = build_parser().parse_args(argv)
    try:
        data, _, _ = load_resume(Path(args.input))
        jd_path = Path(args.jd)
        if not jd_path.is_file():
            raise ToolError("job description file not found", EXIT_INPUT)
        res = jd.match(data, read_text_file(jd_path))
        if args.report:
            refuse_if_protected(Path(args.report), [Path(args.input), jd_path], "report")
            write_json_report(Path(args.report), res, args.force)
        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            c = res["counts"]
            print(f"JD: {res['title'] or jd_path.name}  keyword coverage: {res['keyword_coverage']}")
            print(f"satisfied={c['satisfied']} partial={c['partial']} missing_evidence={c['missing_evidence']} needs_human={c['needs_human']}")
            for r in res["results"]:
                tag = " (preferred)" if r["preferred"] else ""
                print(f"{ICON[r['status']]} {r['requirement']}{tag}")
                if r["unmatched_keywords"]:
                    print(f"      no evidence for: {', '.join(r['unmatched_keywords'])}")
            print(res["note"])
        return EXIT_OK
    except ToolError as e:
        print(f"error: {redact(str(e))}", file=sys.stderr)
        return e.code
    except Exception as e:  # last-resort: no traceback, documented exit code
        return report_unexpected(e)


if __name__ == "__main__":
    sys.exit(main())
