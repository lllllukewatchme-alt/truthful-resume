"""Resume validation with three-tier reporting.

A = automatically verifiable   B = needs human confirmation   C = not verifiable in this environment
"""
from __future__ import annotations

import datetime as _dt
import re

from . import __version__, dates
from .common import snippet
from .model import (ENTRY_SECTIONS, PLACEHOLDER_RE, STATUS_NEEDS_REVIEW, STATUS_VALUES, bullet_status,
                    bullet_text, find_placeholders, full_text, iter_texts, normalize, visible_text)
from .schema_check import validate_schema

_SURROGATE = re.compile("[" + chr(0xD800) + "-" + chr(0xDFFF) + "]")
CJK = re.compile(r"[一-鿿]")
_EMAIL_OK = re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$")
_METRIC = re.compile(r"\d+(?:\.\d+)?\s*(?:%|％|倍|万|亿|千|百|k\b|K\b|M\b|x\b|X\b|人|台|个|家|次|ms|秒|小时|天|元)|"
                     r"(?:提升|降低|减少|增长|节省|提高|reduced|increased|improved|saved|grew|cut)\D{0,12}\d")
_RISK_WORDS = re.compile(r"精通|行业领先|全球领先|第一|唯一|最佳|best|world-class|expert in|guru|ninja|"
                         r"主导|独立负责|full responsibility|single-handedly", re.I)


def _f(fid, level, category, message, path="", **extra):
    d = {"id": fid, "level": level, "category": category, "message": message}
    if path:
        d["path"] = path
    d.update(extra)
    return d


def check_data(data: dict, *, lang: str = "", locale_rules: dict | None = None, page_limit: int | None = None) -> list[dict]:
    """Category A checks on structured data. Returns findings (never mutates data)."""
    out: list[dict] = []
    raw = data
    schema_errors = validate_schema(raw)
    for path, msg in schema_errors:
        out.append(_f("schema", "error", "A", f"{msg}", path))
    if schema_errors:       # structure is unreliable: report it and stop (later checks assume the right types)
        return out
    d = normalize(raw)
    b = d["basics"]
    bad_chars = [p for p, t in iter_texts(d) if _SURROGATE.search(t)]
    for p in bad_chars:     # path only: the offending text must never reach a report
        out.append(_f("text.invalid_char", "error", "A", "text contains an unpaired surrogate character (not valid Unicode)", p))
    if bad_chars:
        return out

    # required content
    name = (b.get("name") or "").strip()
    if not name:
        out.append(_f("required.name", "error", "A", "basics.name is required", "basics.name"))
    if not (b.get("email") or "").strip() and not (b.get("phone") or "").strip():
        out.append(_f("required.contact", "error", "A", "at least one of email/phone is required "
                      "(use {{MISSING:email}} to keep a visible placeholder)", "basics"))
    if not any(d[s] for s in ENTRY_SECTIONS):
        out.append(_f("required.sections", "error", "A", "need at least one of education / experience / projects"))
    if d["experience"] == [] and d["projects"] == [] and d["education"]:
        out.append(_f("sections.no_experience", "info", "A", "no experience/projects: acceptable for new graduates"))

    # placeholders
    phs = find_placeholders(d)
    for ph in phs:
        out.append(_f("placeholder", "warning", "A", f"unresolved placeholder for '{ph['field']}'", ph["path"]))

    # content the renderers cannot place (Markdown sections with unknown headings): never drop silently
    for title in dict.fromkeys(d.get("meta", {}).get("unknown_sections", []) or []):
        out.append(_f("section.unknown", "warning", "A",
                      f"section '{snippet(title, 40)}' is not a recognised section and is NOT rendered in the output; "
                      "rename it to a known section (see core/data-model.md) or confirm it should be left out", "meta.unknown_sections"))

    # contact format
    email = (b.get("email") or "").strip()
    if email and not PLACEHOLDER_RE.search(email) and not _EMAIL_OK.match(email):
        out.append(_f("format.email", "warning", "A", "email address looks malformed", "basics.email"))
    phone = (b.get("phone") or "").strip()
    if phone and not PLACEHOLDER_RE.search(phone):
        digits = re.sub(r"\D", "", phone)
        if not 7 <= len(digits) <= 15:
            out.append(_f("format.phone", "warning", "A", "phone number length looks unusual", "basics.phone"))
        elif (locale_rules or {}).get("lang") == "en" and not phone.startswith("+"):
            out.append(_f("format.phone_country_code", "info", "A",
                          "overseas application: consider adding the country code (confirm with the user)", "basics.phone"))

    # dates / entries / empties
    today = _dt.date.today()
    for sec in ENTRY_SECTIONS:
        prev_start = None
        for i, e in enumerate(d[sec]):
            p = f"{sec}[{i}]"
            if not str(e.get("organization", "")).strip():
                out.append(_f("empty.organization", "error", "A", "entry without organization/name", p))
            status = e.get("confirmation_status", "user_provided")
            if status not in STATUS_VALUES:
                out.append(_f("status.invalid", "error", "A", f"invalid confirmation_status '{status}'", p))
            parsed = {}
            for f in ("start", "end"):
                v = str(e.get(f, "") or "")
                if not v or PLACEHOLDER_RE.search(v):
                    continue
                try:
                    parsed[f] = dates.parse_date(v)
                except dates.DateError:
                    out.append(_f("date.format", "error", "A", f"unrecognised date '{snippet(v, 20)}'", f"{p}.{f}"))
            if sec != "education" and not e.get("start") and not PLACEHOLDER_RE.search(str(e.get("start", ""))):
                out.append(_f("date.missing", "warning", "A", "entry has no start date", p))
            if "start" in parsed and "end" in parsed:
                if dates.sort_key(parsed["start"]) > dates.sort_key(parsed["end"]):
                    out.append(_f("date.order", "error", "A", "start date is after end date", p))
            if "start" in parsed and parsed["start"] != "present":
                if dates.sort_key(parsed["start"]) > (today.year, today.month) and sec == "experience":
                    out.append(_f("date.future", "warning", "A", "experience starts in the future", p))
                if prev_start and dates.sort_key(parsed["start"]) > dates.sort_key(prev_start) and sec == "experience":
                    out.append(_f("order.reverse_chronological", "info", "A",
                                  "experience is not in reverse-chronological order", p))
                prev_start = parsed["start"]
            for j, bl in enumerate(e.get("bullets", [])):
                if not bullet_text(bl).strip():
                    out.append(_f("empty.paragraph", "warning", "A", "empty bullet", f"{p}.bullets[{j}]"))

    # certificates must not be AI-invented
    for i, c in enumerate(d["certificates"]):
        st = c.get("confirmation_status") if isinstance(c, dict) else None
        if st in ("ai_suggested", "unconfirmed"):
            out.append(_f("fabrication.certificate", "error", "A",
                          "certificate not confirmed by the user; remove it or obtain confirmation/evidence",
                          f"certificates[{i}]"))

    # duplicates
    seen: dict[str, str] = {}
    for path, text in iter_texts(d):
        t = re.sub(r"\s+", " ", text).strip().lower()
        if len(t) >= 12 and (".bullets[" in path or path.endswith("description") or path == "basics.summary"):
            if t in seen:
                out.append(_f("duplicate.paragraph", "warning", "A",
                              f"duplicate text ('{snippet(text, 16)}') also at {seen[t]}", path))
            else:
                seen[t] = path

    # language sanity
    text = full_text(d)
    if lang and len(text) > 60:
        ratio = len(CJK.findall(text)) / max(1, len(text))
        if lang.startswith("en") and ratio > 0.10:
            out.append(_f("lang.mismatch", "warning", "A", f"lang=en but {ratio:.0%} of text is CJK"))
        if lang.startswith("zh") and ratio < 0.02:
            out.append(_f("lang.mismatch", "warning", "A", "lang=zh but almost no CJK text found"))

    # preferences
    prefs = d["preferences"]
    if prefs.get("photo"):
        out.append(_f("preferences.photo", "warning", "A", "photo embedding is not supported in v1; flag ignored"))
    if locale_rules is not None and not locale_rules.get("known_locale", True):
        out.append(_f("locale.unknown", "warning", "A", "locale has no specific rules; generic defaults applied (confirm local conventions with the user)"))
    if page_limit is None:
        page_limit = prefs.get("page_limit")
    return out


def manual_review_items(d: dict, has_jd: bool) -> list[dict]:
    """Category B: always listed; never auto-passed."""
    d = normalize(d)
    items = []
    n_entries = sum(len(d[s]) for s in ENTRY_SECTIONS)
    items.append({"id": "facts", "message": "Confirm employers, titles, dates and degrees are accurate",
                  "count": n_entries})
    metrics, risky, unconfirmed = [], [], []
    for sec in ENTRY_SECTIONS:
        for i, e in enumerate(d[sec]):
            has_ev = bool(e.get("evidence")) or e.get("confirmation_status") == "user_confirmed"
            if e.get("confirmation_status") in STATUS_NEEDS_REVIEW:
                unconfirmed.append(f"{sec}[{i}]")
            for j, b in enumerate(e.get("bullets", [])):
                t = bullet_text(b)
                st = bullet_status(b)
                if st in STATUS_NEEDS_REVIEW:
                    unconfirmed.append(f"{sec}[{i}].bullets[{j}]")
                if _METRIC.search(t) and not has_ev:
                    metrics.append({"path": f"{sec}[{i}].bullets[{j}]", "excerpt": snippet(t, 30)})
                if _RISK_WORDS.search(t):
                    risky.append({"path": f"{sec}[{i}].bullets[{j}]", "excerpt": snippet(t, 30)})
    items.append({"id": "metrics", "message": "Quantified claims without recorded evidence: confirm each with the user",
                  "count": len(metrics), "items": metrics})
    items.append({"id": "exaggeration", "message": "Wording that may overstate responsibility or ranking",
                  "count": len(risky), "items": risky})
    items.append({"id": "ai_rewrites", "message": "AI-suggested/unconfirmed content awaiting user approval",
                  "count": len(unconfirmed), "items": unconfirmed})
    if has_jd:
        items.append({"id": "jd_match", "message": "Confirm JD-match assessment and keyword naturalness"})
    items.append({"id": "completeness", "message": "Check that no important experience is missing"})
    items.append({"id": "translation", "message": "If translated: confirm meaning is preserved (titles, degrees, culture-specific terms)"})
    items.append({"id": "final", "message": "Confirm contact details and the final version before submitting"})
    return items


def environment_items(pdf_checked: bool, ats_safe: bool, missing_fonts: list[str] | None,
                      fonts_detectable: bool = True) -> list[dict]:
    """Category C."""
    items = []
    if not pdf_checked:
        items.append({"id": "pagination", "message": "Real pagination/page count not verified (no rendered PDF)"})
    items.append({"id": "word_versions", "message": "Appearance in other Word versions / WPS / Pages is not verified"})
    items.append({"id": "ats_parser", "message": "Behaviour in the target applicant tracking system is not verifiable offline"})
    if missing_fonts:
        items.append({"id": "fonts_missing", "message": "Fonts not installed here; final rendering will use fallbacks: "
                      + ", ".join(missing_fonts)})
    elif not fonts_detectable:
        items.append({"id": "fonts_unknown", "message": "Installed fonts could not be detected"})
    if not ats_safe:
        items.append({"id": "layout_ats", "message": "Selected template uses columns/tables: not ATS-safe; also generate ats-clean"})
    return items


def compute_status(findings: list[dict], data: dict, pdf_status: str | None, pdf_required: bool,
                   confirm_ready: bool = False) -> tuple[str, list[str]]:
    d = normalize(data)
    errors = [f for f in findings if f["level"] == "error"]
    reasons = []
    if errors:
        reasons.append(f"{len(errors)} blocking validation error(s)")
        return "draft", reasons
    placeholders = [f for f in findings if f["id"] == "placeholder"]
    unknown = [f for f in findings if f["id"] == "section.unknown"]
    overflow = [f for f in findings if f["id"] == "pdf.page_limit"]
    pending = [it for it in manual_review_items(d, False) if it["id"] == "ai_rewrites" and it["count"]]
    if placeholders:
        reasons.append(f"{len(placeholders)} unresolved placeholder(s)")
    if unknown:
        reasons.append(f"{len(unknown)} section(s) not rendered")
    if overflow:
        reasons.append("page limit exceeded: " + overflow[0]["message"])
    if pending:
        reasons.append(f"{pending[0]['count']} unconfirmed AI-suggested item(s)")
    if reasons:
        return "needs_review", reasons
    review = d.get("meta", {}).get("review", {})
    review = review if isinstance(review, dict) else {}
    confirmed = all(review.get(k) is True for k in ("facts_confirmed", "contact_confirmed", "target_confirmed"))
    if not confirmed:
        why = ("--confirm-ready was given, but meta.review.facts_confirmed/contact_confirmed/target_confirmed are not all true in the data"
               if confirm_ready else "automatic checks passed; user confirmation of facts/contact/target missing (meta.review)")
        return "validated", [why]
    if not confirm_ready:
        return "validated", ["meta.review is set in the data, but ready_to_submit also needs the human to pass --confirm-ready "
                             "(a flag in a data file can be written by anyone, including an AI assistant)"]
    if pdf_required and pdf_status != "passed":
        return "validated", [f"user confirmed, but requested PDF status is '{pdf_status}'"]
    return "ready_to_submit", ["user confirmed facts, contact and target (meta.review + --confirm-ready); no blocking items"]


def check_docx(info: dict, data: dict | None) -> list[dict]:
    """A-level checks on an inspected DOCX (see docx_writer.inspect_docx)."""
    out = []
    text = info["text"]
    if info["heading1"] < 1:
        out.append(_f("docx.structure", "error", "A", "DOCX has no section headings (Heading1)"))
    if len(text.strip()) < 20:
        out.append(_f("docx.empty", "error", "A", "DOCX has almost no text"))
    for m in PLACEHOLDER_RE.finditer(text):
        out.append(_f("docx.placeholder", "warning", "A", f"placeholder '{m.group(1)}' present in DOCX"))
    if data is not None:
        d = normalize(data)
        want = set(CJK.findall(visible_text(d)))
        have = set(CJK.findall(text))
        lost = want - have
        if lost:
            out.append(_f("docx.cjk_loss", "error", "A", f"{len(lost)} CJK character(s) missing from DOCX text"))
        name = d["basics"].get("name", "")
        if name and name not in text and not d["basics"].get("name_parts"):
            out.append(_f("docx.name", "error", "A", "name not found in DOCX text"))
        for sec in ENTRY_SECTIONS:
            for i, e in enumerate(d[sec]):
                org = e.get("organization", "")
                if org and org not in text:
                    out.append(_f("docx.entry_missing", "error", "A", "entry organization missing from DOCX", f"{sec}[{i}]"))
    if info.get("creator"):
        out.append(_f("docx.author", "warning", "A", "DOCX has an author set; use clean metadata if unwanted"))
    return out


def compare_versions(a: dict, b: dict) -> list[dict]:
    """Cross-version consistency (e.g. zh vs en): dates, counts and numbers must not drift."""
    a, b = normalize(a), normalize(b)
    out = []
    for sec in ENTRY_SECTIONS:
        if len(a[sec]) != len(b[sec]):
            out.append(_f("compare.count", "error", "A", f"{sec}: entry count differs ({len(a[sec])} vs {len(b[sec])})"))
            continue
        for i, (x, y) in enumerate(zip(a[sec], b[sec])):
            for f in ("start", "end"):
                if str(x.get(f, "")) != str(y.get(f, "")):
                    out.append(_f("compare.date", "error", "A", f"{f} differs", f"{sec}[{i}].{f}"))
            nx = sorted(re.findall(r"\d+(?:\.\d+)?", " ".join(bullet_text(t) for t in x.get("bullets", []))))
            ny = sorted(re.findall(r"\d+(?:\.\d+)?", " ".join(bullet_text(t) for t in y.get("bullets", []))))
            if nx != ny:
                out.append(_f("compare.numbers", "error", "A", "numbers in bullets differ between versions", f"{sec}[{i}]"))
            if len(x.get("bullets", [])) != len(y.get("bullets", [])):
                out.append(_f("compare.bullets", "warning", "A", "bullet count differs", f"{sec}[{i}]"))
    for k in ("email", "phone"):
        if a["basics"].get(k) != b["basics"].get(k):
            out.append(_f("compare.contact", "error", "A", f"{k} differs between versions"))
    return out


def build_report(findings: list[dict], data: dict | None, *, input_name: str, input_sha: str | None,
                 pdf_status: str, pdf_required: bool, ats_safe: bool, missing_fonts, fonts_detectable,
                 artifacts: dict | None = None, extra: dict | None = None, confirm_ready: bool = False) -> dict:
    data_n = normalize(data) if data is not None else None
    status, reasons = compute_status(findings, data_n, pdf_status, pdf_required, confirm_ready) if data_n else ("draft", ["no structured data"])
    has_jd = bool(data_n and data_n["target"].get("job_description"))
    counts = {lv: sum(1 for f in findings if f["level"] == lv) for lv in ("error", "warning", "info")}
    rep = {
        "tool": "resume-design", "version": __version__,
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "input": {"name": input_name, "sha256": input_sha},
        "status": status, "status_reasons": reasons,
        "pdf_status": pdf_status,
        "confirmed_via_cli": bool(confirm_ready),
        "A_automated": {"counts": counts, "findings": findings},
        "B_manual_review": manual_review_items(data_n, has_jd) if data_n else [],
        "C_environment_unverifiable": environment_items(pdf_status == "passed", ats_safe, missing_fonts, fonts_detectable),
        "notes": ["Generated files do not imply ready_to_submit; manual items (B) are never auto-passed."],
    }
    if artifacts:
        rep["artifacts"] = artifacts
    if extra:
        rep.update(extra)
    return rep


def format_report_text(rep: dict) -> str:
    lines = [f"Status: {rep['status']}  ({'; '.join(rep.get('status_reasons', []))})",
             f"PDF: {rep.get('pdf_status')}"]
    a = rep["A_automated"]
    lines.append(f"[A] automated: {a['counts']['error']} error(s), {a['counts']['warning']} warning(s), {a['counts']['info']} info")
    for f in a["findings"]:
        if f["level"] != "info":
            lines.append(f"  - {f['level'].upper()} {f['id']}: {f['message']}" + (f" [{f['path']}]" if f.get("path") else ""))
    lines.append("[B] needs human confirmation (not auto-passed):")
    for it in rep["B_manual_review"]:
        lines.append(f"  - {it['id']}: {it['message']}" + (f" ({it['count']})" if "count" in it else ""))
    lines.append("[C] not verifiable in this environment:")
    for it in rep["C_environment_unverifiable"]:
        lines.append(f"  - {it['id']}: {it['message']}")
    return "\n".join(lines)
