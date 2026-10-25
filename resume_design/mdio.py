"""Markdown <-> canonical resume dict.

Markdown dialect (see core/data-model.md):
  optional front matter (--- key: value ---), "# Name", contact bullets
  ("- email: x"), "## Section" headings (zh/en aliases), "### org | role | start - end | location"
  entries with bullets, plain-text description lines and "<!-- status: .. -->" /
  "<!-- evidence: .. -->" comments.
"""
from __future__ import annotations

import re

from . import dates
from .model import ENTRY_SECTIONS, STATUS_VALUES, bullet_text, empty_resume, normalize
from .templates import load_i18n

FRONT_KEYS = {"template": ("preferences", "template"), "page_limit": ("preferences", "page_limit"),
              "lang": ("target", "language"), "locale": ("target", "locale"),
              "role": ("target", "role"), "industry": ("target", "industry")}


def _alias_map(i18n: dict) -> dict[str, str]:
    m = {}
    for key, names in i18n["label_aliases"].items():
        for n in names:
            m[n.lower()] = key
    return m


def _split_pipes(s: str) -> list[str]:
    r"""Split on unescaped '|' ; a literal pipe inside a field is written as '\|'."""
    return [p.replace("\\|", "|").strip() for p in re.split(r"\s*(?<!\\)\|\s*", s.strip())]


def _esc(s) -> str:
    return str(s).replace("|", "\\|")


def _safe_date(raw: str) -> str:
    try:
        return dates.parse_date(raw)
    except dates.DateError:
        return raw  # keep raw text; the validator reports it


def _parse_entry_head(head: str) -> dict:
    parts = _split_pipes(head)
    e = {"organization": parts[0] if parts else "", "role": "", "start": "", "end": "", "location": ""}
    rest = parts[1:]
    # the date is the LAST field that is entirely a date (range): a year inside a role/location is just text
    date_idx = next((i for i in range(len(rest) - 1, -1, -1) if dates.is_date_field(rest[i])), None)
    plain = [p for i, p in enumerate(rest) if i != date_idx]
    if plain:
        e["role"] = plain[0]
    if len(plain) > 1:
        e["location"] = plain[1]
    if date_idx is not None:
        s, en = dates.split_range(rest[date_idx])
        e["start"], e["end"] = _safe_date(s), _safe_date(en)
    return e


def _new_entry(head: dict | None = None) -> dict:
    e = head or {"organization": "", "role": "", "start": "", "end": "", "location": ""}
    e.update({"description": "", "bullets": [], "evidence": [], "confirmation_status": "user_provided"})
    return e


def parse_markdown(text: str) -> dict:
    i18n = load_i18n()
    alias = _alias_map(i18n)
    data = empty_resume()
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    if lines and lines[0].strip() == "---":
        try:
            end = lines.index("---", 1)
        except ValueError:
            end = -1
        if end > 0:
            for ln in lines[1:end]:
                if ":" in ln:
                    k, v = ln.split(":", 1)
                    k, v = k.strip().lower(), v.strip()
                    if k in FRONT_KEYS:
                        grp, field = FRONT_KEYS[k]
                        data[grp][field] = int(v) if field == "page_limit" and v.isdigit() else v
                    elif k == "section_order":
                        data.setdefault("meta", {})["section_order"] = [s.strip() for s in v.split(",") if s.strip()]
            lines = lines[end + 1:]

    section = None
    entry = None
    summary_lines: list[str] = []
    for raw in lines:
        s = raw.strip()
        if s.startswith("# ") and not data["basics"]["name"]:
            data["basics"]["name"] = s[2:].strip()
            continue
        m2 = re.match(r"^##\s+(.*)$", s)
        if m2:
            title = m2.group(1).strip()
            section = alias.get(title.lower()) or "_unknown:" + title
            entry = None
            continue
        m3 = re.match(r"^###\s+(.*)$", s)
        if m3 and section in ENTRY_SECTIONS:
            entry = _new_entry(_parse_entry_head(m3.group(1)))
            data[section].append(entry)
            continue
        if not s:
            continue
        if section is None:
            if s.startswith(">"):
                data["basics"]["headline"] = s.lstrip("> ").strip()
                continue
            bm = re.match(r"^[-*]\s+([^:：]+)[:：]\s*(.+)$", s)
            if bm:
                key = alias.get(bm.group(1).strip().lower())
                if key in ("email", "phone", "location", "website"):
                    data["basics"][key] = bm.group(2).strip()
                    continue
            summary_lines.append(s)
            continue
        cm = re.match(r"^<!--\s*(status|evidence)\s*:\s*(.*?)\s*-->$", s)
        if cm and entry is not None:
            if cm.group(1) == "status" and cm.group(2) in STATUS_VALUES:
                entry["confirmation_status"] = cm.group(2)
            elif cm.group(1) == "evidence":
                entry["evidence"].append(cm.group(2))
            continue
        bullet = re.match(r"^[-*•]\s+(.*)$", s)
        if section == "summary":
            summary_lines.append(s)
        elif section in ENTRY_SECTIONS:
            if entry is None:
                entry = _new_entry()
                data[section].append(entry)
            if bullet:
                entry["bullets"].append(bullet.group(1).strip())
            else:
                entry["description"] = (entry["description"] + " " + s).strip()
        elif section == "skills":
            item = bullet.group(1).strip() if bullet else s
            km = re.match(r"^([^:：]{1,30})[:：]\s*(.+)$", item)
            if km:
                items = [x.strip() for x in re.split(r"[,，、;；]", km.group(2)) if x.strip()]
                data["skills"].append({"category": km.group(1).strip(), "items": items})
            else:
                data["skills"].append({"category": "", "items": [x.strip() for x in re.split(r"[,，、;；]", item) if x.strip()]})
        elif section == "certificates":
            p = _split_pipes(bullet.group(1) if bullet else s)
            data["certificates"].append({"name": p[0], "issuer": p[1] if len(p) > 1 else "",
                                         "date": _safe_date(p[2]) if len(p) > 2 else ""})
        elif section == "languages":
            item = bullet.group(1) if bullet else s
            km = re.match(r"^([^:：]+)[:：]\s*(.+)$", item)
            data["languages"].append({"language": km.group(1).strip(), "level": km.group(2).strip()} if km
                                     else {"language": item.strip(), "level": ""})
        elif section == "awards":
            p = _split_pipes(bullet.group(1) if bullet else s)
            data["awards"].append({"name": p[0], "date": _safe_date(p[1]) if len(p) > 1 else "",
                                   "description": p[2] if len(p) > 2 else ""})
        elif section.startswith("_unknown:"):
            data.setdefault("meta", {}).setdefault("unknown_sections", []).append(section[9:])
    if summary_lines:
        data["basics"]["summary"] = " ".join(summary_lines).strip()
    return normalize(data)


# ------------------------------------------------------------------ writer
def display_name(d: dict, locale_rules: dict) -> str:
    b = d["basics"]
    parts = b.get("name_parts")
    if isinstance(parts, dict) and (parts.get("given") or parts.get("family")):
        g, f = parts.get("given", ""), parts.get("family", "")
        if locale_rules.get("name_order") == "family_given":
            return f"{f}{g}" if re.search(r"[一-鿿]", f + g) else f"{f} {g}".strip()
        return f"{g} {f}".strip()
    return b.get("name", "")


def entry_head(e: dict, style: str, lang: str) -> list[str]:
    head = [_esc(e.get("organization", ""))]
    if e.get("role"):
        head.append(_esc(e["role"]))
    rng = dates.format_range(e.get("start", ""), e.get("end", ""), style, lang)
    if rng:
        head.append(rng)
    if e.get("location"):
        head.append(_esc(e["location"]))
    return head


def _tail(bits: list[str]) -> list[str]:
    while bits and not bits[-1]:
        bits.pop()
    return bits


def _section_md(d: dict, key: str, style: str, lang: str) -> list[str]:
    if key == "summary":
        return [d["basics"]["summary"]] if d["basics"].get("summary") else []
    if key in ENTRY_SECTIONS:
        out = []
        for e in d[key]:
            out.append("### " + " | ".join(entry_head(e, style, lang)))
            if e.get("description"):
                out.append(e["description"])
            out += [f"- {bullet_text(x)}" for x in e.get("bullets", [])]
            for ev in e.get("evidence", []):
                out.append(f"<!-- evidence: {ev} -->")
            if e.get("confirmation_status") and e["confirmation_status"] != "user_provided":
                out.append(f"<!-- status: {e['confirmation_status']} -->")
            out.append("")
        while out and out[-1] == "":
            out.pop()
        return out
    if key == "skills":
        out = []
        for s in d["skills"]:
            if isinstance(s, dict):
                items = ", ".join(s.get("items", []))
                out.append(f"- {s['category']}: {items}" if s.get("category") else f"- {items}")
            else:
                out.append(f"- {s}")
        return out
    if key == "certificates":
        return ["- " + " | ".join(_tail([_esc(c.get("name", "")), _esc(c.get("issuer", "")),
                                         dates.format_date(c.get("date", ""), style, lang)]))
                if isinstance(c, dict) else f"- {c}" for c in d["certificates"]]
    if key == "languages":
        return [(f"- {x['language']}: {x['level']}" if x.get("level") else f"- {x['language']}")
                if isinstance(x, dict) else f"- {x}" for x in d["languages"]]
    if key == "awards":
        return ["- " + " | ".join(_tail([_esc(a.get("name", "")), dates.format_date(a.get("date", ""), style, lang),
                                         _esc(a.get("description", ""))]))
                if isinstance(a, dict) else f"- {a}" for a in d["awards"]]
    return []


def to_markdown(data: dict, lang: str, locale_rules: dict, section_order: list[str],
                labels: dict, front: dict | None = None) -> str:
    d = normalize(data)
    style = locale_rules.get("date_style", "iso")
    out: list[str] = []
    fm = {k: v for k, v in (front or {}).items() if v not in ("", None)}
    if fm:
        out.append("---")
        out += [f"{k}: {v}" for k, v in fm.items()]
        out += ["---", ""]
    b = d["basics"]
    out.append(f"# {display_name(d, locale_rules)}")
    if b.get("headline"):
        out += ["", f"> {b['headline']}"]
    out.append("")
    for k in ("email", "phone", "location", "website"):
        if b.get(k):
            out.append(f"- {labels[k]}: {b[k]}")
    for key in section_order:
        block = _section_md(d, key, style, lang)
        if block:
            out += ["", f"## {labels[key]}", ""] + block
    return "\n".join(out).rstrip() + "\n"
