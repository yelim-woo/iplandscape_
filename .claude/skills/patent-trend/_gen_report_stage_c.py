# -*- coding: utf-8 -*-
"""
Stage C: Assemble Trend_report.hwpx from template + PNGs + bullets
Usage: python _gen_report_stage_c.py <input_dir>
"""
import sys, os, json, shutil, zipfile, re, html
from pathlib import Path
from PIL import Image

# Template: same directory as this script (portable across users)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.environ.get("HWPX_TEMPLATE", os.path.join(_SCRIPT_DIR, "양식.hwpx"))

def log(msg):
    print(f"[stage-c] {msg}", flush=True)

def xml_escape(text):
    return html.escape(text, quote=False)

def get_png_info(png_path):
    """Get pixel dimensions of a PNG."""
    with Image.open(png_path) as im:
        return im.width, im.height

# ---- HWPX XML builders ----
# Style IDs extracted from the template section0.xml:
#   Subtitle text:  paraPrIDRef="0" styleIDRef="0" charPrIDRef="17"
#   Image para:     paraPrIDRef="24" styleIDRef="0" charPrIDRef="16"
#   Caption text:   paraPrIDRef="23" styleIDRef="25" charPrIDRef="12"
#   Bullet text:    paraPrIDRef="0" styleIDRef="0" charPrIDRef="16"
#   Empty line:     paraPrIDRef="0" styleIDRef="0" charPrIDRef="16"

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
    """Build an image paragraph.
    HWPUNIT: 1 inch = 7200 units.
    We display images at a fixed width of 39776 units (~5.5 inches) and scale height proportionally.
    """
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

def split_bullet_into_sentences(bullet_text):
    """Split a long bullet text into separate sentence-level lines.
    First line keeps the '○ ' prefix; continuation lines start without it.
    Splits at Korean sentence endings: ~함, ~나타남, ~보임, ~됨, ~있음, ~분석됨 etc.
    followed by '. ' or end of string.
    """
    # Remove leading ○ and space
    text = bullet_text.strip()
    has_marker = text.startswith("○")
    if has_marker:
        text = text[1:].strip()

    # Split at ". " (period+space) which is sentence boundary in Korean report style
    # Also split at "; " (semicolon+space)
    parts = re.split(r'(?<=함|됨|임|음|남|봄)\.\s+', text)
    if len(parts) == 1:
        # Try splitting at ". " generically
        parts = re.split(r'\.\s+', text)

    # If still just 1 part (no split), try splitting at ", " after long segments
    if len(parts) == 1 and len(text) > 80:
        # Split at major clause boundaries: ~며, ~고, ~어서 followed by comma+space
        segments = re.split(r'(?<=며),\s+|(?<=고),\s+', text)
        if len(segments) > 1:
            parts = segments

    lines = []
    for i, part in enumerate(parts):
        part = part.strip()
        if not part:
            continue
        if i == 0 and has_marker:
            lines.append(f"○ {part}")
        else:
            lines.append(f"  {part}")
    return lines if lines else [bullet_text]

def build_page_block(chart_idx, bullets_data, px_w, px_h, is_first_page=False):
    """Build XML paragraphs for one page (subtitle + image + caption + bullets).
    First page does NOT get pageBreak (it follows the header table).
    Pages 2-6 get pageBreak="1" on their first paragraph.
    """
    paras = []
    # subtitle
    paras.append(make_subtitle_para(
        bullets_data["subtitle"],
        page_break=(not is_first_page)
    ))
    # image
    image_id = f"image{chart_idx}"
    paras.append(make_image_para(image_id, px_w, px_h))
    # caption
    paras.append(make_caption_para(bullets_data["caption"]))
    # empty line
    paras.append(make_empty_para())
    # bullets - one bullet = one paragraph (HWP handles line wrapping)
    for bullet in bullets_data["bullets"]:
        paras.append(make_bullet_para(bullet))
        paras.append(make_empty_para())
    return "\n".join(paras)

# ---- Main ----
def main():
    if len(sys.argv) < 2:
        print("Usage: python _gen_report_stage_c.py <input_dir>")
        sys.exit(1)
    input_dir = Path(sys.argv[1])
    assets = input_dir / "_report_assets"
    work = input_dir / "_hwpx_build"

    # C-1: Extract template
    log("extracting template...")
    if not Path(TEMPLATE).exists():
        sys.exit(f"[stage-c] ERROR: Template not found: {TEMPLATE}")
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    with zipfile.ZipFile(TEMPLATE) as z:
        z.extractall(work)

    # C-2: Copy chart PNGs to BinData
    log("copying chart PNGs...")
    bindata = work / "BinData"
    for i in range(1, 11):
        src = assets / f"chart_{i}.png"
        if not src.exists():
            log(f"  WARN: {src.name} not found, skipping")
            continue
        dst = bindata / f"image{i}.png"
        shutil.copy2(src, dst)
        log(f"  image{i}.png <- {src.name}")

    # C-3: Update content.hpf manifest
    log("updating manifest...")
    hpf_path = work / "Contents" / "content.hpf"
    hpf = hpf_path.read_text(encoding="utf-8")
    # Add image2..image6 items after image1
    image_items = ""
    for i in range(2, 11):
        image_items += f'<opf:item id="image{i}" href="BinData/image{i}.png" media-type="image/png" isEmbeded="1"/>'
    hpf = hpf.replace(
        '<opf:item id="section0"',
        image_items + '<opf:item id="section0"'
    )
    hpf_path.write_text(hpf, encoding="utf-8")

    # C-4: Rebuild section0.xml
    log("rebuilding section0.xml...")
    sec_path = work / "Contents" / "section0.xml"
    sec_xml = sec_path.read_text(encoding="utf-8")

    # Parse structure:
    # The file starts with: <?xml ...?><hs:sec xmlns:...>  <hp:p>...</hp:p> <hp:p>... </hs:sec>
    # We need:
    #   1) XML declaration
    #   2) <hs:sec ...> opening tag (with namespaces)
    #   3) First <hp:p> (secPr + header table)
    #   4) Replace remaining paragraphs with our 6 pages

    # 1) Extract XML declaration (<?xml ... ?>)
    xml_decl_end = sec_xml.find("?>") + 2
    xml_decl = sec_xml[:xml_decl_end]

    # 2) Extract <hs:sec ...> opening tag
    hs_sec_start = sec_xml.find("<hs:sec", xml_decl_end)
    hs_sec_tag_end = sec_xml.find(">", hs_sec_start) + 1
    hs_sec_open = sec_xml[hs_sec_start:hs_sec_tag_end]

    # 3) Extract first <hp:p>...</hp:p> (contains secPr + header table with nested <hp:p>)
    #    Must track depth because table cells contain nested <hp:p> tags
    first_p_start = sec_xml.find("<hp:p ", hs_sec_tag_end)
    depth = 0
    pos = first_p_start
    first_p_end = None
    # Use regex to find only <hp:p followed by space/> (not <hp:pic, <hp:pagePr, etc.)
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
    log(f"  first_para length: {len(first_para)} chars")

    sec_close = "</hs:sec>"

    # --- Build chapter header table XML ---
    # Extract the header table from the first paragraph to reuse for chapter 4
    # The first_para contains: secPr + colPr + table("3","출원동향 분석") + lineseg
    # We need to create a version with "4" and "출원인 분석" for chapter 4
    def make_chapter_header(chapter_num, chapter_title):
        """Create a page-break paragraph with a chapter header table."""
        # Reuse the table structure from first_para but change number and title
        # Build a simpler version that matches the template table style
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

    # Load bullets and PNG dimensions for all 10 charts
    all_bullets = {}
    for i in range(1, 11):
        bullets_path = assets / f"bullets_{i}.json"
        if not bullets_path.exists():
            log(f"  WARN: {bullets_path.name} not found, skipping")
            continue
        with open(bullets_path, encoding="utf-8") as f:
            all_bullets[i] = json.load(f)

    # --- Chapter 3: 출원동향 분석 (charts 1,2,3,4,6,7) ---
    ch3_chart_ids = [1, 2, 3, 4, 6, 7]
    ch3_pages = []
    for idx, i in enumerate(ch3_chart_ids):
        if i not in all_bullets:
            continue
        png_path = assets / f"chart_{i}.png"
        if not png_path.exists():
            continue
        px_w, px_h = get_png_info(png_path)
        log(f"  ch3 page {idx+1}: {all_bullets[i]['subtitle']}, img={px_w}x{px_h}")
        page_xml = build_page_block(i, all_bullets[i], px_w, px_h, is_first_page=(idx == 0))
        ch3_pages.append(page_xml)

    # --- Chapter 4: 출원인 분석 (charts 5,8,9,10) ---
    ch4_chart_ids = [5, 8, 9, 10]
    ch4_pages = []
    ch4_header = make_chapter_header("4", "출원인 분석")
    for idx, i in enumerate(ch4_chart_ids):
        if i not in all_bullets:
            continue
        png_path = assets / f"chart_{i}.png"
        if not png_path.exists():
            continue
        px_w, px_h = get_png_info(png_path)
        log(f"  ch4 page {idx+1}: {all_bullets[i]['subtitle']}, img={px_w}x{px_h}")
        # First page of ch4 doesn't get pageBreak (header has it)
        page_xml = build_page_block(i, all_bullets[i], px_w, px_h, is_first_page=(idx == 0))
        ch4_pages.append(page_xml)

    # Assemble new section0.xml
    new_section0 = (
        xml_decl
        + hs_sec_open
        + first_para + "\n"
        + make_empty_para() + "\n"
        + "\n".join(ch3_pages) + "\n"
        + ch4_header + "\n"
        + make_empty_para() + "\n"
        + "\n".join(ch4_pages) + "\n"
        + sec_close
    )

    sec_path.write_text(new_section0, encoding="utf-8")
    log("section0.xml rebuilt")

    # C-5: Repackage as HWPX ZIP
    log("creating Trend_report.hwpx...")
    output = input_dir / "Trend_report.hwpx"
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
        # mimetype MUST be first entry, uncompressed
        mimetype_path = work / "mimetype"
        z.writestr("mimetype", mimetype_path.read_text(encoding="utf-8"), compress_type=zipfile.ZIP_STORED)
        # add all other files
        for p in sorted(work.rglob("*")):
            if p.is_file() and p.name != "mimetype":
                arcname = str(p.relative_to(work)).replace("\\", "/")
                z.write(p, arcname)

    log(f"DONE: {output}")
    log(f"file size: {output.stat().st_size:,} bytes")

    # C-6: Cleanup
    try:
        shutil.rmtree(work)
        log("cleaned up _hwpx_build")
    except Exception as e:
        log(f"cleanup warning: {e}")

if __name__ == "__main__":
    main()
