# -*- coding: utf-8 -*-
"""
IP Landscape 통합 HWPX(한글) 보고서 빌더.

PDF 빌더(_build_pdf.py)와 **동일한 manifest.json**을 소비해 한글(.hwpx) 보고서를 만든다.
PDF의 프리미엄 비주얼(canvas 표지·2-pass 목차)을 1:1 복제하지는 않지만, 내용·차트·표·해석을
같은 5장 구조로 담아 한글에서 바로 후속 편집할 수 있게 한다.

기반: patent-dashboard의 양식.hwpx 템플릿(이미지/캡션/불릿/장헤더 스타일 검증됨)을 벤더링해 사용.
데이터 표(핵심특허·경쟁사)는 header.xml에 borderFill 8(헤더 음영)·9(격자)를 주입해 그린다.

Usage: python _build_hwpx.py <manifest.json> [출력.hwpx]
"""
import sys, os, json, shutil, zipfile, re, html
from pathlib import Path

from _ipl_io import ensure_pkgs, fmt_patent_no, trunc, clean_label
ensure_pkgs(["pillow"])
from PIL import Image as PILImage

SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATE = os.environ.get("IPL_HWPX_TEMPLATE", str(SCRIPT_DIR.parent / "assets" / "양식.hwpx"))

# ---- 템플릿 스타일 ID (양식.hwpx header.xml 기준) ----
CP_SUBTITLE = "17"   # 11pt bold  (소제목)
CP_IMG = "16"        # 10pt       (이미지 런)
CP_CAPTION = "12"    # 9pt bold   (캡션 / 표 헤더 텍스트)
CP_BODY = "16"       # 10pt       (본문·불릿·표 본문)
CP_CHAP_NUM = "8"    # 15pt bold white (장 번호 셀)
CP_CHAP_TITLE = "9"  # 15pt bold black (장 제목 셀)
PP_IMG = "24"        # CENTER (이미지 문단)
PP_CAPTION = "23"    # CENTER (캡션 문단)
PP_CENTER = "20"     # CENTER (표 헤더 셀)
PP_LEFT = "11"       # LEFT   (표 본문 셀)
BF_TABLE = "4"       # 표 컨테이너(테두리 없음)
BF_CHAP_NUM = "5"    # 네이비 장번호 셀
BF_CHAP_TITLE = "6"  # 무테두리 장제목 셀
BF_TH = "8"          # (주입) 표 헤더 셀: 음영+격자
BF_TD = "9"          # (주입) 표 본문 셀: 격자

BODY_W = 42520       # A4 본문폭(HWPUNIT) = 59528 - 8504*2

_pid = [2147483648]
def nid():
    _pid[0] += 1
    return _pid[0]

def esc(t):
    s = "" if t is None else str(t)
    s = re.sub(r"[ \t 　]{2,}", " ", s)   # 연속 공백(탭·NBSP·전각) -> 한 칸
    return html.escape(s, quote=False)


# ================= borderFill 주입 =================
_BF8 = (
    '<hh:borderFill id="8" threeD="0" shadow="0" centerLine="NONE" breakCellSeparateLine="0">'
    '<hh:slash type="NONE" Crooked="0" isCounter="0"/><hh:backSlash type="NONE" Crooked="0" isCounter="0"/>'
    '<hh:leftBorder type="SOLID" width="0.12 mm" color="#888888"/>'
    '<hh:rightBorder type="SOLID" width="0.12 mm" color="#888888"/>'
    '<hh:topBorder type="SOLID" width="0.4 mm" color="#333333"/>'
    '<hh:bottomBorder type="SOLID" width="0.4 mm" color="#333333"/>'
    '<hh:diagonal type="SOLID" width="0.1 mm" color="#000000"/>'
    '<hc:fillBrush><hc:winBrush faceColor="#E9E9E9" hatchColor="#999999" alpha="0"/></hc:fillBrush>'
    '</hh:borderFill>'
)
_BF9 = (
    '<hh:borderFill id="9" threeD="0" shadow="0" centerLine="NONE" breakCellSeparateLine="0">'
    '<hh:slash type="NONE" Crooked="0" isCounter="0"/><hh:backSlash type="NONE" Crooked="0" isCounter="0"/>'
    '<hh:leftBorder type="SOLID" width="0.12 mm" color="#BBBBBB"/>'
    '<hh:rightBorder type="SOLID" width="0.12 mm" color="#BBBBBB"/>'
    '<hh:topBorder type="SOLID" width="0.12 mm" color="#BBBBBB"/>'
    '<hh:bottomBorder type="SOLID" width="0.12 mm" color="#BBBBBB"/>'
    '<hh:diagonal type="SOLID" width="0.1 mm" color="#000000"/>'
    '</hh:borderFill>'
)

def inject_borderfills(header_xml):
    """표용 borderFill 8·9를 header.xml에 주입(이미 있으면 그대로)."""
    if '<hh:borderFill id="8"' in header_xml and '<hh:borderFill id="9"' in header_xml:
        return header_xml
    m = re.search(r'<hh:borderFills itemCnt="(\d+)"', header_xml)
    if not m:
        return header_xml  # 방어: 못 찾으면 표는 BF_TABLE로 폴백
    cnt = int(m.group(1))
    header_xml = header_xml.replace(m.group(0), f'<hh:borderFills itemCnt="{cnt + 2}"', 1)
    header_xml = header_xml.replace('</hh:borderFills>', _BF8 + _BF9 + '</hh:borderFills>', 1)
    return header_xml


# ================= 문단 빌더 =================
def p_empty():
    return f'<hp:p id="{nid()}" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0"><hp:run charPrIDRef="{CP_BODY}"/></hp:p>'

def p_text(text, cp=CP_BODY, pp="0", page_break=False):
    pb = "1" if page_break else "0"
    return (f'<hp:p id="{nid()}" paraPrIDRef="{pp}" styleIDRef="0" pageBreak="{pb}" columnBreak="0" merged="0">'
            f'<hp:run charPrIDRef="{cp}"><hp:t>{esc(text)}</hp:t></hp:run></hp:p>')

def p_subtitle(text, page_break=False):
    return p_text(text, cp=CP_SUBTITLE, pp="0", page_break=page_break)

def p_caption(text):
    return (f'<hp:p id="{nid()}" paraPrIDRef="{PP_CAPTION}" styleIDRef="25" pageBreak="0" columnBreak="0" merged="0">'
            f'<hp:run charPrIDRef="{CP_CAPTION}"><hp:t>{esc(text)}</hp:t></hp:run></hp:p>')

def p_bullet(text):
    return p_text(f"■ {text}", cp=CP_BODY, pp="0")

def p_label_bullet(label, text):
    """{l,t} 라벨형 해석 → '○ [라벨] 내용' 한 줄(라벨은 별도 볼드 런)."""
    return (f'<hp:p id="{nid()}" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
            f'<hp:run charPrIDRef="{CP_CAPTION}"><hp:t>■ {esc(label)}  </hp:t></hp:run>'
            f'<hp:run charPrIDRef="{CP_BODY}"><hp:t>{esc(text)}</hp:t></hp:run></hp:p>')

def _strip_md(t):
    """HWPX는 인라인 볼드를 단순화 — `**강조**` 마커만 제거(한글에서 직접 편집)."""
    return re.sub(r"\*\*(.+?)\*\*", r"\1", "" if t is None else str(t))


def _refmark(refs):
    """출처 인용번호를 본문 끝에 [1,2] 형태로 부착(참고문헌 페이지와 연결)."""
    if not refs:
        return ""
    nums = ",".join(str(r) for r in (refs if isinstance(refs, (list, tuple)) else [refs]))
    return f" [{nums}]"


def bullets(items, labels=True):
    """문자열이면 ■ 불릿, {l,t}이면 라벨형(labels=True). labels=False면 라벨을 빼고
    내용만 ■ 불릿으로. dict에 refs가 있으면 [n] 인용번호를 끝에 붙인다. 빈 항목 무시."""
    out = []
    for b in (items or []):
        if isinstance(b, dict):
            l, t, refs = b.get("l", ""), b.get("t", ""), b.get("refs")
            if str(t).strip():
                disp = _strip_md(t) + _refmark(refs)
                out.append(p_label_bullet(l, disp) if (labels and str(l).strip()) else p_bullet(disp))
        elif str(b).strip():
            out.append(p_bullet(_strip_md(b)))
    return out


def p_image(image_id, px_w, px_h, max_w=39776):
    """이미지 문단. 폭 max_w(HWPUNIT)에 맞춰 비율 축소."""
    px_w = px_w or 1600
    px_h = px_h or 900
    display_w = max_w
    display_h = int(display_w * px_h / px_w)
    org_w = int(px_w * 7200 / 96)
    org_h = int(px_h * 7200 / 96)
    cx, cy = display_w // 2, display_h // 2
    return (
        f'<hp:p id="{nid()}" paraPrIDRef="{PP_IMG}" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
        f'<hp:run charPrIDRef="{CP_IMG}">'
        f'<hp:pic id="{nid()}" zOrder="1" numberingType="PICTURE" textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" lock="0" dropcapstyle="None" href="" groupLevel="0" instid="{nid()}" reverse="0">'
        f'<hp:offset x="0" y="0"/><hp:orgSz width="{org_w}" height="{org_h}"/>'
        f'<hp:curSz width="{display_w}" height="{display_h}"/><hp:flip horizontal="0" vertical="0"/>'
        f'<hp:rotationInfo angle="0" centerX="{cx}" centerY="{cy}" rotateimage="1"/>'
        f'<hp:renderingInfo><hc:transMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/>'
        f'<hc:scaMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/>'
        f'<hc:rotMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/></hp:renderingInfo>'
        f'<hc:img binaryItemIDRef="{image_id}" bright="0" contrast="0" effect="REAL_PIC" alpha="0"/>'
        f'<hp:imgRect><hc:pt0 x="0" y="0"/><hc:pt1 x="{org_w}" y="0"/><hc:pt2 x="{org_w}" y="{org_h}"/><hc:pt3 x="0" y="{org_h}"/></hp:imgRect>'
        f'<hp:imgClip left="0" right="{org_w}" top="0" bottom="{org_h}"/>'
        f'<hp:inMargin left="0" right="0" top="0" bottom="0"/><hp:imgDim dimwidth="{org_w}" dimheight="{org_h}"/>'
        f'<hp:effects/>'
        f'<hp:sz width="{display_w}" widthRelTo="ABSOLUTE" height="{display_h}" heightRelTo="ABSOLUTE" protect="0"/>'
        f'<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="0" allowOverlap="0" holdAnchorAndSO="0" vertRelTo="PARA" horzRelTo="PARA" vertAlign="TOP" horzAlign="LEFT" vertOffset="0" horzOffset="0"/>'
        f'<hp:outMargin left="0" right="0" top="0" bottom="0"/><hp:shapeComment></hp:shapeComment>'
        f'</hp:pic><hp:t/></hp:run></hp:p>'
    )


# ================= 표 빌더 =================
def _cell(text, col, row, w, h, th=False, align_center=True):
    bf = BF_TH if th else BF_TD
    cp = CP_CAPTION if th else CP_BODY
    pp = PP_CENTER if align_center else PP_LEFT
    return (
        f'<hp:tc name="" header="{1 if th else 0}" hasMargin="1" protect="0" editable="0" dirty="0" borderFillIDRef="{bf}">'
        f'<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER" linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">'
        f'<hp:p id="{nid()}" paraPrIDRef="{pp}" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
        f'<hp:run charPrIDRef="{cp}"><hp:t>{esc(text)}</hp:t></hp:run></hp:p>'
        f'</hp:subList>'
        f'<hp:cellAddr colAddr="{col}" rowAddr="{row}"/><hp:cellSpan colSpan="1" rowSpan="1"/>'
        f'<hp:cellSz width="{w}" height="{h}"/>'
        f'<hp:cellMargin left="283" right="283" top="141" bottom="141"/>'
        f'</hp:tc>'
    )

def make_table(headers, data, col_w, body_center=None, row_h=2600):
    """격자 데이터 표. headers=[..], data=[[..],..], col_w=[..](합=BODY_W), body_center=[bool]×col."""
    ncol = len(headers)
    if body_center is None:
        body_center = [True] * ncol
    # 폭 정규화
    s = sum(col_w) or 1
    col_w = [int(w * BODY_W / s) for w in col_w]
    col_w[-1] += BODY_W - sum(col_w)
    rows = []
    hrow = "".join(_cell(headers[c], c, 0, col_w[c], row_h, th=True) for c in range(ncol))
    rows.append(f'<hp:tr>{hrow}</hp:tr>')
    for r, dr in enumerate(data, 1):
        cells = "".join(
            _cell(dr[c] if c < len(dr) else "", c, r, col_w[c], row_h, th=False, align_center=body_center[c])
            for c in range(ncol))
        rows.append(f'<hp:tr>{cells}</hp:tr>')
    total_h = row_h * (len(data) + 1)
    tbl = (
        f'<hp:tbl id="{nid()}" zOrder="0" numberingType="TABLE" textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" '
        f'lock="0" dropcapstyle="None" pageBreak="CELL" repeatHeader="1" rowCnt="{len(data)+1}" colCnt="{ncol}" '
        f'cellSpacing="0" borderFillIDRef="{BF_TABLE}" noAdjust="0">'
        f'<hp:sz width="{BODY_W}" widthRelTo="ABSOLUTE" height="{total_h}" heightRelTo="ABSOLUTE" protect="0"/>'
        f'<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1" allowOverlap="0" holdAnchorAndSO="0" vertRelTo="PARA" horzRelTo="COLUMN" vertAlign="TOP" horzAlign="LEFT" vertOffset="0" horzOffset="0"/>'
        f'<hp:outMargin left="0" right="0" top="0" bottom="0"/><hp:inMargin left="0" right="0" top="0" bottom="0"/>'
        + "".join(rows) + '</hp:tbl>'
    )
    return (f'<hp:p id="{nid()}" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
            f'<hp:run charPrIDRef="{CP_BODY}">{tbl}<hp:t/></hp:run></hp:p>')


# ================= 장 헤더 =================
def chapter_header(num, title, page_break=True):
    """네이비 번호 박스 + 제목 셀의 장 헤더 표(템플릿 양식)."""
    pb = "1" if page_break else "0"
    num_txt = esc(num) if num else "·"
    return (
        f'<hp:p id="{nid()}" paraPrIDRef="22" styleIDRef="22" pageBreak="{pb}" columnBreak="0" merged="0">'
        f'<hp:run charPrIDRef="7">'
        f'<hp:tbl id="{nid()}" zOrder="0" numberingType="TABLE" textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" lock="0" dropcapstyle="None" pageBreak="CELL" repeatHeader="0" rowCnt="1" colCnt="2" cellSpacing="0" borderFillIDRef="{BF_TABLE}" noAdjust="0">'
        f'<hp:sz width="{BODY_W}" widthRelTo="ABSOLUTE" height="2350" heightRelTo="ABSOLUTE" protect="0"/>'
        f'<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1" allowOverlap="0" holdAnchorAndSO="0" vertRelTo="PARA" horzRelTo="COLUMN" vertAlign="TOP" horzAlign="LEFT" vertOffset="0" horzOffset="0"/>'
        f'<hp:outMargin left="0" right="0" top="0" bottom="0"/><hp:inMargin left="283" right="283" top="425" bottom="425"/>'
        f'<hp:tr>'
        f'<hp:tc name="" header="0" hasMargin="0" protect="0" editable="0" dirty="0" borderFillIDRef="{BF_CHAP_NUM}">'
        f'<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER" linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">'
        f'<hp:p id="{nid()}" paraPrIDRef="{PP_CENTER}" styleIDRef="23" pageBreak="0" columnBreak="0" merged="0">'
        f'<hp:run charPrIDRef="{CP_CHAP_NUM}"><hp:t>{num_txt}</hp:t></hp:run></hp:p>'
        f'</hp:subList>'
        f'<hp:cellAddr colAddr="0" rowAddr="0"/><hp:cellSpan colSpan="1" rowSpan="1"/>'
        f'<hp:cellSz width="5000" height="1866"/><hp:cellMargin left="510" right="510" top="141" bottom="141"/>'
        f'</hp:tc>'
        f'<hp:tc name="" header="0" hasMargin="1" protect="0" editable="0" dirty="0" borderFillIDRef="{BF_CHAP_TITLE}">'
        f'<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER" linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">'
        f'<hp:p id="{nid()}" paraPrIDRef="21" styleIDRef="24" pageBreak="0" columnBreak="0" merged="0">'
        f'<hp:run charPrIDRef="{CP_CHAP_TITLE}"><hp:t>{esc(title)}</hp:t></hp:run></hp:p>'
        f'</hp:subList>'
        f'<hp:cellAddr colAddr="1" rowAddr="0"/><hp:cellSpan colSpan="1" rowSpan="1"/>'
        f'<hp:cellSz width="{BODY_W - 5000}" height="1866"/><hp:cellMargin left="1417" right="1417" top="425" bottom="425"/>'
        f'</hp:tc>'
        f'</hp:tr></hp:tbl><hp:t/></hp:run></hp:p>'
    )


# ================= 이미지 자산 관리 =================
class ImageRegistry:
    def __init__(self):
        self.items = []   # (image_id, src_path)
        self._map = {}

    def add(self, src):
        if not src or not os.path.exists(src):
            return None
        src = os.path.abspath(src)
        if src in self._map:
            return self._map[src]
        iid = f"image{len(self.items) + 1}"
        self.items.append((iid, src))
        self._map[src] = iid
        return iid


def figure(reg, subtitle, chart_path, caption, interp, page_break=True, max_w=39776):
    """소제목 + 이미지 + 캡션 + 해석불릿 1블록."""
    out = [p_subtitle(subtitle, page_break=page_break)]
    iid = reg.add(chart_path)
    if iid:
        try:
            with PILImage.open(chart_path) as im:
                w, h = im.size
        except Exception:
            w, h = 1600, 900
        out.append(p_image(iid, w, h, max_w=max_w))
        if caption:
            out.append(p_caption(caption))
    elif chart_path:
        out.append(p_text(f"[이미지 없음: {os.path.basename(str(chart_path))}]", cp=CP_BODY))
    out.append(p_empty())
    out += bullets(interp, labels=False)   # 차트 해석은 반복 라벨 제거(정량·경쟁사차트·정성)
    out.append(p_empty())
    return out


# ================= 본문 조립 =================
def build_body(m, reg):
    meta = m.get("meta", {})
    P = []

    # ---- 표지(첫 페이지) : secPr는 main()에서 첫 문단에 보존, 여기선 제목 블록만 ----
    P.append(p_empty()); P.append(p_empty()); P.append(p_empty())
    P.append(p_text("IP LANDSCAPE REPORT", cp=CP_CAPTION, pp=PP_CENTER))
    P.append(p_empty())
    P.append(p_text(meta.get("title", "IP 랜드스케이프 분석 보고서"), cp=CP_SUBTITLE, pp=PP_CENTER))
    P.append(p_empty())
    if meta.get("subject"):
        P.append(p_text(f"연구주제 · {meta['subject']}", cp=CP_BODY, pp=PP_CENTER))
    P.append(p_empty()); P.append(p_empty())
    meta_line = "  |  ".join(x for x in [
        f"작성  {meta['author']}" if meta.get("author") else None,
        f"작성일  {meta['date']}" if meta.get("date") else None,
        f"분석대상  {meta['source']}" if meta.get("source") else None,
    ] if x)
    if meta_line:
        P.append(p_text(meta_line, cp=CP_CAPTION, pp=PP_CENTER))

    # ---- 분석 요약 ----
    P.append(chapter_header(None, "분석 요약  Executive Summary"))
    P.append(p_empty())
    P.append(p_text("본 분석의 핵심 결론을 종합한다.", cp=CP_BODY))
    P.append(p_empty())
    P += bullets(m.get("executive_summary") or ["요약 정보가 제공되지 않았습니다."])

    # ---- 기술·시장 분석 (입력 데이터와 별개의 주제 기반 환경분석) ----
    mk = m.get("market") or {}
    if mk:
        P.append(chapter_header(None, "기술·시장 분석"))
        P.append(p_empty())
        for sec_no, (key, head) in enumerate(
                [("tech_overview", "기술 이해"), ("env_domestic", "환경 분석 — 국내(한국)"),
                 ("env_global", "환경 분석 — 국외")], 1):
            if mk.get(key):
                P.append(p_subtitle(f"{sec_no}. {head}", page_break=False))
                P.append(p_empty())
                P += bullets(mk[key], labels=False)
                P.append(p_empty())
        if mk.get("sources"):
            srcs = mk["sources"] if isinstance(mk["sources"], list) else [str(mk["sources"])]
            P.append(p_text("주요 출처 · " + "; ".join(str(x) for x in srcs[:8]), cp=CP_CAPTION))

    # ---- 1. 분석 개요 ----
    P.append(chapter_header("1", "분석 개요"))
    P.append(p_empty())
    ds = m.get("data_summary") or {}
    if ds:
        rows = []
        if "raw_count" in ds: rows.append(["수집 원본 건수", f"{ds['raw_count']:,} 건"])
        if "valid_count" in ds: rows.append(["유효 특허 건수", f"{ds['valid_count']:,} 건"])
        if "excluded_count" in ds: rows.append(["제외 건수", f"{ds['excluded_count']:,} 건"])
        if ds.get("year_range") and len(ds["year_range"]) >= 2:
            rows.append(["출원연도 범위", f"{ds['year_range'][0]} ~ {ds['year_range'][1]}"])
        crit = clean_label(ds.get("criteria_summary") or
                           (os.path.basename(str(ds["criteria_path"]).replace("\\", "/")) if ds.get("criteria_path") else ""))
        if crit: rows.append(["정제 기준", crit])
        if rows:
            P.append(p_subtitle("1. 데이터 수집 개요", page_break=False))
            P.append(p_empty())
            P.append(make_table(["항목", "값"], rows, [12, 30], body_center=[True, False]))
            P.append(p_empty())
        bl = []
        if ds.get("year_range") and len(ds["year_range"]) >= 2:
            bl.append(f"분석 대상은 출원연도 {ds['year_range'][0]}~{ds['year_range'][1]}의 유효특허 {ds.get('valid_count',0):,}건이다.")
        if ds.get("jurisdiction_top"):
            bl.append("주요 출원 관할은 " + ", ".join(f"{k} {v:,}건" for k, v in list(ds["jurisdiction_top"].items())[:5]) + " 순이다.")
        if ds.get("note"):
            bl.append(ds["note"])
        P += bullets(bl)
    else:
        P.append(p_text("분석 개요 정보가 제공되지 않았습니다.", cp=CP_BODY))

    # ---- 2. 정량분석 ----
    P.append(chapter_header("2", "정량분석"))
    q = m.get("quant") or {}
    interp = q.get("interpretation") or []
    cdir = q.get("charts_dir")
    if interp:
        for i, item in enumerate(interp, 1):
            cid = item.get("id", i)
            cp = item.get("chart") or (os.path.join(cdir, f"chart_{cid}.png") if cdir else None)
            title = item.get("title", f"분석 {i}")
            P += figure(reg, f"{i}. {title}", cp, f"〈그림 2-{i}〉 {title}", item.get("bullets"),
                        page_break=(i > 1))
    else:
        P.append(p_empty()); P.append(p_text("정량분석이 수행되지 않았습니다.", cp=CP_BODY))

    # ---- 3. 경쟁사 분석 ----
    P.append(chapter_header("3", "경쟁사 분석"))
    comp = m.get("competitor") or {}
    if comp.get("error"):
        P.append(p_empty()); P.append(p_text(f"경쟁사 분석 미수행: {comp['error']}", cp=CP_BODY))
    elif comp.get("companies"):
        ch = comp.get("charts", {}); ci = comp.get("chart_interp", {}); sno = 0
        # O/S Matrix는 정성분석 장의 구간형 매트릭스로 일원화 — 경쟁사 장의 단순 히트맵(osmatrix)은 제외
        for key, cap in [("share", "상위 출원인 점유율"), ("trend", "상위 출원인 연도별 출원 추이"),
                         ("ipc", "상위 출원인 기술 포커스(IPC)"), ("techflow", "상위 출원인 기술 흐름도")]:
            if ch.get(key):
                sno += 1
                P += figure(reg, f"{sno}. {cap}", ch[key], f"〈그림 3-{sno}〉 {cap}", ci.get(key),
                            page_break=(sno > 1))
        # 대표 특허 표
        sno += 1
        P.append(p_subtitle(f"{sno}. 주요 출원인 대표 특허", page_break=True))
        P.append(p_empty())
        def _rp0(c):
            return (c.get("rep_patents") or [{}])[0]
        # 피인용·패밀리는 데이터가 있을 때만 컬럼 노출(미제공 시 빈 컬럼 방지)
        has_cit = any(_rp0(c).get("citations") is not None for c in comp["companies"])
        has_fam = any(_rp0(c).get("family") is not None for c in comp["companies"])
        headers = ["순위", "기업", "대표 특허번호", "명칭", "연도"]
        colw = [3, 8, 8, 16, 3]; bc = [True, False, True, False, True]
        if has_cit:
            headers.append("피인용"); colw.append(4); bc.append(True)
        if has_fam:
            headers.append("패밀리"); colw.append(4); bc.append(True)
        data = []
        for c in comp["companies"]:
            rp = _rp0(c)
            row = [c.get("rank", ""), trunc(c.get("name", ""), 18), fmt_patent_no(rp.get("number", "")),
                   trunc(rp.get("title", ""), 40), rp.get("year", "") or ""]
            if has_cit:
                row.append(rp.get("citations") if rp.get("citations") is not None else "")
            if has_fam:
                row.append(rp.get("family") if rp.get("family") is not None else "")
            data.append(row)
        P.append(make_table(headers, data, colw, body_center=bc))
        _bcols = (["피인용"] if has_cit else []) + (["패밀리"] if has_fam else [])
        cap_basis = ("·".join(_bcols) + " 기준") if _bcols else "출원인별 대표 특허"
        P.append(p_caption(f"〈표 3-1〉 주요 출원인별 대표 특허 ({cap_basis})"))
        # 상세 프로파일
        sno += 1
        P.append(p_subtitle(f"{sno}. 주요 출원인 상세 프로파일", page_break=True))
        P.append(p_empty())
        for c in comp["companies"]:
            tags = []
            if c.get("positioning"): tags.append(c["positioning"])
            if c.get("momentum"): tags.append(f"모멘텀 {c['momentum']}")
            head = f"{c.get('rank')}. {c.get('name')}  ({c.get('count')}건 · {(c.get('share') or 0)*100:.1f}%)"
            if tags:
                head += "   [" + " · ".join(tags) + "]"
            P.append(p_text(head, cp=CP_CAPTION))
            P += bullets(c.get("profile"))
            P.append(p_empty())
    else:
        P.append(p_empty()); P.append(p_text("경쟁사 분석이 수행되지 않았습니다.", cp=CP_BODY))

    # ---- 4. 정성분석 ----
    P.append(chapter_header("4", "정성분석"))
    ql = m.get("qualitative") or {}; qc = ql.get("charts", {}); fno = 0; any_q = False
    for key, label in [("tech_flow", "기술흐름도"), ("os_matrix", "O/S Matrix"),
                       ("contour_ipc", "특허맵 — IPC 기술분류 등고선"),
                       ("contour_tech", "특허맵 — 기술주제(키워드) 등고선")]:
        node = ql.get(key)
        if not node:
            continue
        any_q = True; fno += 1
        title = node.get("title", label)
        blk = figure(reg, f"{fno}. {title}", qc.get(key), f"〈그림 4-{fno}〉 {title}", node.get("bullets"),
                     page_break=(fno > 1))
        # 핫스팟/화이트스페이스 보조 텍스트는 불릿 뒤 empty 직전에 삽입
        extra = []
        if key.startswith("contour"):
            if node.get("hotspots"):
                extra.append(p_bullet("핫스팟 · " + ", ".join(h.get("ipc") or h.get("term") or "" for h in node["hotspots"])))
            if node.get("whitespace"):
                extra.append(p_bullet("White Space 후보 · " + ", ".join("/".join(w.get("near_ipc") or []) for w in node["whitespace"])))
        if extra:
            blk = blk[:-1] + extra + [blk[-1]]
        P += blk

    # 공백기술 & 진입 전략 (White Space 종합)
    wss = m.get("whitespace_strategy")
    if wss and wss.get("opportunities"):
        any_q = True
        P.append(p_subtitle(wss.get("title", "공백기술 & 진입 전략"), page_break=False))
        P.append(p_empty())
        if wss.get("intro"):
            P.append(p_text(_strip_md(wss["intro"]), cp=CP_BODY)); P.append(p_empty())
        headers = ["순위", "공백 조합 (목적×수단)", "근거", "진입 전략"]
        data = [[op.get("rank", ""), _strip_md(op.get("combo", "")), _strip_md(op.get("evidence", "")),
                 _strip_md(op.get("strategy", ""))] for op in wss["opportunities"]]
        P.append(make_table(headers, data, [3, 12, 12, 16], body_center=[True, False, False, False]))
        P.append(p_caption("〈표 4-1〉 우선 공백기술 및 연구부서 진입 전략"))
        if wss.get("contour_notes"):
            P.append(p_empty()); P.append(p_text("특허맵 등고선 기반 추가 공백", cp=CP_CAPTION))
            P += bullets(wss["contour_notes"], labels=False)

    if not any_q:
        P.append(p_empty()); P.append(p_text("정성분석이 수행되지 않았습니다.", cp=CP_BODY))

    # ---- 5. 핵심특허 ----
    P.append(chapter_header("5", "핵심특허"))
    core = m.get("core") or []
    if core:
        P.append(p_empty())
        P.append(p_subtitle("1. 핵심특허 종합", page_break=False))
        P.append(p_empty())
        headers = ["순위", "특허번호", "명칭", "출원인", "연도"]
        data = []
        for c in core:
            data.append([c.get("rank", ""), trunc(fmt_patent_no(c.get("number", "")), 22),
                         trunc(c.get("title", ""), 60), trunc(c.get("applicant", ""), 28),
                         c.get("year", "") or ""])
        P.append(make_table(headers, data, [3, 8, 20, 8, 3],
                            body_center=[True, True, False, False, True]))
        P.append(p_caption(f"〈표 5-1〉 정량 스코어링·AI 검토 기반 핵심특허 Top {len(core)}"))
        P.append(p_empty())
        reasons = [c for c in core if c.get("reason")]
        if reasons:
            P.append(p_subtitle("2. 핵심특허 선정 근거", page_break=True))
            P.append(p_empty())
            for c in reasons:
                P.append(p_label_bullet(f"{c.get('rank')}위 ({fmt_patent_no(c.get('number'))})", c["reason"]))
    else:
        P.append(p_empty()); P.append(p_text("핵심특허 선별이 수행되지 않았습니다.", cp=CP_BODY))

    # ---- 참고문헌 (기술·시장 분석 출처) — 맨 뒤. 부록은 표시하지 않는다 ----
    refs = mk.get("references") or mk.get("sources") or []
    if refs:
        P.append(chapter_header(None, "참고문헌  References"))
        P.append(p_empty())
        for i, r in enumerate(refs, 1):
            P.append(p_text(f"[{i}]  {r}", cp=CP_BODY))

    return P


# ================= 메인: 템플릿 조립 =================
def main():
    if len(sys.argv) < 2:
        sys.exit("Usage: python _build_hwpx.py <manifest.json> [출력.hwpx]")
    manifest_path = Path(sys.argv[1]).resolve()
    with open(manifest_path, encoding="utf-8") as f:
        m = json.load(f)
    out_hwpx = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else (manifest_path.parent.parent / "IP_Landscape_Report.hwpx")

    if not Path(TEMPLATE).exists():
        sys.exit(f"[hwpx] 템플릿을 찾을 수 없습니다: {TEMPLATE}")

    work = manifest_path.parent / "_hwpx_build"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    with zipfile.ZipFile(TEMPLATE) as z:
        z.extractall(work)

    reg = ImageRegistry()
    body_paras = build_body(m, reg)

    # 이미지 BinData 복사
    bindata = work / "BinData"
    bindata.mkdir(exist_ok=True)
    for iid, src in reg.items:
        try:
            shutil.copy2(src, bindata / f"{iid}.png")
        except Exception as e:
            print(f"[hwpx] WARN 이미지 복사 실패 {iid}: {e}")

    # content.hpf 매니페스트: 사용한 image2.. 등록 (image1은 템플릿에 존재)
    hpf_path = work / "Contents" / "content.hpf"
    hpf = hpf_path.read_text(encoding="utf-8")
    items = ""
    for iid, _ in reg.items:
        if iid != "image1" and f'id="{iid}"' not in hpf:
            items += f'<opf:item id="{iid}" href="BinData/{iid}.png" media-type="image/png" isEmbeded="1"/>'
    if items:
        hpf = hpf.replace('<opf:item id="section0"', items + '<opf:item id="section0"', 1)
    hpf_path.write_text(hpf, encoding="utf-8")

    # header.xml: 표용 borderFill 주입
    hdr_path = work / "Contents" / "header.xml"
    hdr_path.write_text(inject_borderfills(hdr_path.read_text(encoding="utf-8")), encoding="utf-8")

    # section0.xml 재작성: secPr 보존(첫 문단에서 장헤더 표만 제거) + 새 본문
    sec_path = work / "Contents" / "section0.xml"
    sec_xml = sec_path.read_text(encoding="utf-8")
    decl_end = sec_xml.find("?>") + 2
    xml_decl = sec_xml[:decl_end]
    hs_start = sec_xml.find("<hs:sec", decl_end)
    hs_open = sec_xml[hs_start:sec_xml.find(">", hs_start) + 1]

    # 첫 <hp:p>(secPr 포함) 깊이 추적 추출
    start = sec_xml.find("<hp:p ", hs_start)
    p_open = re.compile(r'<hp:p[\s>]'); depth = 0; pos = start; end = None
    while pos < len(sec_xml):
        om = p_open.search(sec_xml, pos); cp = sec_xml.find("</hp:p>", pos)
        if cp == -1:
            break
        op = om.start() if om else len(sec_xml)
        if op < cp:
            depth += 1; pos = op + 5
        else:
            depth -= 1
            if depth == 0:
                end = cp + len("</hp:p>"); break
            pos = cp + len("</hp:p>")
    if end is None:
        raise RuntimeError("section0.xml 첫 문단 파싱 실패")
    first_para = sec_xml[start:end]
    # 첫 문단의 장헤더 표 제거(secPr/colPr은 유지) → 표지 첫 문단
    first_para_clean = re.sub(r'<hp:tbl .*?</hp:tbl>', '', first_para, flags=re.S)

    new_section0 = (xml_decl + hs_open + first_para_clean + "\n"
                    + "\n".join(body_paras) + "\n</hs:sec>")
    sec_path.write_text(new_section0, encoding="utf-8")

    # ZIP 재압축: mimetype 첫 엔트리·무압축
    out_hwpx.parent.mkdir(parents=True, exist_ok=True)
    if out_hwpx.exists():
        out_hwpx.unlink()
    with zipfile.ZipFile(out_hwpx, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("mimetype", (work / "mimetype").read_text(encoding="utf-8"), compress_type=zipfile.ZIP_STORED)
        for p in sorted(work.rglob("*")):
            if p.is_file() and p.name != "mimetype":
                z.write(p, str(p.relative_to(work)).replace("\\", "/"))

    shutil.rmtree(work, ignore_errors=True)
    print(f"[ok] HWPX 생성 완료 → {out_hwpx}  (이미지 {len(reg.items)}개, {out_hwpx.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
