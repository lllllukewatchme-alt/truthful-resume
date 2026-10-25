"""Shared glue used by the CLI scripts: load, resolve options, render."""
from __future__ import annotations

from pathlib import Path

from . import envinfo
from .common import EXIT_INPUT, ToolError, load_input, sha256_file
from .docx_writer import build_docx
from .mdio import parse_markdown, to_markdown
from . import dates
from .model import ENTRY_SECTIONS, full_text, normalize
from .templates import (choose_template, load_content_template, load_i18n, load_style, locale_rules)

import re

_CJK = re.compile(r"[一-鿿]")


def load_resume(path: Path) -> tuple[dict, str, str]:
    """Return (normalized data, input kind, sha256 of the input file)."""
    if not Path(path).is_file():
        raise ToolError(f"input file not found: {Path(path).name}", EXIT_INPUT)
    sha = sha256_file(Path(path))
    kind, payload = load_input(path)
    if kind == "md":
        data = parse_markdown(payload)
        if not data["basics"]["name"]:
            raise ToolError("Markdown input has no '# Name' title line", EXIT_INPUT)
        return data, kind, sha
    return payload, kind, sha  # raw JSON; validated by check_data before normalisation use


def detect_lang(data: dict) -> str:
    text = full_text(normalize(data))
    return "zh" if text and len(_CJK.findall(text)) / max(1, len(text)) > 0.10 else "en"


_NEWLINES = re.compile(r"\s*[\r\n]+\s*")


def _one_line(value):
    """Collapse line breaks in a single-line field to one space (whitespace only; wording is untouched)."""
    if isinstance(value, str):
        return _NEWLINES.sub(" ", value).strip()
    if isinstance(value, list):
        return [_one_line(v) for v in value]
    if isinstance(value, dict):
        return {k: _one_line(v) for k, v in value.items()}
    return value


def _canonical_date(value):
    try:
        return dates.parse_date(value) if isinstance(value, str) and value.strip() else value
    except dates.DateError:
        return value  # invalid dates are reported by the validator, never rewritten


def canonicalize(d: dict) -> dict:
    """Return the data in the single form every renderer (and the Markdown round-trip guard) agrees on:
    dates as YYYY / YYYY-MM / present, no line breaks inside single-line fields. Facts are not changed."""
    d = dict(d)
    for key in ("basics", "education", "experience", "projects", "skills", "certificates", "languages", "awards"):
        d[key] = _one_line(d[key])
    for sec in ENTRY_SECTIONS:
        for e in d[sec]:
            e["start"], e["end"] = _canonical_date(e.get("start", "")), _canonical_date(e.get("end", ""))
    for sec in ("certificates", "awards"):
        for e in d[sec]:
            if isinstance(e, dict) and "date" in e:
                e["date"] = _canonical_date(e["date"])
    return d


def resolve_context(data: dict, *, lang: str = "", locale: str = "", template: str = "",
                    ats_submission: bool = False) -> dict:
    d = canonicalize(normalize(data))
    i18n = load_i18n()
    lang = lang or str(d["target"].get("language") or "")
    if not lang:
        loc_hint = locale or str(d["target"].get("locale") or "")
        lang = i18n["locales"].get(loc_hint, {}).get("lang") or detect_lang(d)
    lang_base = lang.split("-")[0].lower()
    if lang_base not in i18n["labels"]:
        raise ToolError(f"unsupported language '{lang}' (supported: {', '.join(sorted(i18n['labels']))}; "
                        "add section labels to templates/i18n.json to support another language)", EXIT_INPUT)
    locale = locale or str(d["target"].get("locale") or "")
    rules = locale_rules(i18n, locale, lang_base)
    # precedence: --template > --ats-submission > stored preference > role rules > default
    explicit = template or ("" if ats_submission else str(d["preferences"].get("template") or ""))
    tpl, reason = choose_template(str(d["target"].get("role", "") or ""), explicit, ats_submission)
    style = load_style(tpl)
    content = load_content_template(tpl)
    labels = i18n["labels"].get(lang_base) or i18n["labels"]["en"]
    order = d.get("meta", {}).get("section_order") or content["section_order"]
    order = [k for k in order if k in labels]
    for k in ("summary", "education", "experience", "projects", "skills", "certificates", "languages", "awards"):
        if k not in order:
            order.append(k)  # never drop user content because of a template's order
    return {"data": d, "lang": lang_base, "locale": rules["locale"], "rules": rules, "template": tpl,
            "template_reason": reason, "style": style, "labels": labels, "order": order, "content": content}


def render_markdown(ctx: dict) -> str:
    d = ctx["data"]
    front = {"template": ctx["template"], "lang": ctx["lang"], "locale": ctx["locale"],
             "page_limit": d["preferences"].get("page_limit"), "role": d["target"].get("role"),
             "industry": d["target"].get("industry")}
    return to_markdown(d, ctx["lang"], ctx["rules"], ctx["order"], ctx["labels"], front)


def render_docx(ctx: dict, clean_metadata: bool = False, paper: str | None = None) -> bytes:
    return build_docx(ctx["data"], ctx["style"], ctx["labels"], ctx["rules"], ctx["order"], ctx["lang"],
                      clean_metadata=clean_metadata, paper=paper)


def missing_fonts(style: dict) -> tuple[list[str], bool]:
    fonts = envinfo.installed_fonts()
    if fonts is None:
        return [], False
    wanted = {style["fonts"]["latin"], style["fonts"]["east_asian"]}
    return sorted(f for f in wanted if envinfo.font_available(fonts, f) is False), True
