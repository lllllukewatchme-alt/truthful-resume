"""Standard-library Office Open XML (.docx) writer and reader for resumes."""
from __future__ import annotations

import datetime as _dt
import io
import re
import zipfile
from xml.etree import ElementTree as ET

from . import dates
from .mdio import display_name, entry_head
from .model import ENTRY_SECTIONS, PLACEHOLDER_RE, bullet_text, normalize

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")
PAPER = {"A4": (11906, 16838), "Letter": (12240, 15840)}


def _x(text: str) -> str:
    """XML-escape text (own implementation: xml.sax.saxutils would import urllib/ssl)."""
    return _CTRL.sub("", str(text)).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _tw(mm: float) -> int:
    return int(round(mm * 56.693))


def _tint(hex_color: str, amount: float = 0.9) -> str:
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    mix = lambda c: int(c + (255 - c) * amount)
    return f"{mix(r):02X}{mix(g):02X}{mix(b):02X}"


class _Ctx:
    def __init__(self, style: dict, labels: dict, rules: dict, lang: str):
        self.s, self.labels, self.rules, self.lang = style, labels, rules, lang
        self.f = style["fonts"]
        self.c = style["colors"]
        self.layout = style.get("layout", {})
        self.entry_style = self.layout.get("entry_style", "default")
        self.pw = self.ml = self.mr = 0   # page geometry in twips, set by build_docx
        self.sp = style["spacing"]
        self.pag = style.get("pagination", {})
        self.date_style = rules.get("date_style", "iso")


# ----------------------------------------------------------------- runs
def _run(text: str, *, bold=False, italic=False, color=None, size=None, caps=False, highlight=False) -> str:
    pr = ""
    if bold:
        pr += "<w:b/><w:bCs/>"
    if italic:
        pr += "<w:i/><w:iCs/>"
    if caps:
        pr += "<w:caps/>"
    if color:
        pr += f'<w:color w:val="{color}"/>'
    if size:
        pr += f'<w:sz w:val="{int(size * 2)}"/><w:szCs w:val="{int(size * 2)}"/>'
    if highlight:
        pr += '<w:highlight w:val="yellow"/>'
    rpr = f"<w:rPr>{pr}</w:rPr>" if pr else ""
    return f'<w:r>{rpr}<w:t xml:space="preserve">{_x(text)}</w:t></w:r>'


def _runs(text: str, **kw) -> str:
    """Split text on placeholders so they are highlighted visibly."""
    out, pos = [], 0
    for m in PLACEHOLDER_RE.finditer(text):
        if m.start() > pos:
            out.append(_run(text[pos:m.start()], **kw))
        out.append(_run(m.group(0), **{**kw, "highlight": True}))
        pos = m.end()
    if pos < len(text):
        out.append(_run(text[pos:], **kw))
    return "".join(out)


def _tab() -> str:
    return "<w:r><w:tab/></w:r>"


def _p(content: str, style: str | None = None, *, jc=None, keep_next=False, tabs=None,
       before=None, after=None, ind_left=None, ind_hanging=None, bdr=None) -> str:
    pr = ""
    if style:
        pr += f'<w:pStyle w:val="{style}"/>'
    if keep_next:
        pr += "<w:keepNext/>"
    if bdr:
        pr += bdr
    if tabs:
        pr += "<w:tabs>" + "".join(f'<w:tab w:val="{v}" w:pos="{pos}"/>' for v, pos in tabs) + "</w:tabs>"
    if before is not None or after is not None:
        a = ""
        if before is not None:
            a += f' w:before="{int(before * 20)}"'
        if after is not None:
            a += f' w:after="{int(after * 20)}"'
        pr += f"<w:spacing{a}/>"
    if ind_left is not None:
        hang = f' w:hanging="{ind_hanging}"' if ind_hanging else ""
        pr += f'<w:ind w:left="{ind_left}"{hang}/>'
    if jc:
        pr += f'<w:jc w:val="{jc}"/>'
    return f"<w:p><w:pPr>{pr}</w:pPr>{content}</w:p>"


# ----------------------------------------------------------------- blocks
def _heading(ctx: _Ctx, text: str) -> str:
    h = ctx.s.get("heading", {})
    return _p(_run(h.get("prefix", "") + text), "Heading1", jc="center" if h.get("align") == "center" else None)


def _entry_block(ctx: _Ctx, e: dict, width: int, max_bullets: int) -> list[str]:
    out = []
    rng = dates.format_range(e.get("start", ""), e.get("end", ""), ctx.date_style, ctx.lang)
    org = _runs(e.get("organization", ""), bold=True)
    bullet_ind = _tw(ctx.s["bullets"]["indent_mm"])
    kind = ctx.entry_style
    base, hang_title, bdr = 0, None, None
    sub = " · ".join(x for x in (e.get("role", ""), e.get("location", "")) if x)
    has_body = bool(e.get("description") or e.get("bullets"))
    if kind == "date_left":
        col = _tw(ctx.layout.get("date_col_mm", 34))
        title = _runs(rng, color=ctx.c["muted"]) + _tab() + org
        out.append(_p(title, "Heading2", tabs=[("left", col)], keep_next=True, ind_left=col, ind_hanging=col))
        base = col
    elif kind == "timeline":
        base = 300
        bdr = f'<w:pBdr><w:left w:val="single" w:sz="18" w:space="10" w:color="{ctx.c["accent"]}"/></w:pBdr>'
        title = org + (_tab() + _runs(rng, color=ctx.c["muted"]) if rng else "")
        out.append(_p(title, "Heading2", tabs=[("right", width)] if rng else None, keep_next=True, ind_left=base, bdr=bdr))
    else:
        title = org
        if rng:
            title += _tab() + _runs(rng, color=ctx.c["muted"])
            out.append(_p(title, "Heading2", tabs=[("right", width)], keep_next=True))
        else:
            out.append(_p(title, "Heading2", keep_next=True))
    ind = base if base else None
    if sub:
        out.append(_p(_runs(sub, italic=True, color=ctx.c["muted"]), "EntrySub", keep_next=has_body, ind_left=ind, bdr=bdr))
    if e.get("description"):
        out.append(_p(_runs(e["description"]), "BodyText", ind_left=ind, bdr=bdr))
    bullets = e.get("bullets", [])
    if max_bullets and ctx.s.get("_enforce_max_bullets"):
        bullets = bullets[:max_bullets]
    for b in bullets:
        if base:
            out.append(_p(_runs(bullet_text(b)), "ListBullet", ind_left=base + bullet_ind, ind_hanging=bullet_ind, bdr=bdr))
        else:
            out.append(_p(_runs(bullet_text(b)), "ListBullet"))
    return out


def _skills_block(ctx: _Ctx, d: dict, stacked: bool) -> list[str]:
    out = []
    for s in d["skills"]:
        if isinstance(s, dict):
            items = ", ".join(s.get("items", []))
            cat = s.get("category", "")
            if stacked and cat:
                out.append(_p(_runs(cat, bold=True), "BodyText", keep_next=True, after=0))
                out.append(_p(_runs(items), "BodyText"))
            else:
                out.append(_p((_runs(cat + ": ", bold=True) if cat else "") + _runs(items), "BodyText"))
        else:
            out.append(_p(_runs(str(s)), "BodyText"))
    return out


def _simple_list(ctx: _Ctx, key: str, d: dict, stacked: bool = False) -> list[str]:
    out = []
    for x in d[key]:
        if key == "certificates":
            if isinstance(x, dict):
                t = _runs(x.get("name", ""), bold=True)
                meta = " · ".join(v for v in (x.get("issuer", ""),
                                              dates.format_date(x.get("date", ""), ctx.date_style, ctx.lang)) if v)
                if meta and stacked:      # narrow sidebar: name on one line, issuer · date on the next
                    out.append(_p(t, "BodyText", after=0))
                    out.append(_p(_runs(meta, color=ctx.c["muted"]), "BodyText"))
                    continue
                if meta:
                    t += _runs("  " + meta, color=ctx.c["muted"])
            else:
                t = _runs(str(x))
        elif key == "languages":
            t = (_runs(x.get("language", ""), bold=True) + (_runs(": " + x["level"]) if x.get("level") else "")) \
                if isinstance(x, dict) else _runs(str(x))
        else:  # awards
            if isinstance(x, dict):
                t = _runs(x.get("name", ""), bold=True)
                meta = " · ".join(v for v in (dates.format_date(x.get("date", ""), ctx.date_style, ctx.lang),
                                              x.get("description", "")) if v)
                if meta and stacked:
                    out.append(_p(t, "BodyText", after=0))
                    out.append(_p(_runs(meta, color=ctx.c["muted"]), "BodyText"))
                    continue
                if meta:
                    t += _runs("  " + meta, color=ctx.c["muted"])
            else:
                t = _runs(str(x))
        out.append(_p(t, "BodyText"))
    return out


def _section(ctx: _Ctx, d: dict, key: str, width: int, stacked: bool, max_bullets: int) -> list[str]:
    body: list[str] = []
    if key == "summary":
        if d["basics"].get("summary"):
            body = [_p(_runs(d["basics"]["summary"]), "BodyText")]
    elif key in ENTRY_SECTIONS:
        for e in d[key]:
            body += _entry_block(ctx, e, width, max_bullets)
    elif key == "skills":
        body = _skills_block(ctx, d, stacked)
    elif key in ("certificates", "languages", "awards"):
        body = _simple_list(ctx, key, d, stacked)
    if not body:
        return []
    return [_heading(ctx, ctx.labels[key])] + body


def _contact_items(ctx: _Ctx, d: dict) -> list[str]:
    b = d["basics"]
    return [b[k] for k in ("phone", "email", "location", "website") if b.get(k)]


def _header_block(ctx: _Ctx, d: dict, rules: dict, with_contact: bool = True) -> list[str]:
    hdr = ctx.s.get("header", {})
    band = hdr.get("style") == "band"
    jc = {"center": "center", "left": "left"}.get(hdr.get("align", "left"), "left")
    tc = hdr.get("band_text", "FFFFFF") if band else None
    paras = [_p(_runs(display_name(d, rules), color=tc), "Title", jc=jc)]
    if d["basics"].get("headline"):
        paras.append(_p(_runs(d["basics"]["headline"], color=tc or ctx.c["muted"]), "Contact", jc=jc))
    items = _contact_items(ctx, d) if with_contact else []
    if items:
        if hdr.get("contact_layout") == "stacked":
            paras += [_p(_runs(i, color=tc), "Contact", jc=jc) for i in items]
        else:
            paras.append(_p(_runs("  |  ".join(items), color=tc), "Contact", jc=jc))
    if not band:
        return paras
    # banner: one full-width cell bleeding to the page edges; text stays aligned with the body margins.
    # (The package has no compat settings, so Word measures tblInd to the cell TEXT: indent 0 + left cell margin = page edge.)
    fill = hdr.get("band_color", ctx.c["accent"])
    mar = (f'<w:tcMar><w:top w:w="200" w:type="dxa"/><w:left w:w="{ctx.ml}" w:type="dxa"/>'
           f'<w:bottom w:w="200" w:type="dxa"/><w:right w:w="{ctx.mr}" w:type="dxa"/></w:tcMar>')
    cell = (f'<w:tc><w:tcPr><w:tcW w:w="{ctx.pw}" w:type="dxa"/><w:shd w:val="clear" w:color="auto" w:fill="{fill}"/>{mar}</w:tcPr>'
            f'{_no_keep_next("".join(paras))}</w:tc>')
    tbl = (f'<w:tbl><w:tblPr><w:tblW w:w="{ctx.pw}" w:type="dxa"/><w:tblInd w:w="0" w:type="dxa"/><w:tblLayout w:type="fixed"/>'
           f'<w:tblCellMar><w:left w:w="0" w:type="dxa"/><w:right w:w="0" w:type="dxa"/></w:tblCellMar></w:tblPr>'
           f'<w:tblGrid><w:gridCol w:w="{ctx.pw}"/></w:tblGrid><w:tr>{cell}</w:tr></w:tbl>')
    return [tbl, _p("", "BodyText", after=2)]


def _recolor(xml: str, text_color: str, head_color: str) -> str:
    """Re-colour every run in a block of paragraphs (dark sidebar): headings get head_color, the rest text_color.
    The colour element is inserted in schema order (before sz/szCs/highlight) to keep the document strictly valid."""
    def run_pr(col):
        def fix(m):
            inner = re.sub(r'<w:color w:val="\w+"/>', "", m.group(1))
            cut = re.search(r"<w:(sz|szCs|highlight)\b", inner)
            at = cut.start() if cut else len(inner)
            return f'<w:rPr>{inner[:at]}<w:color w:val="{col}"/>{inner[at:]}</w:rPr>'
        return fix

    def para(m):
        p = m.group(0)
        col = head_color if 'w:pStyle w:val="Heading1"' in p else text_color
        p = re.sub(r"<w:rPr>(.*?)</w:rPr>", run_pr(col), p)
        return re.sub(r"<w:r>(?!<w:rPr>)", f'<w:r><w:rPr><w:color w:val="{col}"/></w:rPr>', p)
    return re.sub(r"<w:p>.*?</w:p>", para, xml, flags=re.S)


def _no_keep_next(xml: str) -> str:
    """Switch keep-with-next off for paragraphs inside a table cell. Word moves a whole table row to the next page when
    keepNext chains run through its cells, which left page 1 empty for long two-column resumes (audit F4)."""
    xml = xml.replace("<w:keepNext/>", "")
    return re.sub(r'(<w:pStyle w:val="\w+"/>)', r'\1<w:keepNext w:val="0"/>', xml)


def _table(left_w: int, right_w: int, left: list[str], right: list[str], left_fill: str | None,
           right_fill: str | None) -> str:
    def cell(w, content, fill):
        shd = f'<w:shd w:val="clear" w:color="auto" w:fill="{fill}"/>' if fill else ""
        mar = '<w:tcMar><w:top w:w="80" w:type="dxa"/><w:left w:w="140" w:type="dxa"/><w:bottom w:w="80" w:type="dxa"/><w:right w:w="140" w:type="dxa"/></w:tcMar>'
        body = _no_keep_next("".join(content)) or "<w:p/>"
        return f'<w:tc><w:tcPr><w:tcW w:w="{w}" w:type="dxa"/>{shd}{mar}</w:tcPr>{body}</w:tc>'
    grid = f'<w:tblGrid><w:gridCol w:w="{left_w}"/><w:gridCol w:w="{right_w}"/></w:tblGrid>'
    pr = (f'<w:tblPr><w:tblW w:w="{left_w + right_w}" w:type="dxa"/><w:tblLayout w:type="fixed"/>'
          '<w:tblCellMar><w:left w:w="0" w:type="dxa"/><w:right w:w="0" w:type="dxa"/></w:tblCellMar></w:tblPr>')
    return f"<w:tbl>{pr}{grid}<w:tr>{cell(left_w, left, left_fill)}{cell(right_w, right, right_fill)}</w:tr></w:tbl>"


# ----------------------------------------------------------------- parts
def _styles_xml(ctx: _Ctx) -> str:
    f, c, sp = ctx.f, ctx.c, ctx.sp
    line = int(sp["line_multiple"] * 240)
    body = int(f["body_pt"] * 2)
    cs = f'<w:spacing w:val="{int(sp.get("char_spacing_pt", 0) * 20)}"/>' if sp.get("char_spacing_pt") else ""
    hstyle = ctx.s.get("heading", {}).get("style", "rule")
    caps = "<w:caps/>" if ctx.s.get("heading", {}).get("caps") else ""
    border = f'<w:pBdr><w:bottom w:val="single" w:sz="6" w:space="1" w:color="{c["accent"]}"/></w:pBdr>'
    shade = f'<w:shd w:val="clear" w:color="auto" w:fill="{_tint(c["accent"], 0.88)}"/>'
    bar = f'<w:pBdr><w:left w:val="single" w:sz="36" w:space="8" w:color="{c["accent"]}"/></w:pBdr>'
    h1_ppr = {"rule": border, "caps_rule": border, "band": shade, "plain": "", "left_bar": bar}.get(hstyle, border)
    h1_ind = '<w:ind w:left="220"/>' if hstyle == "left_bar" else ""
    h1_color = c["heading"]
    wc = "<w:widowControl/>" if ctx.pag.get("widow_control", True) else ""
    kn = "<w:keepNext/>"
    lang_east = "zh-CN" if ctx.lang.startswith("zh") else "ja-JP" if ctx.lang == "ja" else "zh-CN"
    lang_val = "zh-CN" if ctx.lang.startswith("zh") else "en-US"
    bullet_ind = _tw(ctx.s["bullets"]["indent_mm"])

    def st(sid, name, ppr="", rpr="", based="Normal", nxt=None, ui=None, q=True):
        b = f'<w:basedOn w:val="{based}"/>' if based else ""
        n = f'<w:next w:val="{nxt}"/>' if nxt else ""
        return (f'<w:style w:type="paragraph" w:styleId="{sid}"><w:name w:val="{name}"/>{b}{n}'
                f'{"<w:qFormat/>" if q else ""}<w:pPr>{ppr}</w:pPr><w:rPr>{rpr}</w:rPr></w:style>')

    ppr_h1 = (f'{kn}{h1_ppr}<w:spacing w:before="{int(sp["section_before_pt"] * 20)}" '
              f'w:after="{int(sp["section_after_pt"] * 20)}"/>{h1_ind}<w:outlineLvl w:val="0"/>')
    h1_rpr = f'<w:b/><w:bCs/>{caps}<w:color w:val="{h1_color}"/><w:sz w:val="{int(f["heading_pt"] * 2)}"/><w:szCs w:val="{int(f["heading_pt"] * 2)}"/>'
    styles = [
        f'<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="{f["latin"]}" w:hAnsi="{f["latin"]}" '
        f'w:eastAsia="{f["east_asian"]}" w:cs="{f["latin"]}"/><w:sz w:val="{body}"/><w:szCs w:val="{body}"/>'
        f'<w:lang w:val="{lang_val}" w:eastAsia="{lang_east}"/></w:rPr></w:rPrDefault>'
        f'<w:pPrDefault><w:pPr><w:spacing w:after="{int(sp["para_after_pt"] * 20)}" w:line="{line}" w:lineRule="auto"/>'
        f'</w:pPr></w:pPrDefault></w:docDefaults>',
        f'<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/>'
        f'<w:pPr>{wc}</w:pPr><w:rPr><w:rFonts w:ascii="{f["latin"]}" w:hAnsi="{f["latin"]}" w:eastAsia="{f["east_asian"]}" w:cs="{f["latin"]}"/>'
        f'<w:color w:val="{c["text"]}"/>{cs}</w:rPr></w:style>',
        st("Title", "Title", f'<w:spacing w:before="0" w:after="{int(sp["para_after_pt"] * 20 + 40)}"/>',
           f'<w:b/><w:bCs/><w:color w:val="{c["heading"]}"/><w:sz w:val="{int(f["name_pt"] * 2)}"/><w:szCs w:val="{int(f["name_pt"] * 2)}"/>'),
        st("Contact", "Contact", f'<w:spacing w:after="{int(sp["para_after_pt"] * 20)}"/>',
           f'<w:sz w:val="{int(f["contact_pt"] * 2)}"/><w:szCs w:val="{int(f["contact_pt"] * 2)}"/>'),
        st("Heading1", "heading 1", ppr_h1, h1_rpr, nxt="BodyText"),
        st("Heading2", "heading 2", f'{kn}<w:spacing w:before="{int(sp["entry_before_pt"] * 20)}" w:after="0"/><w:outlineLvl w:val="1"/>',
           f'<w:sz w:val="{int(f["entry_pt"] * 2)}"/><w:szCs w:val="{int(f["entry_pt"] * 2)}"/>', nxt="BodyText"),
        st("EntrySub", "Entry Subtitle", '<w:spacing w:after="0"/>', ""),
        st("BodyText", "Body Text", "", ""),
        st("ListBullet", "List Bullet",
           f'<w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr><w:spacing w:after="{int(sp["para_after_pt"] * 10)}"/>'
           f'<w:ind w:left="{bullet_ind + 120}" w:hanging="{bullet_ind}"/>', ""),
        st("Footer", "footer", '<w:jc w:val="center"/>',
           f'<w:color w:val="{c["muted"]}"/><w:sz w:val="16"/><w:szCs w:val="16"/>', q=False),
    ]
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles xmlns:w="{W_NS}">'
            + "".join(styles) + "</w:styles>")


def _numbering_xml(ctx: _Ctx) -> str:
    ind = _tw(ctx.s["bullets"]["indent_mm"])
    ch = _x(ctx.s["bullets"]["char"])
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:numbering xmlns:w="{W_NS}">'
            '<w:abstractNum w:abstractNumId="0"><w:multiLevelType w:val="hybridMultilevel"/>'
            f'<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="{ch}"/>'
            f'<w:lvlJc w:val="left"/><w:pPr><w:ind w:left="{ind + 120}" w:hanging="{ind}"/></w:pPr>'
            f'<w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial" w:hint="default"/>'
            f'<w:color w:val="{ctx.c["accent"]}"/></w:rPr></w:lvl></w:abstractNum>'
            '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num></w:numbering>')


def _footer_xml(ctx: _Ctx) -> str:
    def fld(instr):
        return (f'<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText xml:space="preserve"> {instr} </w:instrText></w:r>'
                '<w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>1</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r>')
    txt = ctx.s.get("header_footer", {}).get("footer_text", "")
    content = (_run(txt + "  ") if txt else "") + fld("PAGE") + _run(" / ") + fld("NUMPAGES")
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:ftr xmlns:w="{W_NS}">'
            f'{_p(content, "Footer")}</w:ftr>')


CT = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
      '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
      '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
      '<Default Extension="xml" ContentType="application/xml"/>'
      '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
      '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
      '<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>'
      '<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>'
      '<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
      '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
      '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
      '</Types>')
RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
        '</Relationships>')
DOC_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>'
            '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>'
            '<Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>'
            '</Relationships>')
SETTINGS = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:settings xmlns:w="{W_NS}">'
            '<w:defaultTabStop w:val="720"/><w:characterSpacingControl w:val="doNotCompress"/>'
            '<w:themeFontLang w:val="en-US" w:eastAsia="zh-CN"/></w:settings>')


def _core_xml(clean: bool) -> str:
    ts = ""
    if not clean:
        now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        ts = (f'<dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>'
              f'<dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>')
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            '<dc:title>Resume</dc:title><dc:creator></dc:creator><cp:lastModifiedBy></cp:lastModifiedBy>'
            f'{ts}</cp:coreProperties>')


APP = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
       '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
       '<Application>resume-design</Application><Company></Company></Properties>')


def build_docx(data: dict, style: dict, labels: dict, rules: dict, section_order: list[str],
               lang: str, clean_metadata: bool = False, max_bullets: int = 0,
               paper: str | None = None) -> bytes:
    d = normalize(data)
    ctx = _Ctx(style, labels, rules, lang)
    if max_bullets:
        ctx.s = {**style, "_enforce_max_bullets": True}
    paper = paper or rules.get("paper") or style["page"].get("size", "A4")
    pw, ph = PAPER.get(paper, PAPER["A4"])
    m = style["page"]["margins_mm"]
    ml, mr, mt, mb = _tw(m["left"]), _tw(m["right"]), _tw(m["top"]), _tw(m["bottom"])
    width = pw - ml - mr
    ctx.pw, ctx.ml, ctx.mr = pw, ml, mr

    layout = style.get("layout", {})
    sidebar_contact = layout.get("columns", 1) == 2 and layout.get("sidebar_contact", False)
    body = _header_block(ctx, d, rules, with_contact=not sidebar_contact)
    if layout.get("columns", 1) == 2:
        side_keys = [k for k in section_order if k in layout.get("sidebar_sections", [])]
        main_keys = [k for k in section_order if k not in side_keys]
        side_w = int(width * layout.get("sidebar_width_pct", 30) / 100)
        main_w = width - side_w
        side, main = [], []
        if sidebar_contact:
            side += [_heading(ctx, labels.get("contact", "Contact"))] + [_p(_runs(i), "BodyText") for i in _contact_items(ctx, d)]
        for k in side_keys:
            side += _section(ctx, d, k, side_w - 280, True, max_bullets)
        for k in main_keys:
            main += _section(ctx, d, k, main_w - 280, False, max_bullets)
        fill = layout.get("sidebar_fill") or _tint(ctx.c["accent"], 0.93)
        if layout.get("sidebar_text"):
            side = [_recolor("".join(side), layout["sidebar_text"], layout.get("sidebar_heading", layout["sidebar_text"]))]
        if layout.get("sidebar_side", "left") == "left":
            body.append(_table(side_w, main_w, side, main, fill, None))
        else:
            body.append(_table(main_w, side_w, main, side, None, fill))
        body.append(_p("", "BodyText"))
    else:
        for k in section_order:
            body += _section(ctx, d, k, width, False, max_bullets)

    footer_ref = ""
    if style.get("header_footer", {}).get("page_numbers"):
        footer_ref = '<w:footerReference w:type="default" r:id="rId4"/>'
    sect = (f'<w:sectPr>{footer_ref}<w:pgSz w:w="{pw}" w:h="{ph}"/>'
            f'<w:pgMar w:top="{mt}" w:right="{mr}" w:bottom="{mb}" w:left="{ml}" w:header="400" w:footer="400" w:gutter="0"/></w:sectPr>')
    document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<w:document xmlns:w="{W_NS}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                f'<w:body>{"".join(body)}{sect}</w:body></w:document>')

    ct = CT
    doc_rels = DOC_RELS
    parts = {
        "[Content_Types].xml": ct, "_rels/.rels": RELS, "word/document.xml": document,
        "word/_rels/document.xml.rels": doc_rels, "word/styles.xml": _styles_xml(ctx),
        "word/numbering.xml": _numbering_xml(ctx), "word/settings.xml": SETTINGS,
        "docProps/core.xml": _core_xml(clean_metadata), "docProps/app.xml": APP,
    }
    if footer_ref:
        parts["word/footer1.xml"] = _footer_xml(ctx)
    else:
        parts["[Content_Types].xml"] = ct.replace(
            '<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>', "")
        parts["word/_rels/document.xml.rels"] = doc_rels.replace(
            '<Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>', "")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        # [Content_Types].xml must be first for strict consumers
        for name in ["[Content_Types].xml"] + [n for n in parts if n != "[Content_Types].xml"]:
            z.writestr(name, parts[name])
    return buf.getvalue()


# ----------------------------------------------------------------- reader / inspector
def inspect_docx(path) -> dict:
    """Return structural facts and text of a docx. Raises zipfile.BadZipFile/KeyError/ET.ParseError."""
    with zipfile.ZipFile(path) as z:
        bad = z.testzip()
        names = set(z.namelist())
        if bad:
            raise zipfile.BadZipFile(f"corrupt member {bad}")
        for req in ("[Content_Types].xml", "word/document.xml", "_rels/.rels"):
            if req not in names:
                raise KeyError(f"missing {req}")
        for n in names:
            if n.endswith(".xml") or n.endswith(".rels"):
                ET.fromstring(z.read(n))  # well-formedness of every part
        root = ET.fromstring(z.read("word/document.xml"))
        core = z.read("docProps/core.xml").decode("utf-8") if "docProps/core.xml" in names else ""
    ns = {"w": W_NS}
    q = lambda t: f"{{{W_NS}}}{t}"
    paras, heading1, heading2, bullets = [], 0, 0, 0
    for p in root.iter(q("p")):
        text = ""
        for node in p.iter():
            if node.tag == q("t"):
                text += node.text or ""
            elif node.tag == q("tab"):
                text += "\t"
        st = p.find("w:pPr/w:pStyle", ns)
        sid = st.get(q("val")) if st is not None else ""
        heading1 += sid == "Heading1"
        heading2 += sid == "Heading2"
        bullets += sid == "ListBullet"
        paras.append({"style": sid, "text": text})
    m = re.search(r"<dc:creator>(.*?)</dc:creator>", core)
    return {
        "paragraphs": paras,
        "text": "\n".join(p["text"] for p in paras),
        "heading1": heading1, "heading2": heading2, "bullets": bullets,
        "tables": len(list(root.iter(q("tbl")))),
        "has_styles": "word/styles.xml" in names, "has_numbering": "word/numbering.xml" in names,
        "creator": m.group(1) if m else None,
    }
