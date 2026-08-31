# -*- coding: utf-8 -*-
"""
Stage C: Assemble Quality_report.hwpx from template + chart PNGs + bullets.
Usage: python _gen_quality_report.py <input_dir>
"""
import sys, os, json, shutil, zipfile, re, html
from pathlib import Path
from PIL import Image

# Template: use patent-trend's template (shared)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_TREND_DIR = os.path.join(os.path.dirname(_SCRIPT_DIR), "patent-trend")
TEMPLATE = os.environ.get("HWPX_TEMPLATE", os.path.join(_TREND_DIR, "양식.hwpx"))

CHART_IDS = ["q1", "q2", "q3", "q4", "q5"]
CHART_LABELS = {
    "q1": ("1. 연도별 기술흐름도", "<그림 5-1> 연도별 기술흐름도"),
    "q2": ("2. O/S Matrix 전체 현황", "<그림 5-2> O/S Matrix 전체 현황"),
    "q3": ("3. O/S Matrix 구간별 변화", "<그림 5-3> O/S Matrix 구간별 변화"),
    "q4": ("4. O/S Matrix 세부 전체 현황", "<그림 5-4> O/S Matrix 세부 전체 현황"),
    "q5": ("5. O/S Matrix 세부 구간별 변화", "<그림 5-5> O/S Matrix 세부 구간별 변화"),
}

def log(msg):
    print(f"[report] {msg}", flush=True)

def xml_escape(text):
    return html.escape(text, quote=False)

def get_png_info(png_path):
    with Image.open(png_path) as im:
        return im.width, im.height

# ---- HWPX XML builders (same style IDs as patent-trend) ----
def make_empty_para():
    return (
        '<hp:p id="2147483648" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
        '<hp:run charPrIDRef="16"/>'
        '</hp:p>'
    )

def make_subtitle_para(text, page_break=False):
    pb = "1" if page_break else "0"
    t = xml_escape(text)
    return (
        f'<hp:p id="2147483648" paraPrIDRef="0" styleIDRef="0" pageBreak="{pb}" columnBreak="0" merged="0">'
        f'<hp:run charPrIDRef="17"><hp:t>{t}</hp:t></hp:run>'
        f'</hp:p>'
    )

def make_image_para(image_id, px_w, px_h):
    display_w = 39776
    display_h = int(display_w * px_h / px_w)
    org_w = int(px_w * 7200 / 96)
    org_h = int(px_h * 7200 / 96)
    dim_w = org_w
    dim_h = org_h
    center_x = display_w // 2
    center_y = display_h // 2
    return (
        f'<hp:p id="2147483648" paraPrIDRef="24" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
        f'<hp:run charPrIDRef="16">'
        f'<hp:pic id="2137722595" zOrder="1" numberingType="PICTURE" textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" lock="0" dropcapstyle="None" href="" groupLevel="0" instid="1063980772" reverse="0">'
        f'<hp:offset x="0" y="0"/>'
        f'<hp:orgSz width="{org_w}" height="{org_h}"/>'
        f'<hp:curSz width="{display_w}" height="{display_h}"/>'
        f'<hp:flip horizontal="0" vertical="0"/>'
        f'<hp:rotationInfo angle="0" centerX="{center_x}" centerY="{center_y}" rotateimage="1"/>'
        f'<hp:renderingInfo>'
        f'<hc:transMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/>'
        f'<hc:scaMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/>'
        f'<hc:rotMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/>'
        f'</hp:renderingInfo>'
        f'<hc:img binaryItemIDRef="{image_id}" bright="0" contrast="0" effect="REAL_PIC" alpha="0"/>'
        f'<hp:imgRect>'
        f'<hc:pt0 x="0" y="0"/><hc:pt1 x="{org_w}" y="0"/><hc:pt2 x="{org_w}" y="{org_h}"/><hc:pt3 x="0" y="{org_h}"/>'
        f'</hp:imgRect>'
        f'<hp:imgClip left="0" right="{dim_w}" top="0" bottom="{dim_h}"/>'
        f'<hp:inMargin left="0" right="0" top="0" bottom="0"/>'
        f'<hp:imgDim dimwidth="{dim_w}" dimheight="{dim_h}"/>'
        f'<hp:effects/>'
        f'<hp:sz width="{display_w}" widthRelTo="ABSOLUTE" height="{display_h}" heightRelTo="ABSOLUTE" protect="0"/>'
        f'<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="0" allowOverlap="0" holdAnchorAndSO="0" vertRelTo="PARA" horzRelTo="PARA" vertAlign="TOP" horzAlign="LEFT" vertOffset="0" horzOffset="0"/>'
        f'<hp:outMargin left="0" right="0" top="0" bottom="0"/>'
        f'<hp:shapeComment></hp:shapeComment>'
        f'</hp:pic>'
        f'<hp:t/></hp:run>'
        f'</hp:p>'
    )

def make_caption_para(text):
    t = xml_escape(text)
    return (
        f'<hp:p id="2147483648" paraPrIDRef="23" styleIDRef="25" pageBreak="0" columnBreak="0" merged="0">'
        f'<hp:run charPrIDRef="12"><hp:t>{t}</hp:t></hp:run>'
        f'</hp:p>'
    )

def make_bullet_para(text):
    t = xml_escape(text)
    return (
        f'<hp:p id="2147483648" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
        f'<hp:run charPrIDRef="16"><hp:t>{t}</hp:t></hp:run>'
        f'</hp:p>'
    )

def make_chapter_header(chapter_num, chapter_title):
    t_title = xml_escape(chapter_title)
    return (
        f'<hp:p id="2147483648" paraPrIDRef="22" styleIDRef="22" pageBreak="1" columnBreak="0" merged="0">'
        f'<hp:run charPrIDRef="7">'
        f'<hp:tbl id="2137722594" zOrder="0" numberingType="TABLE" textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" lock="0" dropcapstyle="None" pageBreak="CELL" repeatHeader="1" rowCnt="1" colCnt="2" cellSpacing="0" borderFillIDRef="4" noAdjust="0">'
        f'<hp:sz width="48756" widthRelTo="ABSOLUTE" height="2350" heightRelTo="ABSOLUTE" protect="0"/>'
        f'<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1" allowOverlap="0" holdAnchorAndSO="0" vertRelTo="PARA" horzRelTo="PARA" vertAlign="TOP" horzAlign="LEFT" vertOffset="0" horzOffset="0"/>'
        f'<hp:outMargin left="0" right="0" top="0" bottom="0"/>'
        f'<hp:inMargin left="283" right="283" top="425" bottom="425"/>'
        f'<hp:tr>'
        f'<hp:tc name="" header="0" hasMargin="0" protect="0" editable="0" dirty="0" borderFillIDRef="5">'
        f'<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER" linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">'
        f'<hp:p id="2147483648" paraPrIDRef="20" styleIDRef="23" pageBreak="0" columnBreak="0" merged="0">'
        f'<hp:run charPrIDRef="8"><hp:t>{chapter_num}</hp:t></hp:run>'
        f'</hp:p>'
        f'</hp:subList>'
        f'<hp:cellAddr colAddr="0" rowAddr="0"/><hp:cellSpan colSpan="1" rowSpan="1"/>'
        f'<hp:cellSz width="5700" height="1866"/>'
        f'<hp:cellMargin left="510" right="510" top="141" bottom="141"/>'
        f'</hp:tc>'
        f'<hp:tc name="" header="0" hasMargin="1" protect="0" editable="0" dirty="0" borderFillIDRef="6">'
        f'<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER" linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">'
        f'<hp:p id="2147483648" paraPrIDRef="21" styleIDRef="24" pageBreak="0" columnBreak="0" merged="0">'
        f'<hp:run charPrIDRef="9"><hp:t>{t_title}</hp:t></hp:run>'
        f'</hp:p>'
        f'</hp:subList>'
        f'<hp:cellAddr colAddr="1" rowAddr="0"/><hp:cellSpan colSpan="1" rowSpan="1"/>'
        f'<hp:cellSz width="43056" height="1866"/>'
        f'<hp:cellMargin left="1417" right="1417" top="425" bottom="425"/>'
        f'</hp:tc>'
        f'</hp:tr>'
        f'</hp:tbl>'
        f'<hp:t/></hp:run>'
        f'</hp:p>'
    )

def build_page_block(chart_id, bullets_data, px_w, px_h, is_first_page=False):
    paras = []
    paras.append(make_subtitle_para(
        bullets_data["subtitle"],
        page_break=(not is_first_page)
    ))
    image_ref = f"image_{chart_id}"
    paras.append(make_image_para(image_ref, px_w, px_h))
    paras.append(make_caption_para(bullets_data["caption"]))
    paras.append(make_empty_para())
    for bullet in bullets_data["bullets"]:
        paras.append(make_bullet_para(bullet))
        paras.append(make_empty_para())
    return "\n".join(paras)


def main():
    if len(sys.argv) < 2:
        print("Usage: python _gen_quality_report.py <input_dir>")
        sys.exit(1)

    input_dir = Path(sys.argv[1])
    assets = input_dir / "_quality_assets"
    work = input_dir / "_hwpx_quality_build"

    # Check template
    if not Path(TEMPLATE).exists():
        sys.exit(f"[report] ERROR: Template not found: {TEMPLATE}")

    # Extract template
    log("extracting template...")
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    with zipfile.ZipFile(TEMPLATE) as z:
        z.extractall(work)

    # Copy chart PNGs to BinData
    log("copying chart PNGs...")
    bindata = work / "BinData"
    for cid in CHART_IDS:
        src = assets / f"chart_{cid}.png"
        if not src.exists():
            log(f"  WARN: chart_{cid}.png not found, skipping")
            continue
        dst = bindata / f"image_{cid}.png"
        shutil.copy2(src, dst)
        log(f"  image_{cid}.png <- chart_{cid}.png")

    # Update manifest (content.hpf)
    log("updating manifest...")
    hpf_path = work / "Contents" / "content.hpf"
    hpf = hpf_path.read_text(encoding="utf-8")
    image_items = ""
    for cid in CHART_IDS:
        image_items += f'<opf:item id="image_{cid}" href="BinData/image_{cid}.png" media-type="image/png" isEmbeded="1"/>'
    hpf = hpf.replace(
        '<opf:item id="section0"',
        image_items + '<opf:item id="section0"'
    )
    hpf_path.write_text(hpf, encoding="utf-8")

    # Rebuild section0.xml
    log("rebuilding section0.xml...")
    sec_path = work / "Contents" / "section0.xml"
    sec_xml = sec_path.read_text(encoding="utf-8")

    # Parse structure (same logic as patent-trend stage C)
    xml_decl_end = sec_xml.find("?>") + 2
    xml_decl = sec_xml[:xml_decl_end]

    hs_sec_start = sec_xml.find("<hs:sec", xml_decl_end)
    hs_sec_tag_end = sec_xml.find(">", hs_sec_start) + 1
    hs_sec_open = sec_xml[hs_sec_start:hs_sec_tag_end]

    # Extract first <hp:p> (contains secPr + header table)
    first_p_start = sec_xml.find("<hp:p ", hs_sec_tag_end)
    depth = 0
    pos = first_p_start
    first_p_end = None
    p_open_re = re.compile(r'<hp:p[\s>]')
    while pos < len(sec_xml):
        open_match = p_open_re.search(sec_xml, pos)
        close_pos = sec_xml.find("</hp:p>", pos)
        if close_pos == -1:
            break
        open_pos = open_match.start() if open_match else len(sec_xml)
        if open_pos < close_pos:
            depth += 1
            pos = open_pos + 5
        else:
            depth -= 1
            if depth == 0:
                first_p_end = close_pos + len("</hp:p>")
                break
            pos = close_pos + len("</hp:p>")
    if first_p_end is None:
        raise RuntimeError("Could not find end of first <hp:p> paragraph")
    first_para = sec_xml[first_p_start:first_p_end]

    # Replace chapter number/title in first_para for chapter 5
    first_para = re.sub(r'(<hp:run charPrIDRef="8"><hp:t>)\d+(</hp:t></hp:run>)',
                        r'\g<1>5\2', first_para)
    first_para = re.sub(r'(<hp:run charPrIDRef="9"><hp:t>)[^<]+(</hp:t></hp:run>)',
                        r'\g<1>정성분석\2', first_para)

    sec_close = "</hs:sec>"

    # Load bullets and build pages
    all_bullets = {}
    for cid in CHART_IDS:
        bp = assets / f"bullets_{cid}.json"
        if bp.exists():
            with open(bp, encoding="utf-8") as f:
                all_bullets[cid] = json.load(f)
        else:
            log(f"  WARN: bullets_{cid}.json not found")

    pages = []
    for idx, cid in enumerate(CHART_IDS):
        if cid not in all_bullets:
            continue
        png_path = assets / f"chart_{cid}.png"
        if not png_path.exists():
            continue
        px_w, px_h = get_png_info(png_path)
        log(f"  page {idx+1}: {all_bullets[cid]['subtitle']}, img={px_w}x{px_h}")
        page_xml = build_page_block(cid, all_bullets[cid], px_w, px_h, is_first_page=(idx == 0))
        pages.append(page_xml)

    # Assemble
    new_section0 = (
        xml_decl
        + hs_sec_open
        + first_para + "\n"
        + make_empty_para() + "\n"
        + "\n".join(pages) + "\n"
        + sec_close
    )
    sec_path.write_text(new_section0, encoding="utf-8")
    log("section0.xml rebuilt")

    # Repackage as HWPX
    log("creating Quality_report.hwpx...")
    output = input_dir / "Quality_report.hwpx"
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
        mimetype_path = work / "mimetype"
        z.writestr("mimetype", mimetype_path.read_text(encoding="utf-8"), compress_type=zipfile.ZIP_STORED)
        for p in sorted(work.rglob("*")):
            if p.is_file() and p.name != "mimetype":
                arcname = str(p.relative_to(work)).replace("\\", "/")
                z.write(p, arcname)

    log(f"DONE: {output}")
    log(f"file size: {output.stat().st_size:,} bytes")

    # Cleanup
    try:
        shutil.rmtree(work)
        log("cleaned up build dir")
    except Exception as e:
        log(f"cleanup warning: {e}")

if __name__ == "__main__":
    main()
