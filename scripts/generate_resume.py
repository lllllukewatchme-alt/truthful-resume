#!/usr/bin/env python3
"""Generate Markdown / DOCX (/ PDF) resumes from a Markdown or JSON resume. Offline, stdlib only."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from resume_design.common import setup_console  # noqa: E402
from resume_design import __version__  # noqa: E402
from resume_design import pdf as pdfmod  # noqa: E402
from resume_design import validate as V  # noqa: E402
from resume_design.common import (EXIT_GENERATION, EXIT_INPUT, EXIT_OK, EXIT_VALIDATION,  # noqa: E402
                                  ToolError, check_prefix, pick_free_prefix, prepare_output_dir, redact,
                                  ensure_parent_dir, refuse_if_protected, report_unexpected, sha256_file, write_atomic,
                                  write_json_report)
from resume_design.docx_writer import inspect_docx  # noqa: E402
from resume_design.mdio import parse_markdown  # noqa: E402
from resume_design.model import visible_text  # noqa: E402
from resume_design.pipeline import (load_resume, missing_fonts, render_docx, render_markdown,  # noqa: E402
                                    resolve_context)
from resume_design.templates import list_templates  # noqa: E402

FORMATS = ("md", "docx", "pdf")


def build_parser():
    p = argparse.ArgumentParser(
        prog="generate_resume.py",
        description="Generate Markdown/DOCX/PDF resumes from a .md or .json resume. Never overwrites existing "
                    "files unless --force; never modifies the input; makes no network calls.",
        epilog="Exit codes: 0 ok, 2 input/arg error, 3 dependency missing, 4 generation/export failed, 5 validation failed.")
    p.add_argument("--input", required=True, help="resume source (.md or .json)")
    p.add_argument("--output-dir", default="out", help="output directory, created if missing (default: out)")
    p.add_argument("--prefix", default="", help="output file name prefix (default: input file stem)")
    p.add_argument("--template", default="", help=f"template name ({', '.join(list_templates())}); default: auto-select")
    p.add_argument("--lang", default="", help="resume language, e.g. zh or en (default: from data / detected)")
    p.add_argument("--locale", default="", help="target locale, e.g. zh-CN, en-US, en-GB (default: from data / lang)")
    p.add_argument("--formats", default="md,docx", help="comma list of md,docx,pdf (default: md,docx)")
    p.add_argument("--pdf-backend", default="", choices=["", *pdfmod.BACKENDS], help="force a PDF backend")
    p.add_argument("--ats-submission", action="store_true", help="auto-select the ats-clean template (online ATS upload)")
    p.add_argument("--clean-metadata", action="store_true", help="omit timestamps/title metadata in DOCX")
    p.add_argument("--paper", default="", choices=["", "A4", "Letter"], help="override paper size")
    p.add_argument("--allow-draft", action="store_true", help="generate even if validation errors exist (status stays draft)")
    p.add_argument("--confirm-ready", action="store_true",
                   help="HUMAN attestation: you checked facts, contact and target; allows status ready_to_submit "
                        "(also needs meta.review.* in the data). Assistants must not pass this on their own.")
    p.add_argument("--dry-run", action="store_true", help="show what would be generated; write nothing")
    p.add_argument("--force", action="store_true", help="overwrite the exact target files if they exist")
    p.add_argument("--report", default="", help="report JSON path (default: <output-dir>/<prefix>.report.json)")
    p.add_argument("--json", action="store_true", help="print the final summary as JSON")
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
    except Exception as e:  # last-resort: never leak a traceback or an undocumented exit code
        return report_unexpected(e)


def run(args) -> int:
    formats = [f.strip().lower() for f in args.formats.split(",") if f.strip()]
    bad = [f for f in formats if f not in FORMATS]
    if bad or not formats:
        raise ToolError(f"invalid --formats: {args.formats!r} (choose from md,docx,pdf)", EXIT_INPUT)
    src = Path(args.input)
    data, kind, in_sha = load_resume(src)
    prefix = check_prefix(args.prefix or src.stem)
    ctx = resolve_context(data, lang=args.lang, locale=args.locale, template=args.template,
                          ats_submission=args.ats_submission)
    d = ctx["data"]
    findings = V.check_data(data, lang=ctx["lang"], locale_rules=ctx["rules"])
    errors = [f for f in findings if f["level"] == "error"]
    miss, fonts_detectable = missing_fonts(ctx["style"])
    ats_safe = ctx["style"].get("ats", {}).get("safe", True)
    if not ats_safe:
        findings.append(V._f("template.not_ats_safe", "warning", "A",
                             f"template '{ctx['template']}' is not ATS-safe: also generate an ats-clean version"))

    out_dir = prepare_output_dir(Path(args.output_dir), src, args.dry_run)
    suffixes = {"md": ".md", "docx": ".docx", "pdf": ".pdf"}
    report_path = Path(args.report) if args.report else None
    # P0-1: never write over the input. An explicit --report is always checked; with --force the
    # output names are used as-is, so they are checked too (without --force a free name is picked).
    if report_path:
        refuse_if_protected(report_path, [src], "report")
        if not args.dry_run:
            ensure_parent_dir(report_path)      # fail before any file is generated, not after
    if args.force:
        for f in formats:
            refuse_if_protected(out_dir / (prefix + {"md": ".md", "docx": ".docx", "pdf": ".pdf"}[f]), [src], f.upper() + " output")
        refuse_if_protected(out_dir / f"{prefix}.report.json", [src], "report")
        refuse_if_protected(out_dir / f".{prefix}.intermediate.docx", [src], "intermediate file")
    plan ={"template": ctx["template"], "template_reason": ctx["template_reason"], "lang": ctx["lang"],
            "locale": ctx["locale"], "formats": formats, "output_dir": str(out_dir)}

    def summary(code, status, extra):
        out = {"exit_code": code, "status": status, **extra}
        if args.json:
            print(json.dumps(out, ensure_ascii=False, indent=2))
        return code

    if errors and not args.allow_draft:
        rep = V.build_report(findings, data, input_name=src.name, input_sha=in_sha, pdf_status="not_tested",
                             pdf_required="pdf" in formats, ats_safe=ats_safe, missing_fonts=miss,
                             fonts_detectable=fonts_detectable, extra={"plan": plan, "generated": []},
                             confirm_ready=args.confirm_ready)
        if not args.dry_run:
            rp = write_json_report(report_path or out_dir / f"{prefix}.report.json", rep, args.force)
            print(f"report: {rp}")
        print(V.format_report_text(rep), file=sys.stderr)
        print("validation failed: no files generated (use --allow-draft to force a draft)", file=sys.stderr)
        return summary(EXIT_VALIDATION, "draft", {"generated": [], "errors": len(errors)})

    prefix = pick_free_prefix(out_dir, prefix, [suffixes[f] for f in formats] + [".report.json"], args.force)
    targets = {f: out_dir / (prefix + suffixes[f]) for f in formats}
    if args.dry_run:
        print(f"[dry-run] template={ctx['template']} ({ctx['template_reason']}) lang={ctx['lang']} locale={ctx['locale']}")
        for f, t in targets.items():
            print(f"[dry-run] would write {t}")
        print(f"[dry-run] findings: {len(errors)} error(s), "
              f"{sum(1 for f in findings if f['level'] == 'warning')} warning(s)")
        return summary(EXIT_OK, "dry_run", {"would_write": [str(t) for t in targets.values()]})

    generated, stage_failed = [], None
    docx_path = None
    if "md" in formats:
        try:
            md_text = render_markdown(ctx)
            back = parse_markdown(md_text)           # round-trip guard: facts must survive Markdown output
            drift = [f for f in V.compare_versions(d, back) if f["level"] == "error"]
            if drift:
                raise ToolError("Markdown output would not reproduce your data (" + drift[0]["message"]
                                + "); Markdown file not written, other formats continue", EXIT_GENERATION)
            write_atomic(targets["md"], md_text.encode("utf-8"), args.force)
            generated.append(str(targets["md"]))
        except ToolError as e:
            print(f"error: {redact(str(e))}", file=sys.stderr)
            stage_failed = ("md", e)
    docx_findings = []
    try:
        if "docx" in formats or "pdf" in formats:
            docx_bytes = render_docx(ctx, args.clean_metadata, args.paper or None)

            def check(tmp):
                try:
                    info = inspect_docx(tmp)
                except Exception as e:  # zipfile.BadZipFile, KeyError, ParseError
                    raise ToolError(f"generated DOCX failed structure check: {e}", EXIT_GENERATION)
                fs = V.check_docx(info, d)
                docx_findings.extend(fs)
                hard = [f for f in fs if f["level"] == "error"]
                if hard:
                    raise ToolError("generated DOCX failed content check: " + hard[0]["message"], EXIT_GENERATION)

            dest = targets.get("docx") or (out_dir / (prefix + ".docx"))
            if "docx" not in formats:  # PDF-only request: keep an intermediate docx in a temp location
                dest = out_dir / f".{prefix}.intermediate.docx"
            write_atomic(dest, docx_bytes, args.force, validator=check)
            docx_path = dest
            if "docx" in formats:
                generated.append(str(dest))
            findings += [f for f in docx_findings if f["id"] != "docx.placeholder"]
    except ToolError as e:
        print(f"error: {redact(str(e))}", file=sys.stderr)
        stage_failed = stage_failed or ("docx", e)
        docx_path = None

    pdf_status, pdf_result = "not_tested", None
    if "pdf" in formats and docx_path is not None:
        try:
            pdf_result = pdfmod.export_pdf(docx_path, targets["pdf"], backend=args.pdf_backend or None,
                                           force=args.force, expected_text=visible_text(d),
                                           page_limit=d["preferences"].get("page_limit"))
            pdf_status = "passed"
            generated.append(pdf_result["output"])
            if pdf_result["verification"].get("page_limit_exceeded"):
                findings.append(V._f("pdf.page_limit", "warning", "A",
                                     f"rendered PDF has {pdf_result['verification']['pages']} pages; page_limit is {d['preferences'].get('page_limit')}"))
        except ToolError as e:
            pdf_status = getattr(e, "result", {}).get("status", "failed")
            pdf_result = getattr(e, "result", {"status": pdf_status})
            stage_failed = stage_failed or ("pdf", e)
            print(f"error: {redact(str(e))}", file=sys.stderr)
            for alt in pdf_result.get("alternatives", []):
                print(f"  alternative: {alt}", file=sys.stderr)
    if "pdf" in formats and docx_path is not None and "docx" not in formats:
        docx_path.unlink(missing_ok=True)

    artifacts = {"generated": [Path(g).name for g in generated],
                 "template": ctx["template"], "lang": ctx["lang"], "locale": ctx["locale"]}
    if pdf_result:
        artifacts["pdf"] = {k: v for k, v in pdf_result.items() if k != "output"}
    if "pdf" in formats:
        pdf_for_status = pdf_status
    else:
        pdf_for_status = "not_tested"
    rep = V.build_report(findings, data, input_name=src.name, input_sha=in_sha, pdf_status=pdf_for_status,
                         pdf_required="pdf" in formats, ats_safe=ats_safe, missing_fonts=miss,
                         fonts_detectable=fonts_detectable, artifacts=artifacts,
                         extra={"plan": plan, "partial_success": bool(stage_failed and generated),
                                "failed_stage": stage_failed[0] if stage_failed else None,
                                "input_unchanged": sha256_file(src) == in_sha}, confirm_ready=args.confirm_ready)
    rp = write_json_report(report_path or out_dir / f"{prefix}.report.json", rep, args.force)
    print(V.format_report_text(rep))
    for g in generated:
        print(f"generated: {g}")
    print(f"report: {rp}")
    if stage_failed:
        if generated:
            print(f"PARTIAL SUCCESS: {len(generated)} file(s) generated; failed stage: {stage_failed[0]}", file=sys.stderr)
        return summary(stage_failed[1].code, rep["status"], {"generated": generated, "failed_stage": stage_failed[0]})
    return summary(EXIT_OK, rep["status"], {"generated": generated, "report": str(rp)})


if __name__ == "__main__":
    sys.exit(main())
