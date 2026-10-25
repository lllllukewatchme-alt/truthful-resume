"""Load content templates, style configs, i18n rules; template selection."""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import ROOT
from .common import EXIT_INPUT, ToolError

TEMPLATES_DIR = ROOT / "templates"
STYLE_NAMES = ["ats-clean", "technical", "management", "modern-business", "creative"]
DEFAULT_TEMPLATE = "modern-business"


def _load_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ToolError(f"cannot load config {p.name}: {e}", EXIT_INPUT)


def load_i18n() -> dict:
    return _load_json(TEMPLATES_DIR / "i18n.json")


def list_templates() -> list[str]:
    return sorted(p.stem for p in (TEMPLATES_DIR / "styles").glob("*.json"))


def load_style(name: str) -> dict:
    if not re.fullmatch(r"[a-z0-9-]+", name or ""):
        raise ToolError(f"invalid template name: {name!r}", EXIT_INPUT)
    p = TEMPLATES_DIR / "styles" / f"{name}.json"
    if not p.is_file():
        raise ToolError(f"unknown template '{name}'. Available: {', '.join(list_templates())}", EXIT_INPUT)
    return _load_json(p)


def load_content_template(name: str) -> dict:
    """Parse templates/content/<name>.md: 'key: value' header lines before '---'."""
    p = TEMPLATES_DIR / "content" / f"{name}.md"
    if not p.is_file():
        p = TEMPLATES_DIR / "content" / "general.md"
    text = p.read_text(encoding="utf-8")
    cfg = {"section_order": ["summary", "experience", "projects", "education", "skills",
                             "certificates", "languages", "awards"], "max_bullets": 0, "guidance": text}
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                k, v = k.strip(), v.strip()
                if k == "section_order":
                    cfg[k] = [s.strip() for s in v.split(",") if s.strip()]
                elif k == "max_bullets":
                    cfg[k] = int(v or 0)
                else:
                    cfg[k] = v
    return cfg


def locale_rules(i18n: dict, locale: str, lang: str) -> dict:
    locales = i18n["locales"]
    if not locale:
        locale = i18n.get("default_locale_for_lang", {}).get(lang, "")
    rules = dict(locales.get(locale, locales["default"]))
    rules["locale"] = locale or "default"
    rules["known_locale"] = locale in locales
    return rules


# Selection rules are data, overridable via templates/selection-rules.json or caller.
DEFAULT_RULES = {
    "ats": "ats-clean",
    "technical_keywords": ["engineer", "developer", "software", "devops", "data", "algorithm", "sre",
                           "工程师", "开发", "算法", "测试", "运维", "架构", "研发", "技术", "程序员", "后端", "前端"],
    "management_keywords": ["director", "vp", "head of", "chief", "cto", "ceo", "manager", "总监", "经理",
                           "负责人", "总经理", "副总裁", "主管", "高管"],
    "creative_keywords": ["designer", "creative", "art director", "illustrator", "设计师", "设计", "美术", "创意", "插画"],
    "default": DEFAULT_TEMPLATE,
}


def choose_template(role: str, explicit: str = "", ats_submission: bool = False,
                    rules: dict | None = None) -> tuple[str, str]:
    """Return (template, reason). Explicit user choice always wins."""
    r = dict(DEFAULT_RULES)
    custom = TEMPLATES_DIR / "selection-rules.json"
    if custom.is_file():
        r.update(_load_json(custom))
    if rules:
        r.update(rules)
    if explicit:
        return explicit, "explicit user choice"
    if ats_submission:
        return r["ats"], "online/ATS submission"
    low = (role or "").lower()
    # management is checked before technical so 'engineering manager' is treated as management
    for key, tpl in (("management_keywords", "management"), ("creative_keywords", "creative"),
                     ("technical_keywords", "technical")):
        if any(k.lower() in low for k in r[key]):
            return tpl, f"role matches {key}"
    return r["default"], "default"
