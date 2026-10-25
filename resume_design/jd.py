"""Heuristic JD requirement extraction and resume keyword coverage (offline, deterministic).

This is an aid, not a verdict: 'missing_evidence' means the resume text shows no evidence, not that the
candidate lacks the skill. A human must confirm every classification (report category B).
"""
from __future__ import annotations

import re

from .model import iter_texts, normalize

_REQ_HEAD = re.compile(r"任职要求|岗位要求|职位要求|要求|资格|requirements?|qualifications?|what you|must have|skills", re.I)
_DUTY_HEAD = re.compile(r"岗位职责|工作职责|职责|responsibilit|what you.ll do|duties", re.I)
_PREFER = re.compile(r"优先|加分|preferred|nice to have|a plus|bonus", re.I)
_ASCII_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9+#./-]*[A-Za-z0-9+#]|[A-Za-z]{2}")
_STOP_EN = {"and", "or", "the", "with", "of", "to", "in", "for", "a", "an", "on", "etc", "good", "strong", "year", "years",
            "experience", "knowledge", "ability", "skills", "team", "work", "working", "plus", "preferred", "is", "are",
            "as", "be", "have", "has", "using", "use", "such", "ci", "cd"}
_CJK_SPLIT = re.compile(r"熟悉|熟练|掌握|精通|具备|具有|拥有|了解|有|经验|以上|及以上|者优先|优先|良好的|良好|优秀的|较强的|"
                        r"以及|并且|及|与|和|或|等|的|者|者优先|相关|专业|能力|精神|学历|本科|硕士|大专|开发|工作|[，,、；;。.:：()（）\s\d]+")
_BULLET = re.compile(r"^\s*(?:[-*•·]|\d+[.)、])\s*(.+)$")


def parse_jd(text: str) -> dict:
    title, reqs, duties, mode = "", [], [], None
    for raw in text.replace("\r", "").split("\n"):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            h = line.lstrip("# ").strip()
            if not title and line.startswith("# ") and not line.startswith("##"):
                title = h
                continue
            mode = "req" if _REQ_HEAD.search(h) else "duty" if _DUTY_HEAD.search(h) else None
            continue
        m = _BULLET.match(line)
        item = (m.group(1) if m else line).strip()
        if mode == "req":
            reqs.append(item)
        elif mode == "duty":
            duties.append(item)
        elif m:
            reqs.append(item)
    return {"title": title, "requirements": [_req(r) for r in reqs], "responsibilities": duties}


def _req(text: str) -> dict:
    return {"text": text, "preferred": bool(_PREFER.search(text)), "keywords": keywords(text)}


def keywords(text: str) -> list[str]:
    kws: list[str] = []
    for tok in _ASCII_TOKEN.findall(text):
        t = tok.strip("./-")
        if t.lower() not in _STOP_EN and len(t) >= 2 and t.lower() not in (k.lower() for k in kws):
            kws.append(t)
    cjk_part = re.sub(r"[A-Za-z0-9+#./-]+", " ", text)
    for chunk in _CJK_SPLIT.split(cjk_part):
        chunk = chunk.strip()
        if 2 <= len(chunk) <= 8 and re.fullmatch(r"[一-鿿]+", chunk) and chunk not in kws:
            kws.append(chunk)
    return kws


def _resume_corpus(data: dict) -> list[tuple[str, str]]:
    return [(p, t.casefold()) for p, t in iter_texts(normalize(data)) if t]


def match(data: dict, jd_text: str) -> dict:
    jd = parse_jd(jd_text)
    corpus = _resume_corpus(data)
    results = []
    all_kw, hit_kw = set(), set()
    for r in jd["requirements"]:
        found = {}
        for kw in r["keywords"]:
            k = kw.casefold()
            for path, text in corpus:
                if re.search(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])", text) if k.isascii() else k in text:
                    found.setdefault(kw, path)
                    break
        all_kw.update(r["keywords"])
        hit_kw.update(found)
        if not r["keywords"]:
            status = "needs_human"
        elif len(found) == len(r["keywords"]):
            status = "satisfied"
        elif found:
            status = "partial"
        else:
            status = "missing_evidence"
        results.append({"requirement": r["text"], "preferred": r["preferred"], "status": status,
                        "matched_keywords": found, "unmatched_keywords": [k for k in r["keywords"] if k not in found]})
    counts = {s: sum(1 for x in results if x["status"] == s) for s in ("satisfied", "partial", "missing_evidence", "needs_human")}
    return {"title": jd["title"], "counts": counts,
            "keyword_coverage": round(len(hit_kw) / len(all_kw), 3) if all_kw else None,
            "results": results,
            "note": "Heuristic only. 'missing_evidence' = no evidence in the resume text; never add skills the user "
                    "has not confirmed. Ask the user whether real experience exists before adding anything."}
