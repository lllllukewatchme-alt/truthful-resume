"""Canonical resume data model: normalisation, placeholders, text iteration."""
from __future__ import annotations

import copy
import re

PLACEHOLDER_RE = re.compile(r"\{\{MISSING:([A-Za-z0-9_.\[\]-]+)\}\}")
SECTION_KEYS = ["summary", "education", "experience", "projects", "skills",
                "certificates", "languages", "awards"]
ENTRY_SECTIONS = ["education", "experience", "projects"]
STATUS_VALUES = ["user_provided", "ai_suggested", "user_confirmed", "unconfirmed"]
STATUS_NEEDS_REVIEW = {"ai_suggested", "unconfirmed"}


def empty_resume() -> dict:
    return {
        "basics": {"name": "", "email": "", "phone": "", "location": "", "website": "", "summary": ""},
        "target": {"role": "", "industry": "", "locale": "", "language": "", "job_description": ""},
        "education": [], "experience": [], "projects": [], "skills": [],
        "certificates": [], "languages": [], "awards": [],
        "preferences": {"template": "", "page_limit": 2, "photo": False},
    }


def _entry(e) -> dict:
    if not isinstance(e, dict):
        return {"organization": str(e), "role": "", "bullets": []}
    out = dict(e)
    out.setdefault("organization", "")
    out.setdefault("role", "")
    out.setdefault("location", "")
    out.setdefault("start", "")
    out.setdefault("end", "")
    out.setdefault("description", "")
    out.setdefault("evidence", [])
    out.setdefault("confirmation_status", "user_provided")
    bullets = out.get("bullets")
    bullets = bullets if isinstance(bullets, list) else []   # wrong types are reported by the schema check
    out["bullets"] = [b if isinstance(b, (str, dict)) else str(b) for b in bullets]
    if isinstance(out["evidence"], str):
        out["evidence"] = [out["evidence"]] if out["evidence"] else []
    elif not isinstance(out["evidence"], list):
        out["evidence"] = []
    return out


def normalize(data: dict) -> dict:
    """Fill defaults without altering content. Does not mutate the input. Never raises on wrong types
    (the schema check reports them); wrongly typed sections become empty."""
    base = empty_resume()
    d = copy.deepcopy(data) if isinstance(data, dict) else {}
    for k in ("basics", "target", "preferences"):
        if not isinstance(d.get(k), dict):
            d[k] = {}
        merged = dict(base[k])
        merged.update(d[k])
        d[k] = merged
    for k in ENTRY_SECTIONS:
        d[k] = [_entry(e) for e in d[k]] if isinstance(d.get(k), list) else []
    for k in ("skills", "certificates", "languages", "awards"):
        d[k] = list(d[k]) if isinstance(d.get(k), list) else []
    if not isinstance(d.get("meta"), dict):
        d["meta"] = {}
    return d


def bullet_text(b) -> str:
    return b.get("text", "") if isinstance(b, dict) else str(b)


def bullet_status(b) -> str:
    return b.get("status", "") if isinstance(b, dict) else ""


def iter_texts(data: dict):
    """Yield (path, text) for every user-facing string in the resume."""
    for k, v in data.get("basics", {}).items():
        if isinstance(v, str):
            yield f"basics.{k}", v
        elif isinstance(v, dict):
            for kk, vv in v.items():
                yield f"basics.{k}.{kk}", str(vv)
    for k in ("role", "industry"):
        yield f"target.{k}", str(data.get("target", {}).get(k, ""))
    for sec in ENTRY_SECTIONS:
        for i, e in enumerate(data.get(sec, [])):
            for f in ("organization", "role", "location", "start", "end", "description"):
                yield f"{sec}[{i}].{f}", str(e.get(f, ""))
            for j, b in enumerate(e.get("bullets", [])):
                yield f"{sec}[{i}].bullets[{j}]", bullet_text(b)
    for i, s in enumerate(data.get("skills", [])):
        if isinstance(s, dict):
            yield f"skills[{i}].category", str(s.get("category", ""))
            for j, it in enumerate(s.get("items", [])):
                yield f"skills[{i}].items[{j}]", str(it)
        else:
            yield f"skills[{i}]", str(s)
    for sec in ("certificates", "languages", "awards"):
        for i, c in enumerate(data.get(sec, [])):
            if isinstance(c, dict):
                for f, v in c.items():
                    if isinstance(v, str):
                        yield f"{sec}[{i}].{f}", v
            else:
                yield f"{sec}[{i}]", str(c)


def find_placeholders(data: dict) -> list[dict]:
    out = []
    for path, text in iter_texts(data):
        for m in PLACEHOLDER_RE.finditer(text):
            out.append({"field": m.group(1), "path": path})
    return out


def full_text(data: dict) -> str:
    return "\n".join(t for _, t in iter_texts(data) if t)


def visible_text(data: dict) -> str:
    """Text that appears verbatim in rendered output. Excluded: dates (reformatted) and the 'target.*' fields
    (they steer template/locale choice and are not printed)."""
    skip = (".start", ".end", ".date")
    return "\n".join(t for path, t in iter_texts(data)
                     if t and not path.endswith(skip) and not path.startswith("target."))
