#!/usr/bin/env python3
"""Validate a resume (.md/.json) and optionally a generated .docx/.pdf. Read-only."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from resume_design.common import setup_console  # noqa: E402
from resume_design import __version__  # noqa: E402
from resume_design import pdf as pdfmod  # noqa: E402
from resume_design import validate as V  # noqa: E402
from resume_design.common import (EXIT_INPUT, EXIT_OK, EXIT_VALIDATION, ToolError, redact, refuse_if_protected,
                                  report_unexpected, sha256_file,  # noqa: E402
                                  write_json_report)
from resume_design.docx_writer import inspect_docx  # noqa: E402
from resume_design.model import normalize, visible_text  # noqa: E402
from resume_design.pipeline import load_resume, missing_fonts, resolve_context  # noqa: E402


def build_parser():
    p = argparse.ArgumentParser(
        prog="validate_resume.py",
        description="Validate resume structure, placeholders ({{MISSING:field}}), dates, duplicates and generated "
                    "DOCX/PDF files. Never modifies any input. Output is a three-tier report: A automated, "
                    "B needs human confirmation, C not verifiable here.",
        epilog="Exit codes: 0 ok, 2 input/arg error, 3 dependency missing, 4 failure, 5 validation failed.")
    p.add_argument("--input", required=True, help="resume source (.md/.json) or a generated .docx")
    p.add_argument("--docx", default="", help="also validate this generated .docx against the input data")
    p.add_argument("--pdf", default="", help="also verify this generated .pdf (header, pages, text, fonts)")
    p.add_argument("--compare", default="", help="second resume (.md/.json) to check cross-version consistency")
    p.add_argument("--lang", default="", help="expected resume language (zh/en)")
    p.add_argument("--locale", default="", help="target locale (zh-CN, en-US, ...)")
    p.add_argument("--confirm-ready", action="store_true",
                   help="HUMAN attestation: you checked facts, contact and target; allows status ready_to_submit "
                        "(also needs meta.review.* in the data). Assistants must not pass this on their own.")
    p.add_argument("--strict", action="store_true", help="treat warnings (incl. placeholders) as failures (exit 5)")
    p.add_argument("--report", default="", help="write JSON report to this path (never overwritten without --force)")
    p.add_argument("--force", action="store_true", help="overwrite the --report file if it exists")
    p.add_argument("--json", action="store_true", help="print the report as JSON instead of text")
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
    src = Path(args.input)
    if args.report:
        refuse_if_protected(Path(args.report), [src, *(Path(p) for p in (args.docx, args.pdf, args.compare) if p)], "report")
    sha = sha256_file(src) if src.is_file() else None
    data, findings, ats_safe, miss, fdet = None, [], True, [], True
    docx_target = Path(args.docx) if args.docx else None
    if src.suffix.lower() == ".docx":
        docx_target, data_for_docx = src, None
    else:
        data, kind, sha = load_resume(src)
        ctx = resolve_context(data, lang=args.lang, locale=args.locale)
        findings += V.check_data(data, lang=ctx["lang"], locale_rules=ctx["rules"])
        ats_safe = ctx["style"].get("ats", {}).get("safe", True)
        miss, fdet = missing_fonts(ctx["style"])
        data_for_docx = ctx["data"]
    if docx_target:
        if not docx_target.is_file():
            raise ToolError(f"docx not found: {docx_target.name}", EXIT_INPUT)
        try:
            info = inspect_docx(docx_target)
        except Exception as e:
            findings.append(V._f("docx.invalid", "error", "A", f"not a valid DOCX package: {e}"))
        else:
            findings += V.check_docx(info, data_for_docx)
    pdf_status = "not_tested"
    pdf_info = None
    if args.pdf:
        pdf_info = pdfmod.verify_pdf(Path(args.pdf), visible_text(normalize(data)) if data else None,
                                     (normalize(data)["preferences"].get("page_limit") if data else None))
        pdf_status = pdf_info["status"]
        for e in pdf_info["errors"]:
            findings.append(V._f("pdf.verify", "error", "A", e))
        if pdf_info.get("page_limit_exceeded") and data:
            findings.append(V._f("pdf.page_limit", "warning", "A",
                                 f"PDF has {pdf_info['pages']} pages; page_limit is {normalize(data)['preferences'].get('page_limit')}"))
    if args.compare:
        other, _, _ = load_resume(Path(args.compare))
        findings += V.compare_versions(data or {}, other)
    rep = V.build_report(findings, data, input_name=src.name, input_sha=sha, pdf_status=pdf_status,
                         pdf_required=bool(args.pdf), ats_safe=ats_safe, missing_fonts=miss, fonts_detectable=fdet,
                         extra={"pdf": pdf_info} if pdf_info else None, confirm_ready=args.confirm_ready)
    if data is None:
        rep["status"], rep["status_reasons"] = "draft", ["artifact-only validation: status needs the source resume"]
    if args.report:
        rp = write_json_report(Path(args.report), rep, args.force)
        print(f"report: {rp}", file=sys.stderr)
    print(json.dumps(rep, ensure_ascii=False, indent=2) if args.json else V.format_report_text(rep))
    c = rep["A_automated"]["counts"]
    if c["error"] or (args.strict and (c["warning"] or rep["status"] == "needs_review")):
        return EXIT_VALIDATION
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
