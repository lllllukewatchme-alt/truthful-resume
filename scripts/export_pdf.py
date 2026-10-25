#!/usr/bin/env python3
"""Export a .docx to a verified PDF using Microsoft Word (Windows) or LibreOffice. Never installs anything."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from resume_design.common import setup_console  # noqa: E402
from resume_design import __version__  # noqa: E402
from resume_design import envinfo  # noqa: E402
from resume_design import pdf as pdfmod  # noqa: E402
from resume_design.common import (EXIT_INPUT, EXIT_OK, ToolError, check_prefix,  # noqa: E402
                                  ensure_parent_dir, pick_free_prefix, prepare_output_dir, redact, refuse_if_protected,
                                  report_unexpected,
                                  write_json_report)
from resume_design.docx_writer import inspect_docx  # noqa: E402


def positive_int(text):
    try:
        n = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a whole number")
    if n < 1:
        raise argparse.ArgumentTypeError("must be at least 1 second")
    return n


def build_parser():
    p = argparse.ArgumentParser(
        prog="export_pdf.py",
        description="Convert a .docx resume to PDF (backend order: --backend if given, else Microsoft Word, "
                    "then LibreOffice). Verifies the PDF (header/trailer, pages, text extraction, CJK, fonts). "
                    "Exits 4 with a failure report when no backend works; never produces a fake PDF.",
        epilog="Exit codes: 0 ok, 2 input/arg error, 3 dependency missing, 4 export failed.")
    p.add_argument("--input", required=True, help="source .docx file")
    p.add_argument("--output-dir", default="", help="output directory (default: next to the input)")
    p.add_argument("--prefix", default="", help="output file name prefix (default: input stem)")
    p.add_argument("--backend", default="", choices=["", *pdfmod.BACKENDS], help="force a backend: word or libreoffice")
    p.add_argument("--dry-run", action="store_true", help="only detect backends and show what would happen")
    p.add_argument("--force", action="store_true", help="overwrite the target PDF if it exists")
    p.add_argument("--report", default="", help="write JSON result/failure report to this path")
    p.add_argument("--timeout", type=positive_int, default=180, help="seconds to wait for the backend, whole number >= 1 (default 180)")
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
    if not src.is_file() or src.suffix.lower() != ".docx":
        raise ToolError("--input must be an existing .docx file", EXIT_INPUT)
    if args.report:
        refuse_if_protected(Path(args.report), [src], "report")
        ensure_parent_dir(Path(args.report))
    try:
        info = inspect_docx(src)
    except Exception as e:
        raise ToolError(f"input is not a valid DOCX: {e}", EXIT_INPUT)
    prefix = check_prefix(args.prefix or src.stem)
    out_dir = prepare_output_dir(Path(args.output_dir) if args.output_dir else src.parent, src, args.dry_run)
    backends = pdfmod.choose_backends(args.backend or None)
    if args.dry_run:
        for b in envinfo.pdf_backends():
            print(f"[dry-run] backend {b['name']}: {'available at ' + b['path'] if b['available'] else 'NOT available (' + b['note'] + ')'}")
        print(f"[dry-run] would write {out_dir / (prefix + '.pdf')}")
        return EXIT_OK
    prefix = pick_free_prefix(out_dir, prefix, [".pdf"], args.force)
    dest = out_dir / (prefix + ".pdf")
    expected = info["text"]
    result, code = None, EXIT_OK
    try:
        result = pdfmod.export_pdf(src, dest, backend=args.backend or None, force=args.force,
                                   expected_text=expected, timeout=args.timeout)
    except ToolError as e:
        result = {**getattr(e, "result", {"status": "failed"}), "error": redact(str(e))}
        code = e.code
        print(f"error: {redact(str(e))}", file=sys.stderr)
        for a in result.get("attempts", []):
            print(f"  attempt {a['backend']}: {a['result']} {redact(a.get('detail', ''))}", file=sys.stderr)
        for b in result.get("detected_backends", []):
            print(f"  detected {b['name']}: available={b['available']} path={b.get('path')}", file=sys.stderr)
        for alt in result.get("alternatives", []):
            print(f"  alternative: {alt}", file=sys.stderr)
    report = {"tool": "export_pdf", "version": __version__, "input": src.name, **result}
    if args.report:
        rp = write_json_report(Path(args.report), report, args.force)
        print(f"report: {rp}", file=sys.stderr)
    if code == EXIT_OK:
        v = result["verification"]
        print(f"PDF exported via {result['backend']}: {result['output']}")
        print(f"  pages={v['pages']} size={v['size_bytes']}B text_check={v['text_check']} "
              f"fonts_all_embedded={v.get('fonts_all_embedded')}")
        for w in v["warnings"]:
            print(f"  warning: {w}")
    return code


if __name__ == "__main__":
    sys.exit(main())
