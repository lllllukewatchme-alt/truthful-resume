"""Date parsing/formatting. Stored form: 'YYYY', 'YYYY-MM' or 'present'."""
from __future__ import annotations

import datetime as _dt
import re

PRESENT_WORDS = {"present", "current", "now", "ongoing", "至今", "现在", "目前", "今", "迄今"}
_RANGE_SEP = re.compile(r"\s*(?:–|—|-|~|至|to)\s*", re.I)
_DATE = re.compile(r"^(\d{4})(?:\s*[-./年]\s*(\d{1,2})\s*月?)?$")
_EN_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_EN_PARSE = {m.lower(): i + 1 for i, m in enumerate(_EN_MONTHS)}


class DateError(ValueError):
    pass


def parse_date(text: str) -> str:
    """Normalise a single date to 'YYYY', 'YYYY-MM' or 'present'. Raises DateError."""
    t = str(text or "").strip()
    if not t:
        return ""
    if t.lower() in PRESENT_WORDS:
        return "present"
    m = re.match(r"^([A-Za-z]{3,9})\.?\s+(\d{4})$", t)
    if m and m.group(1)[:3].lower() in _EN_PARSE:
        return f"{m.group(2)}-{_EN_PARSE[m.group(1)[:3].lower()]:02d}"
    m = _DATE.match(t)
    if not m:
        raise DateError(f"unrecognised date: {t!r}")
    year, month = int(m.group(1)), m.group(2)
    if not 1950 <= year <= _dt.date.today().year + 6:
        raise DateError(f"year out of range: {year}")
    if month is None:
        return f"{year:04d}"
    mo = int(month)
    if not 1 <= mo <= 12:
        raise DateError(f"month out of range: {mo}")
    return f"{year:04d}-{mo:02d}"


def split_range(text: str) -> tuple[str, str]:
    """Split '2019.07 – 至今' into raw start/end strings."""
    t = str(text or "").strip()
    if not t:
        return "", ""
    # Avoid splitting 'YYYY-MM' dashes: split only on separators surrounded by space or non-digit joins.
    m = re.match(r"^(.+?)\s*(?:–|—|~|至|\sto\s|\s-\s)\s*(.+)$", t, re.I)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    m = re.match(r"^(\d{4}(?:[./]\d{1,2})?)-(\d{4}(?:[./]\d{1,2})?|present|至今)$", t, re.I)
    if m:
        return m.group(1), m.group(2)
    return t, ""


def sort_key(value: str) -> tuple[int, int]:
    if value == "present":
        return (9999, 12)
    if not value:
        return (0, 0)
    parts = value.split("-")
    return (int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)


def format_date(value: str, style: str, lang: str = "zh") -> str:
    """style: iso | dot | cn | en_short ."""
    if not value:
        return ""
    if value == "present":
        return "至今" if lang.startswith("zh") else "Present"
    parts = value.split("-")
    y = parts[0]
    mo = int(parts[1]) if len(parts) > 1 else None
    if mo is None:
        return y + ("年" if style == "cn" else "")
    if style == "dot":
        return f"{y}.{mo:02d}"
    if style == "cn":
        return f"{y}年{mo}月"
    if style == "en_short":
        return f"{_EN_MONTHS[mo - 1]} {y}"
    return f"{y}-{mo:02d}"


def format_range(start: str, end: str, style: str, lang: str) -> str:
    s, e = format_date(start, style, lang), format_date(end, style, lang)
    if s and e:
        return f"{s} – {e}"
    return s or e


_MONTH_NAME = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}"
_DATE_TOKEN = rf"(?:\d{{4}}(?:\s*[-./年]\s*\d{{1,2}}\s*月?)?|{_MONTH_NAME})"
_END_TOKEN = rf"(?:{_DATE_TOKEN}|" + "|".join(sorted((re.escape(w) for w in PRESENT_WORDS), key=len, reverse=True)) + ")"
_RANGE_FIELD = re.compile(rf"^{_DATE_TOKEN}(?:(?:\s*(?:–|—|-|~|至)\s*|\s+to\s+){_END_TOKEN})?$", re.I)


def is_date_field(text: str) -> bool:
    """True only if the whole field is a date or a date range (a year inside other words is not)."""
    return bool(_RANGE_FIELD.match(str(text or "").strip()))
