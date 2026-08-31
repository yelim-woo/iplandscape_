# -*- coding: utf-8 -*-
"""
IP Landscape 통합 PDF 보고서 빌더 (미니멀 에디토리얼 양식).
원칙: 절제된 모노톤(잉크/그레이) + 얇은 헤어라인 + 넉넉한 여백 + 정돈된 타이포. 색·밴드를 쓰지 않는다.
- 표지: 상/하 헤어라인, 좌측정렬 대형 제목, 작은 레터스페이스 라벨, 하단 메타 (전부 흑백)
- 목차: '목차' + 회색 번호 + 점선 리더 + 정확한 페이지번호(2-pass)
- 장: 큰 연회색 번호 + CHAPTER 라벨 + 제목 + 풀폭 헤어라인 (밴드 없음)
- 섹션: 굵은 제목 + 풀폭 얇은 밑줄 / 그림 우선 + <그림 N-M> 캡션
- 해석: 회색 라벨 정의리스트({l,t}) / 표: 가로선만(채움·세로선 없음) / 푸터: — N —

Usage: python _build_pdf.py <manifest.json> [출력.pdf]
"""
import sys, os, json, re
from io import BytesIO
from pathlib import Path
from _ipl_io import ensure_pkgs, korean_font_path, fmt_patent_no, trunc, clean_label

ensure_pkgs(["reportlab", "pillow"])
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_RIGHT, TA_LEFT
from reportlab.lib.utils import simpleSplit
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Image, Table,
                                TableStyle, PageBreak, HRFlowable, KeepTogether, Flowable)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PIL import Image as PILImage

# ---- 한글 폰트 ----
FONT, FONT_B = "Malgun", "Malgun-B"
fp = korean_font_path()
try:
    if fp and fp.lower().endswith(".ttf"):
        pdfmetrics.registerFont(TTFont(FONT, fp))
        b = fp.replace("malgun.ttf", "malgunbd.ttf")
        pdfmetrics.registerFont(TTFont(FONT_B, b if os.path.exists(b) else fp))
    elif fp and fp.lower().endswith(".ttc"):
        pdfmetrics.registerFont(TTFont(FONT, fp, subfontIndex=0))
        pdfmetrics.registerFont(TTFont(FONT_B, fp, subfontIndex=0))
    else:
        FONT = FONT_B = "Helvetica"
except Exception:
    FONT = FONT_B = "Helvetica"
try:
    pdfmetrics.registerFontFamily(FONT, normal=FONT, bold=FONT_B, italic=FONT, boldItalic=FONT_B)
except Exception:
    pass

# ---- 모노톤 팔레트 ----
INK = colors.HexColor("#1a1a1a")
DARK = colors.HexColor("#333333")
GREY = colors.HexColor("#737373")
FAINT = colors.HexColor("#a3a3a3")
GHOST = colors.HexColor("#e9e9e9")     # 큰 장 번호 등
LINE = colors.HexColor("#e2e2e2")      # 헤어라인
LINE_D = colors.HexColor("#c7c7c7")    # 강조 헤어라인
WHITE = colors.white

MARGIN = 2.4 * cm
TOPM = 2.2 * cm
AVAIL_W = A4[0] - 2 * MARGIN
META = {}
PAGE_CHAP = {}


def S(name, size, bold=False, **kw):
    kw.setdefault("leading", size * 1.5)
    return ParagraphStyle(name, fontName=(FONT_B if bold else FONT), fontSize=size, **kw)


ST = {
    "sec": S("sec", 12.5, bold=True, textColor=INK),
    "co": S("co", 10.8, bold=True, textColor=INK, spaceBefore=2, spaceAfter=3),
    "body": S("body", 10.2, textColor=DARK, alignment=TA_LEFT, spaceAfter=2, leading=15.5),
    "obul": S("obul", 10.2, textColor=DARK, alignment=TA_LEFT, leftIndent=12,
              firstLineIndent=-12, spaceAfter=3.5, leading=15.5),
    # 해석 불릿(라벨 없이) — 항목 간 여백을 넉넉히 줘 가독성↑
    "ibul": S("ibul", 10.2, textColor=DARK, alignment=TA_LEFT, leftIndent=13,
              firstLineIndent=-13, spaceAfter=6.5, leading=16),
    # Executive Summary 불릿 — 더 큰 행간·여백
    "exbul": S("exbul", 10.8, textColor=DARK, alignment=TA_LEFT, leftIndent=14,
               firstLineIndent=-14, spaceAfter=9, leading=18),
    "cap": S("cap", 8.8, textColor=GREY, alignment=TA_CENTER, spaceBefore=4, spaceAfter=8),
    "small": S("small", 8.8, textColor=GREY, alignment=TA_LEFT, spaceAfter=2),
    "lbl": S("lbl", 8.6, bold=True, textColor=GREY, leading=14),
    "toc_n": S("toc_n", 10, textColor=FAINT),
    "toc_t": S("toc_t", 11.5, bold=True, textColor=INK),
    "toc_p": S("toc_p", 10.5, textColor=INK, alignment=TA_RIGHT),
    "toc_d": S("toc_d", 8.8, textColor=GREY),
    "mokcha": S("mokcha", 22, bold=True, textColor=INK),
    "kicker": S("kicker", 9, textColor=GREY),
}


_ENT = re.compile(r"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)")


def esc(t):
    """reportlab Paragraph용 XML 이스케이프. 이스케이프 안 된 '&'(R&D·M&A 등)가
    reportlab에서 '&D;' 처럼 깨지는 것을 막는다. 이미 엔티티(&amp; 등)는 보존(멱등)."""
    s = "" if t is None else str(t)
    s = re.sub(r"[ 	 　]{2,}", " ", s)   # 연속 공백(탭·NBSP·전각) -> 한 칸
    s = _ENT.sub("&amp;", s)
    return s.replace("<", "&lt;").replace(">", "&gt;")


_BOLD = re.compile(r"\*\*(.+?)\*\*")
# 핵심 수치 토큰(%·금액·건수·배수·CAGR) — 중요 포인트가 눈에 띄게 자동 볼드
_STAT = re.compile(
    r"(?:US\$|\$)?\d[\d,]*(?:\.\d+)?\s?(?:%|％|배|건|개사|"
    r"억\s?달러|백만\s?달러|만\s?달러|달러|조\s?원|억\s?원|만\s?원)"
    r"|CAGR\s?\d[\d.]*\s?%?")


def rich(text):
    """본문 강조 렌더: `**강조**` 마크다운 → 볼드, 핵심 수치(%·금액·건수·배수·CAGR)는
    자동 볼드 처리해 중요 포인트가 눈에 들어오게 한다. esc는 내부에서 수행(멱등)."""
    s = "" if text is None else str(text)
    parts, last = [], 0
    for mo in _BOLD.finditer(s):
        parts.append(("n", s[last:mo.start()])); parts.append(("b", mo.group(1))); last = mo.end()
    parts.append(("n", s[last:]))
    out = []
    for kind, seg in parts:
        if kind == "b":
            out.append(f"<b>{esc(seg)}</b>")
        else:
            out.append(_STAT.sub(lambda m: f"<b>{m.group(0)}</b>", esc(seg)))
    return "".join(out)


def _supref(refs):
    if not refs:
        return ""
    nums = ",".join(str(r) for r in (refs if isinstance(refs, (list, tuple)) else [refs]))
    return f" <super><font size=6.5 color='#737373'>[{esc(nums)}]</font></super>"


def obullets(items, style="obul"):
    out = []
    for b in (items or []):
        refs = None
        if isinstance(b, dict):
            refs = b.get("refs"); b = b.get("t", "")
        if str(b).strip():
            out.append(Paragraph(f"<font color='#737373' size=7.5>■</font>&nbsp;{rich(b)}{_supref(refs)}", ST[style]))
    return out


def interp_block(items, labels=True):
    """해석 블록. labels=True면 '라벨 | 내용' 정의리스트(기업 프로파일 등),
    labels=False면 라벨을 빼고 가독성 불릿만(정량·차트 해석 — 반복 라벨 제거)."""
    items = items or []
    if items and isinstance(items[0], dict):
        if not labels:
            return obullets(items, style="ibul")
        rows = [[Paragraph(esc(it.get("l", "")), ST["lbl"]), Paragraph(rich(it.get("t", "")), ST["body"])]
                if isinstance(it, dict) else [Paragraph("", ST["lbl"]), Paragraph(rich(str(it)), ST["body"])]
                for it in items]
        t = Table(rows, colWidths=[2.1 * cm, AVAIL_W - 2.1 * cm])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                               ("LEFTPADDING", (0, 0), (0, -1), 0), ("LEFTPADDING", (1, 0), (1, -1), 6),
                               ("LINEBELOW", (0, 0), (-1, -2), 0.4, GHOST)]))
        return [t]
    return obullets(items, style="ibul" if not labels else "obul")


# ================= 표지 / 헤더·푸터 canvas =================
def _wrap_width(text, font, fs, maxw, max_lines=2):
    """text 를 폭 maxw 안에 들도록 문자 단위로 그리디 줄바꿈(한글·기호 포함 대응).
    max_lines 를 넘으면 마지막 줄을 '…' 로 마무리한다."""
    lines, i, n = [], 0, len(text)
    while i < n and len(lines) < max_lines:
        j, cur = i, ""
        while j < n and pdfmetrics.stringWidth(cur + text[j], font, fs) <= maxw:
            cur += text[j]; j += 1
        if j == i:  # 한 글자가 폭보다 넓은 극단 케이스 — 강제로 한 글자
            cur, j = text[i], i + 1
        lines.append(cur); i = j
    if i < n and lines:  # 아직 남았으면 말줄임
        last = lines[-1]
        while last and pdfmetrics.stringWidth(last + "…", font, fs) > maxw:
            last = last[:-1]
        lines[-1] = last + "…"
    return lines


def draw_cover(c, doc):
    W, H = A4
    c.saveState()
    c.setFillColor(WHITE); c.rect(0, 0, W, H, fill=1, stroke=0)
    lm, rm = MARGIN, W - MARGIN
    # 상단 헤어라인 + 레터스페이스 라벨
    c.setStrokeColor(INK); c.setLineWidth(1.1); c.line(lm, H - 2.4 * cm, rm, H - 2.4 * cm)
    c.setFillColor(GREY); c.setFont(FONT, 9.5)
    c.drawString(lm, H - 2.15 * cm, "I P   L A N D S C A P E   R E P O R T")
    c.drawRightString(rm, H - 2.15 * cm, "STRATEGIC ANALYSIS")
    # 제목 블록 (상단 1/3 지점)
    # 연구주제 라벨 — 본문폭을 넘으면 폰트 축소, 그래도 길면 최대 2줄로 줄바꿈(제목 위로 쌓아 겹침 방지)
    c.setFillColor(GREY)
    subj_label = "연구주제 · " + str(META.get("subject", "-"))
    sfs = 11.0
    while sfs > 8.5 and pdfmetrics.stringWidth(subj_label, FONT, sfs) > AVAIL_W:
        sfs -= 0.5
    subj_base = H * 0.60 + 1.0 * cm
    if pdfmetrics.stringWidth(subj_label, FONT, sfs) <= AVAIL_W:
        c.setFont(FONT, sfs)
        c.drawString(lm, subj_base, subj_label)
    else:
        sfs = 9.5
        slines = _wrap_width(subj_label, FONT, sfs, AVAIL_W, max_lines=2)
        c.setFont(FONT, sfs)
        lh = sfs * 1.32
        for k, ln in enumerate(slines):
            c.drawString(lm, subj_base + (len(slines) - 1 - k) * lh, ln)
    c.setFillColor(INK)
    title = META.get("title", "IP 랜드스케이프 분석 보고서")
    # 제목은 항상 한 줄 — 본문폭에 맞게 폰트를 자동 축소(줄바꿈 방지)
    fs = 29.0
    while fs > 15 and pdfmetrics.stringWidth(title, FONT_B, fs) > AVAIL_W:
        fs -= 0.5
    c.setFont(FONT_B, fs)
    y = H * 0.60
    c.drawString(lm, y, title)
    # 제목 아래 짧은 헤어라인
    c.setStrokeColor(INK); c.setLineWidth(1.2); c.line(lm, y - 0.55 * cm, lm + 3.2 * cm, y - 0.55 * cm)
    c.setFillColor(GREY); c.setFont(FONT, 11.5)
    c.drawString(lm, y - 1.25 * cm, "Strategic IP Landscape Analysis")
    # 하단 메타
    c.setStrokeColor(LINE_D); c.setLineWidth(0.8); c.line(lm, 3.0 * cm, rm, 3.0 * cm)
    c.setFillColor(GREY); c.setFont(FONT, 10)
    parts = []
    if META.get("author"): parts.append("작성  " + str(META["author"]))
    if META.get("date"): parts.append("작성일  " + str(META["date"]))
    if parts:
        c.drawString(lm, 2.35 * cm, "      |      ".join(parts))
    if META.get("source"):
        c.drawString(lm, 1.85 * cm, "분석대상  " + str(META["source"]))
    c.restoreState()


def draw_chrome(c, doc):
    W, H = A4
    c.saveState()
    # 러닝 헤더 (얇은 라인 + 양끝 작은 회색 텍스트)
    c.setFont(FONT, 7.8); c.setFillColor(FAINT)
    c.drawString(MARGIN, H - 1.35 * cm, META.get("title", "")[:48])
    c.drawRightString(W - MARGIN, H - 1.35 * cm, PAGE_CHAP.get(doc.page, ""))
    c.setStrokeColor(LINE); c.setLineWidth(0.6); c.line(MARGIN, H - 1.5 * cm, W - MARGIN, H - 1.5 * cm)
    # 푸터 — N —
    c.setFont(FONT, 9); c.setFillColor(GREY)
    c.drawCentredString(W / 2, 1.2 * cm, f"—  {doc.page}  —")
    c.restoreState()


# ================= 장 마커 / 섹션 =================
class ChapAnchor(Flowable):
    """페이지번호/장명 캡처용 0높이 앵커."""
    def __init__(self, title, capture=True):
        super().__init__()
        self.title = title; self.capture = capture; self.width = 0; self.height = 0

    def wrap(self, aw, ah):
        return (0, 0)

    def draw(self):
        pass


def chapter(num, title):
    els = [ChapAnchor(title), Spacer(1, 0.3 * cm)]
    if num:
        numP = Paragraph(f"{int(num):02d}", S("cn", 40, bold=True, textColor=GHOST, leading=40))
        right = [Paragraph("C H A P T E R", S("cl", 9, textColor=GREY, leading=12)),
                 Spacer(1, 2), Paragraph(title, S("ct", 19, bold=True, textColor=INK, leading=23))]
        t = Table([[numP, right]], colWidths=[2.4 * cm, AVAIL_W - 2.4 * cm])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (0, 0), "MIDDLE"), ("VALIGN", (1, 0), (1, 0), "MIDDLE"),
                               ("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
        els.append(t)
    else:
        els.append(Paragraph(title, S("ct0", 19, bold=True, textColor=INK, leading=23)))
    els += [Spacer(1, 6), HRFlowable(width="100%", thickness=1.1, color=INK, spaceAfter=14)]
    return els


def sec_heading(text):
    t = Table([[Paragraph(esc(text), ST["sec"])]], colWidths=[AVAIL_W])
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.7, LINE_D),
                           ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                           ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    return t


def band_heading(label, tag=""):
    """카드형 섹션 헤더 — 연회색 밴드 + 굵은 라벨 + (우)영문 태그 + 하단 잉크 룰."""
    cells = [[Paragraph(esc(label), S("bh", 11.5, bold=True, textColor=INK)),
              Paragraph(esc(tag), S("bt", 8.0, textColor=FAINT, alignment=TA_RIGHT))]]
    t = Table(cells, colWidths=[AVAIL_W * 0.72, AVAIL_W * 0.28])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f0f0f0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (0, 0), 10), ("RIGHTPADDING", (-1, 0), (-1, 0), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -1), 1.1, INK)]))
    return t


def panel_body(items):
    """헤더 밴드 아래 본문 — 좌측 액센트 룰 + 패딩된 불릿(카드 느낌)."""
    t = Table([[obullets(items, style="ibul")]], colWidths=[AVAIL_W])
    t.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 13), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBEFORE", (0, 0), (-1, -1), 2.2, LINE_D)]))
    return t


def img_flow(path, max_w=AVAIL_W, max_h=13 * cm):
    if not path or not os.path.exists(path):
        return Paragraph(f"<i>[이미지 없음: {esc(os.path.basename(str(path)))}]</i>", ST["small"])
    try:
        with PILImage.open(path) as _im:
            iw, ih = _im.size
    except Exception:
        return Paragraph(f"<i>[이미지 오류: {esc(os.path.basename(str(path)))}]</i>", ST["small"])
    if not iw or not ih:
        return Paragraph(f"<i>[이미지 오류: {esc(os.path.basename(str(path)))}]</i>", ST["small"])
    ratio = min(max_w / iw, max_h / ih)
    im = Image(path, width=iw * ratio, height=ih * ratio); im.hAlign = "CENTER"
    return im


class LandscapeImage(Flowable):
    """이미지를 페이지를 가로로 돌려(90°) 거의 전면에 배치(자체 페이지 점유).
    조밀한 표/매트릭스를 세로 A4에서 크게 보여줄 때 사용. 제목·캡션도 함께 회전 렌더."""
    def __init__(self, path, title="", caption=""):
        super().__init__()
        self.path = path; self.title = title; self.caption = caption

    def wrap(self, aw, ah):
        self.aw, self.ah = aw, ah
        return aw, ah

    def draw(self):
        c = self.canv; aw, ah = self.aw, self.ah
        c.saveState()
        c.translate(aw, 0); c.rotate(90)        # 세로 프레임 → 가로 배치
        DW, DH = ah, aw                          # 회전 후 가용 폭(DW)·높이(DH)
        if self.title:
            c.setFillColor(INK); c.setFont(FONT_B, 13)
            c.drawString(0, DH - 0.6 * cm, self.title)
            c.setStrokeColor(INK); c.setLineWidth(1.0)
            c.line(0, DH - 0.82 * cm, DW, DH - 0.82 * cm)
        try:
            with PILImage.open(self.path) as _im:
                iw, ih = _im.size
        except Exception:
            iw, ih = 1600, 1000
        area_w = DW
        area_h = (DH - 1.1 * cm) - 0.7 * cm      # 제목 위·캡션 아래 여백
        ratio = min(area_w / iw, area_h / ih) if iw and ih else 1
        w, h = iw * ratio, ih * ratio
        x = (DW - w) / 2; y = 0.7 * cm + (area_h - h) / 2
        try:
            c.drawImage(self.path, x, y, w, h, preserveAspectRatio=True, mask="auto")
        except Exception:
            pass
        if self.caption:
            c.setFillColor(GREY); c.setFont(FONT, 9)
            c.drawCentredString(DW / 2, 0.3 * cm, self.caption)
        c.restoreState()


def figure_block(secno, title, chap, fig_idx, chart_path, bullets_list, max_h=8.6 * cm, labels=False):
    """섹션제목 + 그림 + 캡션만 '한 덩어리(KeepTogether)'로 묶고, 해석은 자연 흐름으로 반환.
    해석까지 통째로 묶으면 해석이 길 때 블록이 커져, 장 헤더 다음 남은 공간에 못 들어가 통째로
    다음 페이지로 밀리고 장 헤더만 남는 빈 페이지가 생긴다. 그림+캡션은 붙여 두고 해석은 흐르게 해
    앞이 아니라 '뒤(페이지 하단)'에 여백이 남고 다음 페이지로 이어지게 한다(정성분석 장과 동일 방식)."""
    head = []
    if title:
        head.append(sec_heading(f"{secno}. {title}" if secno is not None else title)); head.append(Spacer(1, 6))
    if chart_path:
        head.append(img_flow(chart_path, max_h=max_h))
        head.append(Paragraph(f"〈그림 {chap}-{fig_idx}〉 {esc(title)}", ST["cap"]))
    return [KeepTogether(head)] + interp_block(bullets_list, labels=labels) + [Spacer(1, 13)]


def mono_table(rows, colWidths, label_col=True, body_align=None, header=True):
    t = Table(rows, colWidths=colWidths, repeatRows=1 if header else 0)
    style = [("FONTNAME", (0, 0), (-1, -1), FONT),
             ("FONTSIZE", (0, 0), (-1, -1), 9.0), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
             ("TEXTCOLOR", (0, 0), (-1, -1), DARK),
             ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
             ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
             ("LINEBELOW", (0, 0), (-1, -1), 0.4, GHOST)]
    if header:
        style += [("FONTNAME", (0, 0), (-1, 0), FONT_B), ("TEXTCOLOR", (0, 0), (-1, 0), INK),
                  ("LINEABOVE", (0, 0), (-1, 0), 1.0, INK), ("LINEBELOW", (0, 0), (-1, 0), 1.0, INK),
                  ("BOTTOMPADDING", (0, 0), (-1, 0), 7), ("TOPPADDING", (0, 0), (-1, 0), 7)]
        style += [("LINEBELOW", (0, -1), (-1, -1), 1.0, INK)]   # 표 하단 강조선
    if label_col:
        style += [("FONTNAME", (0, 1 if header else 0), (0, -1), FONT_B), ("TEXTCOLOR", (0, 1 if header else 0), (0, -1), INK)]
    if body_align:
        style += body_align
    t.setStyle(TableStyle(style))
    return t


# ================= 목차 =================
CHAPTERS = [
    (None, "분석 요약  Executive Summary", "핵심 결론 종합"),
    (None, "기술·시장 분석", "기술 이해 · 환경분석(국내/국외)"),
    ("1", "분석 개요", "데이터 수집 · 정제 · 분석 범위"),
    ("2", "정량분석", "출원동향 · 국가 · IPC · 출원인"),
    ("3", "경쟁사 분석", "상위 기업별 상세 · 포지셔닝"),
    ("4", "정성분석", "특허맵 · 기술공백(White Space)"),
    ("5", "핵심특허", "정량 스코어링 · AI 검토"),
    (None, "참고문헌  References", "기술·시장 분석 출처"),
]


def toc_flowables(pages):
    els = [Spacer(1, 0.5 * cm), Paragraph("C O N T E N T S", ST["kicker"]),
           Paragraph("목차", ST["mokcha"]),
           HRFlowable(width="100%", thickness=1.1, color=INK, spaceBefore=8, spaceAfter=6)]
    rows = []
    for num, title, desc in CHAPTERS:
        pg = pages.get(title)
        pgs = "%02d" % pg if pg else "—"
        rows.append([Paragraph(("%02d" % int(num)) if num else "—", ST["toc_n"]),
                     Paragraph(title, ST["toc_t"]), Paragraph(pgs, ST["toc_p"])])
        rows.append(["", Paragraph(desc, ST["toc_d"]), ""])
    t = Table(rows, colWidths=[1.4 * cm, AVAIL_W - 3.0 * cm, 1.6 * cm])
    sstyle = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (0, -1), 0),
              ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
    for r in range(0, len(rows), 2):
        sstyle += [("LINEBELOW", (0, r + 1), (-1, r + 1), 0.5, LINE),
                   ("TOPPADDING", (0, r + 1), (-1, r + 1), 0), ("BOTTOMPADDING", (0, r), (-1, r), 1)]
    t.setStyle(TableStyle(sstyle))
    els.append(t)
    els.append(PageBreak())
    return els


# ================= 스토리 =================
def build_story(m, toc_pages):
    s = [Spacer(1, 1), PageBreak()]
    s += toc_flowables(toc_pages)

    s += chapter(None, CHAPTERS[0][1])
    s.append(Paragraph("본 분석의 핵심 결론을 종합한다.", ST["body"]))
    s.append(Spacer(1, 10))
    s += obullets(m.get("executive_summary") or ["요약 정보가 제공되지 않았습니다."], style="exbul")
    s.append(PageBreak())

    # ---- 기술·시장 분석 (입력 데이터와 별개의 주제 기반 환경분석) ----
    mk = m.get("market") or {}
    if mk:
        s += chapter(None, "기술·시장 분석")
        s.append(Paragraph("입력 특허 데이터와 별개로, 본 기술의 개요와 국내·외 시장 환경을 최근 동향 중심으로 정리한다.", ST["body"]))
        s.append(Spacer(1, 14))
        for key, label, tag in [("tech_overview", "기술 이해", "TECHNOLOGY"),
                                ("env_domestic", "환경 분석 · 국내 (한국)", "DOMESTIC"),
                                ("env_global", "환경 분석 · 국외", "GLOBAL")]:
            if mk.get(key):
                s.append(KeepTogether([band_heading(label, tag), panel_body(mk[key])]))
                s.append(Spacer(1, 14))
        if mk.get("sources"):
            srcs = mk["sources"] if isinstance(mk["sources"], list) else [str(mk["sources"])]
            s.append(HRFlowable(width="100%", thickness=0.5, color=LINE, spaceBefore=2, spaceAfter=7))
            s.append(Paragraph("<font name='%s'>주요 출처</font>  %s" % (FONT_B, esc(" · ".join(str(x) for x in srcs[:8]))), ST["small"]))
        s.append(PageBreak())

    s += chapter("1", "분석 개요")
    ds = m.get("data_summary") or {}
    if ds:
        rows = [["항목", "값"]]
        if "raw_count" in ds: rows.append(["수집 원본 건수", f"{ds['raw_count']:,} 건"])
        if "valid_count" in ds: rows.append(["유효 특허 건수", f"{ds['valid_count']:,} 건"])
        if "excluded_count" in ds: rows.append(["제외 건수", f"{ds['excluded_count']:,} 건"])
        if ds.get("year_range") and len(ds["year_range"]) >= 2:
            rows.append(["출원연도 범위", f"{ds['year_range'][0]} ~ {ds['year_range'][1]}"])
        crit = clean_label(ds.get("criteria_summary") or
                           (os.path.basename(str(ds["criteria_path"]).replace("\\", "/")) if ds.get("criteria_path") else ""))
        if crit: rows.append(["정제 기준", crit])
        s.append(sec_heading("1. 데이터 수집 개요")); s.append(Spacer(1, 6))
        s.append(mono_table(rows, [5 * cm, AVAIL_W - 5 * cm]))
        bl = []
        if ds.get("year_range") and len(ds["year_range"]) >= 2:
            bl.append(f"분석 대상은 출원연도 {ds['year_range'][0]}~{ds['year_range'][1]}의 유효특허 {ds.get('valid_count',0):,}건이다.")
        if ds.get("jurisdiction_top"):
            bl.append("주요 출원 관할은 " + ", ".join(f"{k} {v:,}건" for k, v in list(ds["jurisdiction_top"].items())[:5]) + " 순이다.")
        if ds.get("note"):
            bl.append(ds["note"])
        if bl:
            s.append(Spacer(1, 10)); s += obullets(bl)
    s.append(PageBreak())

    s += chapter("2", "정량분석")
    q = m.get("quant") or {}; interp = q.get("interpretation") or []; cdir = q.get("charts_dir")
    if interp:
        for i, item in enumerate(interp, 1):
            cid = item.get("id", i)
            cp = item.get("chart") or (os.path.join(cdir, f"chart_{cid}.png") if cdir else None)
            s += figure_block(i, item.get("title", f"분석 {i}"), 2, i, cp, item.get("bullets"))
    else:
        s.append(Paragraph("정량분석이 수행되지 않았습니다.", ST["small"]))
    s.append(PageBreak())

    s += chapter("3", "경쟁사 분석")
    comp = m.get("competitor") or {}
    if comp.get("error"):
        s.append(Paragraph(f"경쟁사 분석 미수행: {comp['error']}", ST["small"]))
    elif comp.get("companies"):
        ch = comp.get("charts", {}); ci = comp.get("chart_interp", {}); sno = 0
        # O/S Matrix는 정성분석 장의 구간형 매트릭스로 일원화 — 경쟁사 장의 단순 히트맵(osmatrix)은 제외
        for key, cap in [("share", "상위 출원인 점유율"), ("trend", "상위 출원인 연도별 출원 추이"),
                         ("ipc", "상위 출원인 기술 포커스(IPC)"), ("techflow", "상위 출원인 기술 흐름도")]:
            if ch.get(key):
                sno += 1; s += figure_block(sno, cap, 3, sno, ch[key], ci.get(key), max_h=8.6 * cm)
        sno += 1
        cellr = S("rc", 8.3, leading=10.5)
        rh = S("rh", 8.5, bold=True, textColor=INK, leading=10.5)

        def RP(t, st=cellr):
            return Paragraph(esc(t), st)

        def _rp0(c):
            return (c.get("rep_patents") or [{}])[0]
        # 피인용·패밀리는 데이터가 있을 때만 컬럼을 노출(KIPRIS 등 미제공 시 빈 컬럼 방지)
        has_cit = any(_rp0(c).get("citations") is not None for c in comp["companies"])
        has_fam = any(_rp0(c).get("family") is not None for c in comp["companies"])
        heads = ["순위", "기업", "대표 특허번호", "명칭", "연도"]
        cw = [0.9 * cm, 3.0 * cm, 2.9 * cm, None, 1.0 * cm]   # None=명칭(가변폭)
        if has_cit:
            heads.append("피인용"); cw.append(1.3 * cm)
        if has_fam:
            heads.append("패밀리"); cw.append(1.3 * cm)
        fixed = sum(w for w in cw if w is not None)
        cw[3] = AVAIL_W - fixed
        rows = [[Paragraph(h, rh) for h in heads]]
        for c in comp["companies"]:
            rp = _rp0(c)
            row = [RP(c.get("rank", "")), RP(trunc(c.get("name", ""), 18)),
                   RP(fmt_patent_no(rp.get("number", ""))),
                   RP(trunc(rp.get("title", ""), 48)), RP(rp.get("year", "") or "")]
            if has_cit:
                row.append(RP(rp.get("citations") if rp.get("citations") is not None else ""))
            if has_fam:
                row.append(RP(rp.get("family") if rp.get("family") is not None else ""))
            rows.append(row)
        center_cols = [("ALIGN", (0, 1), (0, -1), "CENTER"), ("ALIGN", (4, 1), (len(heads) - 1, -1), "CENTER")]
        _bcols = (["피인용"] if has_cit else []) + (["패밀리"] if has_fam else [])
        cap_basis = ("·".join(_bcols) + " 기준") if _bcols else "출원인별 대표 특허"
        # 대표 특허 표 — 새 페이지에서 시작, 제목+표+캡션을 한 덩어리로(쪼개짐 방지)
        s.append(PageBreak())
        s.append(KeepTogether([
            sec_heading(f"{sno}. 주요 출원인 대표 특허"), Spacer(1, 6),
            mono_table(rows, cw, label_col=False, body_align=center_cols),
            Paragraph(f"〈표 3-1〉 주요 출원인별 대표 특허 ({cap_basis})", ST["cap"])]))
        # 상세 프로파일 — 새 페이지에서 시작
        sno += 1
        s.append(PageBreak())
        prof = [sec_heading(f"{sno}. 주요 출원인 상세 프로파일"), Spacer(1, 8)]
        for c in comp["companies"]:
            head = f"{c.get('rank')}. {c.get('name')}  ({c.get('count')}건 · {(c.get('share') or 0)*100:.1f}%)"
            tags = []
            if c.get("positioning"): tags.append(c["positioning"])
            if c.get("momentum"): tags.append(f"모멘텀 {c['momentum']}")
            sub = [Paragraph(esc(head) + (f"   <font color='#a3a3a3' size=9>{esc(' · '.join(tags))}</font>" if tags else ""), ST["co"])]
            sub += interp_block(c.get("profile"))
            sub.append(Spacer(1, 10)); prof.append(KeepTogether(sub))
        s.append(KeepTogether(prof[:2])); s += prof[2:]
    else:
        s.append(Paragraph("경쟁사 분석이 수행되지 않았습니다.", ST["small"]))
    s.append(PageBreak())

    s += chapter("4", "정성분석")
    ql = m.get("qualitative") or {}; qc = ql.get("charts", {}); fno = 0; any_q = False
    for key, label in [("tech_flow", "기술흐름도"),
                       ("contour_ipc", "특허맵 — IPC 기술분류 등고선"),
                       ("contour_tech", "특허맵 — 기술주제(키워드) 등고선")]:
        node = ql.get(key)
        if not node:
            continue
        any_q = True; fno += 1
        # 제목+그림+캡션만 한 덩어리(장 헤더 다음에 들어가도록) — 해석은 자연 흐름(정량·경쟁사와 동일)
        head = [sec_heading(f"{fno}. {node.get('title', label)}"), Spacer(1, 6)]
        if qc.get(key):
            head.append(img_flow(qc[key], max_h=9.5 * cm))
            head.append(Paragraph(f"〈그림 4-{fno}〉 {esc(node.get('title', label))}", ST["cap"]))
        s.append(KeepTogether(head))
        s += interp_block(node.get("bullets"), labels=False)
        if key.startswith("contour"):
            if node.get("hotspots"):
                s.append(Paragraph(esc("핫스팟 · " + ", ".join(h.get("ipc") or h.get("term") or "" for h in node["hotspots"])), ST["small"]))
            if node.get("whitespace"):
                s.append(Paragraph(esc("White Space 후보 · " + ", ".join("/".join(w.get("near_ipc") or []) for w in node["whitespace"])), ST["small"]))
        s.append(Spacer(1, 13))

    # O/S 매트릭스 (구간별 공백 탐색) — 가로 전용 페이지 + 해석
    osm = ql.get("os_matrix")
    if osm and qc.get("os_matrix"):
        any_q = True; fno += 1
        title = osm.get("title", "O/S Matrix")
        cap = f"〈그림 4-{fno}〉 {title} (대각선=시간 흐름, 색=조합 범주)"
        if osm.get("landscape"):
            # 아주 넓은 매트릭스(8×8+)는 가로 전용 페이지로 회전 배치
            s.append(PageBreak())
            s.append(LandscapeImage(qc["os_matrix"], title=f"{fno}. {title}", caption=cap))
            s.append(PageBreak())
            s.append(sec_heading(f"{title} — 해석")); s.append(Spacer(1, 6))
            s += interp_block(osm.get("bullets"), labels=False)
        else:
            # 6×6 등은 세로 폭에 맞춰 일반 도표로(제목+그림+캡션 한 덩어리)
            s.append(KeepTogether([sec_heading(f"{fno}. {title}"), Spacer(1, 6),
                                   img_flow(qc["os_matrix"], max_h=15.5 * cm),
                                   Paragraph(esc(cap), ST["cap"])]))
            s += interp_block(osm.get("bullets"), labels=False)
        s.append(Spacer(1, 13))

    # 공백기술 & 진입 전략 (White Space 종합) — 보고서 핵심 목적
    wss = m.get("whitespace_strategy")
    if wss and wss.get("opportunities"):
        any_q = True
        s.append(sec_heading(wss.get("title", "공백기술 & 진입 전략"))); s.append(Spacer(1, 6))
        if wss.get("intro"):
            s.append(Paragraph(rich(wss["intro"]), ST["body"])); s.append(Spacer(1, 9))
        whead = S("wsh", 8.6, bold=True, textColor=INK, alignment=TA_CENTER, leading=11)
        wcell = S("wsc", 8.6, textColor=DARK, leading=12)
        rows = [[Paragraph(h, whead) for h in ["순위", "공백 조합 (목적×수단)", "근거", "진입 전략"]]]
        for op in wss["opportunities"]:
            rows.append([Paragraph(str(op.get("rank", "")), whead),
                         Paragraph(rich(op.get("combo", "")), wcell),
                         Paragraph(rich(op.get("evidence", "")), wcell),
                         Paragraph(rich(op.get("strategy", "")), wcell)])
        s.append(mono_table(rows, [1.0 * cm, 4.2 * cm, 4.0 * cm, AVAIL_W - 9.2 * cm], label_col=False,
                            body_align=[("ALIGN", (0, 1), (0, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        s.append(Paragraph("〈표 4-1〉 우선 공백기술 및 연구부서 진입 전략", ST["cap"]))
        if wss.get("contour_notes"):
            s.append(Spacer(1, 8))
            s.append(Paragraph("특허맵 등고선 기반 추가 공백", ST["co"]))
            s += obullets(wss["contour_notes"], style="ibul")

    if not any_q:
        s.append(Paragraph("정성분석이 수행되지 않았습니다.", ST["small"]))
    s.append(PageBreak())

    s += chapter("5", "핵심특허")
    core = m.get("core") or []
    if core:
        cell = S("tc", 8.4, leading=10.8); cellb = S("tcb", 8.4, bold=True, leading=10.8)
        chead = S("th", 8.6, bold=True, textColor=INK, alignment=TA_CENTER, leading=10.8)

        def P(t, st=cell):
            return Paragraph(esc(t), st)
        rows = [[Paragraph(h, chead) for h in ["순위", "특허번호", "명칭", "출원인", "연도"]]]
        for c in core:
            rows.append([P(c.get("rank", ""), cellb), P(trunc(fmt_patent_no(c.get("number", "")), 22)),
                         P(trunc(c.get("title", ""), 80)), P(trunc(c.get("applicant", ""), 34)),
                         P(c.get("year", "") or "")])
        s.append(sec_heading("1. 핵심특허 종합")); s.append(Spacer(1, 6))
        s.append(mono_table(rows, [1.0 * cm, 3.2 * cm, AVAIL_W - 8.7 * cm, 3.4 * cm, 1.1 * cm],
                            label_col=False,
                            body_align=[("ALIGN", (0, 1), (1, -1), "CENTER"), ("ALIGN", (4, 1), (4, -1), "CENTER")]))
        s.append(Paragraph(f"〈표 5-1〉 정량 스코어링·AI 검토 기반 핵심특허 Top {len(core)}", ST["cap"]))
        s.append(Spacer(1, 12))
        s.append(sec_heading("2. 핵심특허 선정 근거")); s.append(Spacer(1, 8))
        rlbl = S("rlbl", 9.0, bold=True, textColor=INK, leading=12.5)
        rrows = []
        for c in core:
            if c.get("reason"):
                rrows.append([Paragraph(f"{c.get('rank')}위<br/><font name='{FONT}' color='#737373' size=7.5>{esc(fmt_patent_no(c.get('number')))}</font>", rlbl),
                              Paragraph(rich(c["reason"]), ST["body"])])
        if rrows:
            rt = Table(rrows, colWidths=[3.0 * cm, AVAIL_W - 3.0 * cm])
            rt.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                    ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                                    ("LEFTPADDING", (1, 0), (1, -1), 8), ("LEFTPADDING", (0, 0), (0, -1), 0),
                                    ("LINEBELOW", (0, 0), (-1, -2), 0.4, GHOST)]))
            s.append(rt)
    else:
        s.append(Paragraph("핵심특허 선별이 수행되지 않았습니다.", ST["small"]))

    # ---- 참고문헌 (기술·시장 분석 출처) — 맨 뒷페이지. 부록은 표시하지 않는다 ----
    mk = m.get("market") or {}
    refs = mk.get("references") or mk.get("sources") or []
    if refs:
        s.append(PageBreak())
        s += chapter(None, CHAPTERS[-1][1])
        refstyle = S("ref", 9.5, textColor=DARK, leftIndent=17, firstLineIndent=-17,
                     spaceAfter=7, leading=14.5)
        for i, r in enumerate(refs, 1):
            s.append(Paragraph(f"<font name='{FONT_B}'>[{i}]</font>&nbsp;&nbsp;{esc(str(r))}", refstyle))
    return s


class KDoc(SimpleDocTemplate):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.captured = {}

    def afterFlowable(self, fl):
        if isinstance(fl, ChapAnchor) and fl.capture and fl.title:
            self.captured.setdefault(fl.title, self.page)


def main():
    global META, PAGE_CHAP
    if len(sys.argv) < 2:
        sys.exit("Usage: python _build_pdf.py <manifest.json> [출력.pdf]")
    manifest_path = sys.argv[1]
    with open(manifest_path, encoding="utf-8") as _f:
        m = json.load(_f)
    META = m.get("meta", {})
    out_pdf = sys.argv[2] if len(sys.argv) > 2 else str(Path(manifest_path).resolve().parent.parent / "IP_Landscape_Report.pdf")
    kw = dict(pagesize=A4, topMargin=TOPM, bottomMargin=1.7 * cm, leftMargin=MARGIN, rightMargin=MARGIN,
              title=META.get("title", "IP Landscape Report"))

    d1 = KDoc(BytesIO(), **kw)
    d1.build(build_story(m, {}), onFirstPage=draw_cover, onLaterPages=draw_chrome)
    captured = d1.captured; total = d1.page
    starts = sorted(((p, t) for t, p in captured.items()), key=lambda x: x[0])
    PAGE_CHAP = {}
    for pg in range(1, total + 1):
        cur = ""
        for sp, t in starts:
            if sp <= pg:
                cur = t.split("  ")[0]
        PAGE_CHAP[pg] = cur

    d2 = KDoc(out_pdf, **kw)
    d2.build(build_story(m, captured), onFirstPage=draw_cover, onLaterPages=draw_chrome)
    print(f"[ok] PDF 생성 완료 → {out_pdf}  (미니멀 양식, {total}p, 폰트 {FONT}/{FONT_B})")


if __name__ == "__main__":
    main()
