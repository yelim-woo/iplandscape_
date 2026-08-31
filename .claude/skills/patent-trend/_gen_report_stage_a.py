# -*- coding: utf-8 -*-
"""
Stage A v2: Patent xlsx -> 10 charts PNG + 10 stats JSON  (premium chart design)
Supports any patent DB (WIPS, KIPRIS, USPTO, Espacenet, etc.) via auto column mapping.
Usage: python _gen_report_stage_a.py <input_dir> [--column-map map.json]
"""
import sys, os, glob, json, re
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import matplotlib.ticker as mticker
from matplotlib import rcParams
import platform

def _detect_korean_font():
    system = platform.system()
    if system == "Windows":
        return "Malgun Gothic"
    elif system == "Darwin":
        return "AppleGothic"
    else:
        # Linux: try common Korean fonts
        for name in ["NanumGothic", "NanumBarunGothic", "UnDotum", "DejaVu Sans"]:
            try:
                from matplotlib.font_manager import findfont, FontProperties
                path = findfont(FontProperties(family=name), fallback_to_default=False)
                if path:
                    return name
            except Exception:
                continue
        return "sans-serif"

rcParams["font.family"] = _detect_korean_font()
rcParams["axes.unicode_minus"] = False

# ---------------- config ----------------
FOLDER_TO_COUNTRY = {"한국": "KR", "미국": "US", "일본": "JP", "중국": "CN", "유럽": "EP"}
COUNTRY_NAME  = {"KR": "한국", "US": "미국", "JP": "일본", "CN": "중국", "EP": "유럽"}
COUNTRY_OFFICE = {"KR": "KIPO", "US": "USPTO", "JP": "JPO", "CN": "CNIPA", "EP": "EPO"}

NEEDED_COLS = [
    "국가코드", "출원일", "등록번호", "출원인", "출원인(제2언어)",
    "출원인 대표명화 영문명", "출원인 대표명화 코드",
    "Current IPC Main", "Current IPC All",
    "상태정보[KR,JP,US,EP,CN,CA,AU]",
]

# --- Column auto-mapping: alias table + pattern detectors ---
# Key = lowercase alternative name, Value = standard NEEDED_COLS name
COLUMN_ALIASES = {
    # 출원일
    "출원일자": "출원일", "출원 일자": "출원일", "출원일(국제)": "출원일",
    "출원년월일": "출원일", "application date": "출원일", "filing date": "출원일",
    "filing_date": "출원일", "app date": "출원일", "app_date": "출원일",
    "date of application": "출원일", "date of filing": "출원일",
    "earliest filing date": "출원일", "earliest_filing_date": "출원일",
    # 국가코드
    "국가": "국가코드", "country": "국가코드", "country code": "국가코드",
    "country_code": "국가코드", "국가 코드": "국가코드", "출원국": "국가코드",
    "출원국가": "국가코드", "patent office": "국가코드", "office": "국가코드",
    "authority": "국가코드",
    # 출원인
    "출원인명": "출원인", "applicant": "출원인", "applicant name": "출원인",
    "applicant_name": "출원인", "first applicant": "출원인", "출원인1": "출원인",
    "출원인(대표)": "출원인", "대표출원인": "출원인", "assignee": "출원인",
    "권리자": "출원인", "특허권자": "출원인", "patentee": "출원인",
    "applicants": "출원인", "first named applicant": "출원인",
    # 출원인(제2언어)
    "출원인제2언어": "출원인(제2언어)", "출원인 제2언어": "출원인(제2언어)",
    "applicant (2nd lang)": "출원인(제2언어)",
    # 출원인 영문명
    "출원인영문명": "출원인 대표명화 영문명", "출원인 영문명": "출원인 대표명화 영문명",
    "applicant english name": "출원인 대표명화 영문명", "출원인(영문)": "출원인 대표명화 영문명",
    "영문출원인": "출원인 대표명화 영문명",
    # IPC
    "ipc": "Current IPC Main", "ipc code": "Current IPC Main",
    "ipc분류": "Current IPC Main", "ipc 분류": "Current IPC Main",
    "main ipc": "Current IPC Main", "ipc코드": "Current IPC Main",
    "ipc_code": "Current IPC Main", "ipc(대표)": "Current IPC Main",
    "대표ipc": "Current IPC Main", "ipc분류(대표)": "Current IPC Main",
    "international patent classification": "Current IPC Main",
    "ipc classification": "Current IPC Main",
    "ipc all": "Current IPC All", "ipc전체": "Current IPC All",
    "ipc 전체": "Current IPC All", "all ipc": "Current IPC All",
    "ipc(전체)": "Current IPC All",
    # 등록번호
    "registration no": "등록번호", "registration number": "등록번호",
    "reg no": "등록번호", "reg_no": "등록번호", "patent no": "등록번호",
    "patent number": "등록번호", "grant number": "등록번호",
    # 상태정보
    "상태": "상태정보[KR,JP,US,EP,CN,CA,AU]", "법적상태": "상태정보[KR,JP,US,EP,CN,CA,AU]",
    "legal status": "상태정보[KR,JP,US,EP,CN,CA,AU]",
    "status": "상태정보[KR,JP,US,EP,CN,CA,AU]",
    "patent status": "상태정보[KR,JP,US,EP,CN,CA,AU]",
    "상태정보": "상태정보[KR,JP,US,EP,CN,CA,AU]",
}

def _detect_date_column(series):
    """Detect if a column contains date-like values (YYYYMMDD, YYYY-MM-DD, etc.)."""
    sample = series.dropna().head(50).astype(str)
    if len(sample) == 0:
        return False
    date_pat = re.compile(r"^\d{4}[-/.]?\d{2}[-/.]?\d{2}")
    match_count = sum(1 for v in sample if date_pat.match(v.strip()))
    return match_count / len(sample) > 0.5

def _detect_country_code_column(series):
    """Detect if a column contains 2-letter country codes."""
    sample = series.dropna().head(50).astype(str)
    if len(sample) == 0:
        return False
    known = {"KR","US","JP","CN","EP","WO","DE","FR","GB","CA","AU","TW","IN","BR","RU"}
    match_count = sum(1 for v in sample if v.strip().upper() in known)
    return match_count / len(sample) > 0.5

def _detect_ipc_column(series):
    """Detect if a column contains IPC classification codes."""
    sample = series.dropna().head(50).astype(str)
    if len(sample) == 0:
        return False
    ipc_pat = re.compile(r"[A-H]\d{2}[A-Z]")
    match_count = sum(1 for v in sample if ipc_pat.search(v.strip().upper()))
    return match_count / len(sample) > 0.3

def _detect_registration_number(series):
    """Detect if a column contains patent registration/grant numbers."""
    sample = series.dropna().head(50).astype(str)
    if len(sample) == 0:
        return False
    reg_pat = re.compile(r"(\d{7,}|[\dA-Z]{2,3}[-/]\d{5,})")
    match_count = sum(1 for v in sample if reg_pat.search(v.strip()))
    return match_count / len(sample) > 0.3

def auto_map_columns(df, explicit_map=None):
    """Auto-map column names to standard NEEDED_COLS.
    Priority: exact match (no rename) > explicit_map > alias > pattern detection.
    Returns renamed DataFrame. Original WIPS columns pass through untouched.
    """
    rename_map = {}
    # Columns already matching NEEDED_COLS exactly — no rename needed
    mapped_targets = set(c for c in NEEDED_COLS if c in df.columns)

    # 1) Explicit mapping from Claude/user (--column-map JSON)
    if explicit_map:
        for src, dst in explicit_map.items():
            if src in df.columns and dst not in mapped_targets:
                rename_map[src] = dst
                mapped_targets.add(dst)

    # 2) Alias matching (case-insensitive)
    for col in df.columns:
        if col in rename_map or col in NEEDED_COLS:
            continue
        key = col.strip().lower()
        if key in COLUMN_ALIASES:
            target = COLUMN_ALIASES[key]
            if target not in mapped_targets:
                rename_map[col] = target
                mapped_targets.add(target)

    # 3) Pattern-based detection for critical columns still missing
    missing = [c for c in NEEDED_COLS if c not in mapped_targets]
    if missing:
        unmapped = [c for c in df.columns if c not in rename_map and c not in NEEDED_COLS]

        # 3a) Date → 출원일: prefer columns with filing-related keywords
        if "출원일" in missing:
            filing_kw = ["출원", "filing", "application", "app_date"]
            candidates = [c for c in unmapped if any(k in c.lower() for k in filing_kw)]
            if not candidates:
                candidates = unmapped  # fallback: any column
            for col in candidates:
                if _detect_date_column(df[col]):
                    rename_map[col] = "출원일"
                    mapped_targets.add("출원일")
                    unmapped = [c for c in unmapped if c != col]
                    break

        # 3b) Country code → 국가코드
        if "국가코드" not in mapped_targets:
            for col in unmapped:
                if _detect_country_code_column(df[col]):
                    rename_map[col] = "국가코드"
                    mapped_targets.add("국가코드")
                    unmapped = [c for c in unmapped if c != col]
                    break

        # 3c) IPC → Current IPC Main
        if "Current IPC Main" not in mapped_targets and "Current IPC All" not in mapped_targets:
            for col in unmapped:
                if _detect_ipc_column(df[col]):
                    rename_map[col] = "Current IPC Main"
                    mapped_targets.add("Current IPC Main")
                    unmapped = [c for c in unmapped if c != col]
                    break

        # 3d) Registration number → 등록번호
        if "등록번호" not in mapped_targets:
            for col in unmapped:
                if _detect_registration_number(df[col]):
                    rename_map[col] = "등록번호"
                    mapped_targets.add("등록번호")
                    unmapped = [c for c in unmapped if c != col]
                    break

    if rename_map:
        log(f"  column auto-mapping applied: {rename_map}")
        df = df.rename(columns=rename_map)

    return df

# --- 출원인 정규화용 상수 ---
# 제거할 법인 접미사 (대소문자 무시, 순서: 긴 것 먼저)
CORP_SUFFIXES = [
    # 한글
    r"주식회사", r"\(주\)", r"유한회사", r"\(유\)", r"재단법인", r"사단법인",
    r"학교법인", r"산학협력단", r"의료법인",
    # 영문 (긴 것 먼저)
    r"CORPORATION", r"CORP\.", r"CORP",
    r"COMPANY\s+LIMITED", r"COMPANY,?\s*LTD\.?", r"CO\.\s*,?\s*LTD\.?",
    r"CO\.,?\s*LTD\.?", r"CO\.\s*LTD\.?", r"CO\s*LTD\.?",
    r"LIMITED", r"LTD\.?",
    r"INCORPORATED", r"INC\.?",
    r"L\.?L\.?C\.?", r"L\.?L\.?P\.?", r"L\.?P\.?",
    r"PLC\.?", r"GMBH", r"AG", r"S\.?A\.?", r"B\.?V\.?",
    r"PTY\.?", r"PTE\.?",
]
# 컴파일된 접미사 패턴 (문자열 끝에서 매칭)
_SUFFIX_PATTERNS = [re.compile(r"[\s,]*\b" + s + r"[\s.,]*$", re.IGNORECASE) for s in CORP_SUFFIXES]

def log(msg):
    print(f"[stage-a] {msg}", flush=True)

_HDR_HINTS = ["발명의명칭", "발명의 명칭", "출원번호", "출원일", "출원인", "ipc", "title",
              "applicant", "filing date", "application number", "요약", "abstract", "공개번호", "등록번호", "피인용"]


def _find_header_row(path, engine):
    try:
        probe = pd.read_excel(path, engine=engine, header=None, nrows=25)
    except Exception:
        return 0
    best, best_hits = 0, 0
    for i in range(len(probe)):
        cells = [str(v).strip().lower() for v in probe.iloc[i].tolist()]
        nn = sum(1 for c in cells if c and c != "nan")
        hits = sum(1 for c in cells for h in _HDR_HINTS if h in c)
        if hits > best_hits and nn >= 4:
            best, best_hits = i, hits
        if best_hits >= 4:
            break
    return best if best_hits >= 2 else 0


def safe_read_excel(path, explicit_map=None):
    # 손상 스타일(KIPRIS 등)·헤더 오프셋 대응: openpyxl 실패 시 calamine 폴백 + 헤더 자동탐지
    df = None
    last = None
    for eng in ("openpyxl", "calamine"):
        try:
            if eng == "calamine":
                try:
                    import python_calamine  # noqa
                except ImportError:
                    import subprocess, sys as _sys
                    subprocess.check_call([_sys.executable, "-m", "pip", "install", "-q", "python-calamine"])
            hr = _find_header_row(path, eng)
            df = pd.read_excel(path, engine=eng, header=hr)
            break
        except Exception as e:
            last = e
    if df is None:
        log(f"WARN read fail: {path} ({last})")
        return pd.DataFrame()
    # auto-map column names (exact match > alias > pattern detection)
    df = auto_map_columns(df, explicit_map)
    # keep only the columns we need (if present)
    keep = [c for c in NEEDED_COLS if c in df.columns]
    return df[keep].copy() if keep else pd.DataFrame()

def extract_year(val):
    if pd.isna(val):
        return None
    s = str(val).strip()
    m = re.match(r"^(\d{4})", s)
    if m:
        y = int(m.group(1))
        return y if 1970 <= y <= 2050 else None
    return None

def normalize_country(val, folder_country):
    if pd.isna(val) or not str(val).strip():
        return folder_country
    s = str(val).strip().upper()
    # WIPS sometimes uses "WO" for PCT, keep as is but mapping
    if s in ("KR","US","JP","CN","EP","WO"):
        return s
    return folder_country

def ipc_subclass(codes):
    """Extract IPC subclass (4 chars like B25J) from a cell that may contain multiple codes."""
    if pd.isna(codes):
        return []
    s = str(codes)
    parts = re.split(r"[;,|\n]+", s)
    out = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        # IPC like "B25J 9/00" or "B25J9/00" -> "B25J"
        m = re.match(r"^([A-H]\d{2}[A-Z])", p.upper())
        if m:
            out.append(m.group(1))
    return list(dict.fromkeys(out))  # dedup keep order

def _strip_corp_suffix(name):
    """Remove corporate suffixes from a name."""
    result = name
    for pat in _SUFFIX_PATTERNS:
        result = pat.sub("", result)
    # clean up trailing/leading punctuation and whitespace
    result = re.sub(r"[\s,.\-]+$", "", result)
    result = re.sub(r"^[\s,.\-]+", "", result)
    result = re.sub(r"\s+", " ", result).strip()
    return result if result else name  # fallback to original if everything stripped

def normalize_applicant(val):
    """Extract and normalize the first applicant name."""
    if pd.isna(val):
        return None
    s = str(val).strip()
    if not s:
        return None
    # take first applicant if multiple separated by | or ;
    parts = re.split(r"[|;]", s)
    name = parts[0].strip()
    name = re.sub(r"\s+", " ", name)
    if not name:
        return None
    # strip corporate suffixes
    name = _strip_corp_suffix(name)
    return name.upper() if name else None  # uppercase for dedup

def normalize_applicant_with_en(row):
    """Normalize applicant using both Korean and English name columns.
    Priority: 출원인 대표명화 영문명 > 출원인(제2언어) > 출원인
    This ensures Korean and English variants map to the same canonical name.
    """
    # 1) Try standardized English name first (most consistent across WIPS)
    for col in ["출원인 대표명화 영문명", "출원인(제2언어)"]:
        val = row.get(col)
        if pd.notna(val) and str(val).strip():
            en_name = str(val).strip()
            # take first if multiple
            en_name = re.split(r"[|;]", en_name)[0].strip()
            en_name = re.sub(r"\s+", " ", en_name)
            en_name = _strip_corp_suffix(en_name)
            if en_name and len(en_name) >= 2:
                return en_name.upper()
    # 2) Fallback to primary 출원인 column
    val = row.get("출원인")
    return normalize_applicant(val)

def build_applicant_merge_map(names, top_n=300):
    """Build a mapping to merge similar applicant names.
    Only considers top_n most frequent names for O(n²) comparison to keep fast.
    Handles cases like 'FANUC' appearing as both 'FANUC CORPORATION' and 'FANUC LTD'
    after suffix stripping both become 'FANUC'.
    """
    from collections import Counter
    counts = Counter(names)
    # Only compare top N names (covers >95% of patents, keeps O(n²) manageable)
    sorted_names = [name for name, _ in counts.most_common(top_n)]

    merge_map = {}
    used = set()

    for i, name in enumerate(sorted_names):
        if name in used:
            continue
        for j in range(i + 1, len(sorted_names)):
            other = sorted_names[j]
            if other in used:
                continue
            if len(name) <= 3 or len(other) <= 3:
                continue
            shorter, longer = (name, other) if len(name) <= len(other) else (other, name)
            if longer.startswith(shorter + " ") or longer.startswith(shorter + "-"):
                # Merge lower-count into higher-count
                if counts[name] >= counts[other]:
                    merge_map[other] = name
                    used.add(other)
                else:
                    merge_map[name] = other
                    used.add(name)
                    break
    return merge_map

def is_granted(row):
    # "등록번호" present -> granted
    rn = row.get("등록번호")
    if pd.notna(rn) and str(rn).strip():
        return True
    # fallback to 상태정보
    st = row.get("상태정보[KR,JP,US,EP,CN,CA,AU]")
    if pd.notna(st):
        s = str(st)
        if "등록" in s:
            return True
    return False

# ---------------- load ----------------
def load_all(input_dir, explicit_map=None):
    files = glob.glob(os.path.join(input_dir, "**/*.xlsx"), recursive=True)
    log(f"found {len(files)} xlsx files")
    dfs = []
    for i, f in enumerate(files, 1):
        # country from parent folder
        parent = os.path.basename(os.path.dirname(f))
        folder_country = FOLDER_TO_COUNTRY.get(parent, None)
        df = safe_read_excel(f, explicit_map)
        if df.empty:
            continue
        if "국가코드" not in df.columns:
            df["국가코드"] = folder_country
        else:
            df["국가코드"] = df["국가코드"].apply(lambda v: normalize_country(v, folder_country))
        df["_folder_country"] = folder_country
        dfs.append(df)
        if i % 20 == 0 or i == len(files):
            log(f"  loaded {i}/{len(files)} ({len(df)} rows, total so far: {sum(len(x) for x in dfs)})")
    if not dfs:
        raise SystemExit("No xlsx data loaded.")
    all_df = pd.concat(dfs, ignore_index=True, sort=False)
    log(f"total rows: {len(all_df)}")
    return all_df

def preprocess(df):
    df = df.copy()
    df["year"] = df["출원일"].apply(extract_year)
    # apply country normalization final
    df["country"] = df["국가코드"].fillna(df.get("_folder_country"))
    df["country"] = df["country"].apply(lambda v: v if v in ("KR","US","JP","CN","EP","WO") else None)
    # keep only rows with year and country
    df = df[df["year"].notna() & df["country"].notna()].copy()
    df["year"] = df["year"].astype(int)
    # applicant — advanced normalization
    if "출원인" in df.columns:
        df["applicant_norm"] = df.apply(normalize_applicant_with_en, axis=1)
        # build merge map for similar names and apply
        valid_names = df["applicant_norm"].dropna().tolist()
        if valid_names:
            merge_map = build_applicant_merge_map(valid_names)
            if merge_map:
                log(f"  applicant merge map: {len(merge_map)} names merged")
                df["applicant_norm"] = df["applicant_norm"].map(lambda x: merge_map.get(x, x) if x else x)
    else:
        df["applicant_norm"] = None
    # IPC subclass list per row
    ipc_col = "Current IPC Main" if "Current IPC Main" in df.columns else ("Current IPC All" if "Current IPC All" in df.columns else None)
    if ipc_col:
        df["ipc_list"] = df[ipc_col].apply(ipc_subclass)
    else:
        df["ipc_list"] = [[] for _ in range(len(df))]
    # granted
    df["is_granted"] = df.apply(is_granted, axis=1)
    return df

# ---------------- charts v2 (premium design) ----------------
FIG_W_IN, FIG_H_IN, DPI = 16, 9, 110  # 1760x990 at dpi=110

# 절제된 에디토리얼 팔레트(차분한 채도) — 엑셀 기본색 느낌을 피한다.
V2_GRID = "#ededed"
V2_TICK = "#6b6b6b"
V2_COUNTRY_COLOR = {
    "KR": "#2E5B8A", "US": "#B5483D", "JP": "#3F8E7E", "CN": "#C9A24B", "EP": "#7E5A8C"
}
V2_IPC_PALETTE = ["#2E4A6B", "#B5483D", "#3F8E7E", "#7E5A8C", "#C9A24B"]
V2_APPLICANT_COUNTRY_COLOR = {
    "KR": "#2E5B8A", "JP": "#3F8E7E", "CN": "#C9A24B", "US": "#B5483D"
}

def _new_fig():
    fig, ax = plt.subplots(figsize=(FIG_W_IN, FIG_H_IN), dpi=DPI)
    fig.set_facecolor("#ffffff")
    ax.set_facecolor("#ffffff")
    return fig, ax

def _style_ax(ax):
    """에디토리얼 스타일: 스파인 제거 + 옅은 실선 가로그리드 + 얇은 베이스라인 + 눈금 마크 제거."""
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.grid(axis="y", color=V2_GRID, linewidth=0.9, zorder=0)
    ax.set_axisbelow(True)
    ax.spines["bottom"].set_visible(True)
    ax.spines["bottom"].set_color(V2_GRID); ax.spines["bottom"].set_linewidth(1.0)
    ax.tick_params(labelsize=13, colors=V2_TICK, length=0)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x):,}"))

def _style_ax_x_grid(ax):
    """가로 막대용 — 세로 그리드만 옅게."""
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.grid(axis="x", color=V2_GRID, linewidth=0.9, zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(labelsize=13, colors=V2_TICK, length=0)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x):,}"))

def _hlabel(ax, text):
    """y축 단위 라벨을 '가로'로 plot 상단 좌측에 표기(한글 세로쓰기 방지)."""
    ax.set_ylabel("")
    ax.annotate(text, xy=(0.0, 1.02), xycoords="axes fraction", ha="left", va="bottom",
                fontsize=13, color="#666666", annotation_clip=False)


def _mark_incomplete(ax, years, note="최근(공개 시차)"):
    """시계열 마지막 연도(공개 18개월 시차로 미집계)를 회색 밴드로 표시.
    마지막 해의 급락이 실제 감소가 아니라 집계 artifact임을 알린다(연도 4개 이상일 때)."""
    ys = [int(y) for y in (years or []) if y is not None]
    if len(ys) < 4:
        return
    y = max(ys)
    ax.axvspan(y - 0.5, y + 0.5, facecolor="#9aa3af", alpha=0.13, zorder=0)
    ax.annotate(note, xy=(y, 1.0), xycoords=("data", "axes fraction"),
                xytext=(0, -3), textcoords="offset points", ha="center", va="top",
                fontsize=10, color="#9aa3af", annotation_clip=False)


def _save(fig, out_path):
    fig.tight_layout()
    fig.savefig(str(out_path), dpi=DPI, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


def chart1_year_country(df, out_dir):
    countries = [c for c in ["KR","US","JP","CN","EP","WO"] if c in df["country"].unique()]
    years = sorted(df["year"].unique())
    piv = df.groupby(["year","country"]).size().unstack(fill_value=0).reindex(index=years, columns=countries, fill_value=0)

    fig, ax = _new_fig()
    bottom = np.zeros(len(years))
    for c in countries:
        vals = piv[c].values.astype(float)
        color = V2_COUNTRY_COLOR.get(c, "#AAAAAA")
        ax.bar(years, vals, bottom=bottom, label=COUNTRY_NAME.get(c, c),
               color=color, width=0.8, edgecolor="white", linewidth=0.8)
        bottom += vals

    # Total line overlay
    totals = piv.sum(axis=1).values
    ax.plot(years, totals, color="#444444", linestyle="--", linewidth=2, marker="o",
            markersize=6, zorder=5, label="합계")

    # Annotate peak year
    peak_idx = np.argmax(totals)
    peak_year = years[peak_idx]
    peak_val = int(totals[peak_idx])
    ax.annotate(f"{peak_val:,}", xy=(peak_year, peak_val),
                xytext=(0, 14), textcoords="offset points",
                ha="center", va="bottom", fontsize=12, fontweight="bold", color="#333333",
                arrowprops=dict(arrowstyle="-", color="#666666", lw=0.8))

    ax.set_xlabel("출원년도", fontsize=14)
    _hlabel(ax, "출원건수")
    ax.legend(loc="upper left", fontsize=12, ncol=len(countries) + 1, frameon=False)
    _style_ax(ax)
    _mark_incomplete(ax, years)
    _save(fig, out_dir / "chart_1.png")

    by_country = piv.sum(axis=0).to_dict()
    total = int(sum(by_country.values()))
    by_country_pct = {k: round(v*100/total,1) for k,v in by_country.items()} if total else {}
    year_totals = piv.sum(axis=1)
    top_year = int(year_totals.idxmax()) if not year_totals.empty else None
    top_year_count = int(year_totals.max()) if not year_totals.empty else 0
    recent_cut = max(years)-4
    recent_sum = int(year_totals[year_totals.index >= recent_cut].sum())
    recent_pct = round(recent_sum*100/total,1) if total else 0
    last5 = {int(y): int(year_totals.get(y,0)) for y in range(max(years)-4, max(years)+1)}
    return {
        "chart_id": 1, "title": "주요 국가별 연도별 출원동향",
        "total_count": total, "year_range": [int(min(years)), int(max(years))],
        "by_country": {k:int(v) for k,v in by_country.items()},
        "by_country_pct": by_country_pct,
        "country_office": {k: COUNTRY_OFFICE.get(k,k) for k in by_country.keys()},
        "top_year": top_year, "top_year_count": top_year_count,
        "recent5_sum": recent_sum, "recent5_pct": recent_pct, "recent5_detail": last5,
    }


def chart2_country_share(df, out_dir):
    countries = ["KR","US","JP","CN","EP","WO"]
    by_country = df["country"].value_counts().reindex(countries).dropna().astype(int)
    colors = [V2_COUNTRY_COLOR.get(c, "#AAAAAA") for c in by_country.index]
    total = int(by_country.sum())

    fig, ax = _new_fig()
    wedges, texts, autotexts = ax.pie(
        by_country.values,
        colors=colors,
        autopct=lambda pct: f"{pct:.1f}%",
        startangle=90,
        pctdistance=0.75,
        labeldistance=1.15,
        wedgeprops=dict(width=0.48, edgecolor="white", linewidth=2.2),
        textprops={"fontsize": 13},
        shadow=False,
    )

    # Style percent labels inside (white bold)
    for at in autotexts:
        at.set_color("white")
        at.set_fontsize(13)
        at.set_fontweight("bold")

    # External labels: name + count connected by thin lines
    for i, (wedge, c) in enumerate(zip(wedges, by_country.index)):
        count = int(by_country.iloc[i])
        name = COUNTRY_NAME.get(c, c)
        texts[i].set_text(f"{name}  {count:,}건")
        texts[i].set_fontsize(13)

    # Center text: total count
    ax.text(0, 0.04, f"{total:,}", ha="center", va="center", fontsize=28, fontweight="bold", color="#333333")
    ax.text(0, -0.1, "건", ha="center", va="center", fontsize=16, color="#666666")

    _save(fig, out_dir / "chart_2.png")
    return {
        "chart_id": 2, "title": "국가별 특허 점유 현황",
        "total_count": total,
        "by_country": {k:int(v) for k,v in by_country.to_dict().items()},
        "by_country_pct": {k: round(v*100/total,1) for k,v in by_country.items()},
        "country_office": {k: COUNTRY_OFFICE.get(k,k) for k in by_country.index},
        "top_country": by_country.idxmax() if not by_country.empty else None,
        "top_country_count": int(by_country.max()) if not by_country.empty else 0,
    }


def chart3_ipc_top10(df, out_dir):
    exploded = df.explode("ipc_list")
    exploded = exploded[exploded["ipc_list"].notna() & (exploded["ipc_list"] != "")]
    cnt = exploded["ipc_list"].value_counts().head(10)
    if cnt.empty:
        log("  chart3: no IPC data, skipping")
        return {"chart_id": 3, "title": "IPC 기술 분야 분포", "top10": [], "total_rows_with_ipc": 0, "top10_sum": 0, "top10_pct_of_total": 0}

    fig, ax = _new_fig()
    n = len(cnt)
    ys = list(range(n))[::-1]

    # Gradient colors: dark for rank 1 -> light for rank 10
    cmap = cm.Blues_r
    grad_colors = [cmap(0.25 + 0.55 * i / max(n - 1, 1)) for i in range(n)]

    bars = ax.barh(ys, cnt.values, color=grad_colors, height=0.7, edgecolor="none")

    # Y-axis labels with rank numbers
    rank_labels = [f"{i+1}   {ipc}" for i, ipc in enumerate(cnt.index)]
    ax.set_yticks(ys)
    ax.set_yticklabels(rank_labels, fontsize=13)

    # Value labels: inside for long bars, outside for short
    max_val = cnt.values.max()
    for i, (y, v) in enumerate(zip(ys, cnt.values)):
        if v > max_val * 0.2:
            # Inside, white bold, right-aligned
            ax.text(v - max_val * 0.01, y, f"{v:,}", va="center", ha="right",
                    fontsize=13, fontweight="bold", color="white")
        else:
            # Outside
            ax.text(v + max_val * 0.01, y, f"{v:,}", va="center", ha="left",
                    fontsize=13, fontweight="bold", color="#333333")

    ax.set_xlabel("건수", fontsize=14)
    _style_ax_x_grid(ax)
    _save(fig, out_dir / "chart_3.png")

    total_ipc = int(len(exploded))
    return {
        "chart_id": 3, "title": "IPC 기술 분야 분포",
        "top10": [{"ipc": str(k), "count": int(v)} for k,v in cnt.items()],
        "total_rows_with_ipc": total_ipc,
        "top10_sum": int(cnt.sum()),
        "top10_pct_of_total": round(cnt.sum()*100/total_ipc,1) if total_ipc else 0,
    }


def chart4_ipc_year_trend(df, out_dir):
    exploded = df.explode("ipc_list")
    exploded = exploded[exploded["ipc_list"].notna() & (exploded["ipc_list"] != "")]
    top5 = exploded["ipc_list"].value_counts().head(5).index.tolist()
    years = sorted(df["year"].unique())

    fig, ax = _new_fig()
    fig.set_facecolor("#fafafa")
    ax.set_facecolor("white")

    # Light yellow band for last 5 years
    if years:
        band_start = max(years) - 4
        ax.axvspan(band_start - 0.5, max(years) + 0.5, color="#FFFDE7", alpha=0.7, zorder=0)

    series = {}
    palette = V2_IPC_PALETTE
    for i, ipc in enumerate(top5):
        sub = exploded[exploded["ipc_list"] == ipc]
        g = sub.groupby("year").size().reindex(years, fill_value=0)
        color = palette[i % len(palette)]
        ax.fill_between(g.index, g.values, alpha=0.12, color=color, zorder=1)
        ax.plot(g.index, g.values, marker="o", linewidth=3, markersize=7,
                label=ipc, color=color, zorder=2)
        series[ipc] = {int(y): int(v) for y,v in g.items()}

    ax.set_xlabel("출원년도", fontsize=14)
    _hlabel(ax, "출원건수")
    ax.legend(bbox_to_anchor=(0.5, -0.12), loc="upper center", fontsize=12,
              frameon=False, ncol=5)
    _style_ax(ax)
    _mark_incomplete(ax, years)
    # Extra bottom margin for legend
    fig.subplots_adjust(bottom=0.18)
    _save(fig, out_dir / "chart_4.png")

    growth = {}
    if years:
        recent_cut = max(years)-4
        for ipc, ys_data in series.items():
            recent = sum(v for y,v in ys_data.items() if y >= recent_cut)
            earlier = sum(v for y,v in ys_data.items() if y < recent_cut)
            growth[ipc] = {"recent5": recent, "earlier": earlier,
                           "ratio": round(recent/earlier,2) if earlier else None}
    return {
        "chart_id": 4, "title": "주요 IPC 연도별 동향",
        "top5_ipc": top5, "series": series, "growth": growth,
        "year_range": [int(min(years)), int(max(years))] if years else None,
    }


def chart5_top_applicants(df, out_dir):
    ap = df["applicant_norm"].dropna()
    cnt = ap.value_counts().head(15)
    if cnt.empty:
        log("  chart5: no applicant data, skipping")
        return {"chart_id": 5, "title": "주요 출원인 분석", "top15": [], "total_applicants": 0}
    top_names = cnt.index.tolist()
    breakdown = {}
    for name in top_names:
        sub = df[df["applicant_norm"] == name]
        bd = sub["country"].value_counts().to_dict()
        breakdown[name] = {str(k): int(v) for k,v in bd.items()}

    fig, ax = _new_fig()
    n = len(cnt)
    ys = list(range(n))[::-1]

    # Determine primary country for each applicant and assign color
    bar_colors = []
    primary_countries = []
    for name in cnt.index:
        bd = breakdown[name]
        if bd:
            primary = max(bd, key=bd.get)
        else:
            primary = "KR"
        primary_countries.append(primary)
        bar_colors.append(V2_APPLICANT_COUNTRY_COLOR.get(primary, "#AAAAAA"))

    bars = ax.barh(ys, cnt.values, color=bar_colors, height=0.7, edgecolor="white", linewidth=0.5)

    # Truncated y-axis labels
    labels_trunc = [n if len(n) <= 25 else n[:23] + "..." for n in cnt.index]
    ax.set_yticks(ys)
    ax.set_yticklabels(labels_trunc, fontsize=12)

    # Value labels + country tag
    max_val = cnt.values.max()
    for i, (y, v) in enumerate(zip(ys, cnt.values)):
        pc = primary_countries[i]
        tag = f"[{pc}]"
        if v > max_val * 0.25:
            # Inside bar: white bold
            ax.text(v - max_val * 0.01, y, f"{v:,}", va="center", ha="right",
                    fontsize=12, fontweight="bold", color="white")
            # Country tag just outside
            ax.text(v + max_val * 0.008, y, tag, va="center", ha="left",
                    fontsize=10, color="#666666")
        else:
            # Outside bar
            ax.text(v + max_val * 0.008, y, f"{v:,}  {tag}", va="center", ha="left",
                    fontsize=12, fontweight="bold", color="#333333")

    ax.set_xlabel("건수", fontsize=14)
    _style_ax_x_grid(ax)
    _save(fig, out_dir / "chart_5.png")

    return {
        "chart_id": 5, "title": "주요 출원인 분석",
        "top15": [{"applicant": str(n), "count": int(c), "by_country": breakdown[n]} for n,c in cnt.items()],
        "total_applicants": int(ap.nunique()),
    }


def chart6_grant_rate(df, out_dir):
    countries = [c for c in ["KR","US","JP","CN","EP","WO"] if c in df["country"].unique()]
    total = df.groupby("country").size().reindex(countries, fill_value=0)
    granted = df[df["is_granted"]].groupby("country").size().reindex(countries, fill_value=0)
    pct = (granted / total.replace(0, pd.NA) * 100).round(1)

    fig, ax = _new_fig()
    x = np.arange(len(countries))
    w = 0.32
    light_color = "#B8D4F0"
    dark_color = "#1E4D8C"

    bars_total = ax.bar(x - w/2, total.values, width=w, label="출원", color=light_color,
                        edgecolor="white", linewidth=0.5)
    bars_granted = ax.bar(x + w/2, granted.values, width=w, label="등록", color=dark_color,
                          edgecolor="white", linewidth=0.5)

    # Small count text on top of each bar
    for i, (t, g) in enumerate(zip(total.values, granted.values)):
        ax.text(i - w/2, t, f"{t:,}", ha="center", va="bottom", fontsize=11, color="#555555")
        ax.text(i + w/2, g, f"{g:,}", ha="center", va="bottom", fontsize=11, color="#555555")

    # Large bold grant rate percentage above each group
    y_max = max(total.values) if len(total.values) > 0 else 1
    for i, p in enumerate(pct.values):
        if pd.notna(p):
            ax.text(i, y_max * 1.08, f"{p}%", ha="center", va="bottom",
                    fontsize=18, fontweight="bold", color=dark_color)

    # Thin dashed vertical separator lines between groups
    for i in range(len(countries) - 1):
        ax.axvline(x=i + 0.5, color="#DDDDDD", linestyle="--", linewidth=0.8, zorder=0)

    ax.set_xticks(x)
    ax.set_xticklabels([COUNTRY_NAME.get(c, c) for c in countries], fontsize=14)
    _hlabel(ax, "건수")
    ax.legend(fontsize=12, frameon=False, loc="upper right")
    _style_ax(ax)
    # Extend y-axis a bit for the percentage labels
    ax.set_ylim(0, y_max * 1.25)
    _save(fig, out_dir / "chart_6.png")

    return {
        "chart_id": 6, "title": "국가별 등록률 분석",
        "by_country": {
            c: {"total": int(total[c]), "granted": int(granted[c]),
                "grant_rate_pct": float(pct[c]) if pd.notna(pct[c]) else None}
            for c in countries
        },
    }


def chart7_scurve(df, out_dir):
    years = sorted(df["year"].unique())
    yearly = df.groupby("year").size().reindex(years, fill_value=0)
    cumsum = yearly.cumsum()
    total = int(cumsum.iloc[-1]) if len(cumsum) > 0 else 1

    # Determine stage boundaries by cumulative percentage
    thresholds = {"도입기": 0.10, "성장기": 0.50, "성숙기": 0.90, "쇠퇴기": 1.00}
    boundaries = {}
    prev_year = years[0]
    for stage, pct in thresholds.items():
        target = total * pct
        stage_year = years[-1]
        for y in years:
            if cumsum.get(y, 0) >= target:
                stage_year = y
                break
        boundaries[stage] = (prev_year, stage_year)
        prev_year = stage_year

    # Determine current stage
    current_year = years[-1]
    current_pct = cumsum.iloc[-1] / total if total else 0
    if current_pct <= 0.10:
        current_stage = "도입기"
    elif current_pct <= 0.50:
        current_stage = "성장기"
    elif current_pct <= 0.90:
        current_stage = "성숙기"
    else:
        current_stage = "쇠퇴기"

    fig, ax = _new_fig()

    # Shade each stage band
    band_colors = {"도입기": "#DBEAFE", "성장기": "#DCFCE7", "성숙기": "#FEF9C3", "쇠퇴기": "#FEE2E2"}
    for stage, (y_start, y_end) in boundaries.items():
        ax.axvspan(y_start - 0.5, y_end + 0.5, color=band_colors[stage], alpha=0.5, zorder=0)
        mid_x = (y_start + y_end) / 2
        ax.text(mid_x, total * 0.95, stage, ha="center", va="top",
                fontsize=14, fontweight="bold", color="#555555", zorder=3)

    # Cumulative line
    ax.plot(years, cumsum.values, color="#1E4D8C", linewidth=3.5, zorder=2)
    ax.fill_between(years, cumsum.values, alpha=0.10, color="#1E4D8C", zorder=1)

    ax.set_xlabel("출원년도", fontsize=14)
    _hlabel(ax, "누적 출원건수")
    _style_ax(ax)
    _mark_incomplete(ax, years)
    _save(fig, out_dir / "chart_7.png")

    return {
        "chart_id": 7, "title": "기술 성장단계",
        "total_count": total,
        "boundaries": {stage: {"start": int(b[0]), "end": int(b[1])} for stage, b in boundaries.items()},
        "current_stage": current_stage,
    }


def chart8_applicant_trend(df, out_dir):
    ap = df["applicant_norm"].dropna()
    top5 = ap.value_counts().head(5).index.tolist()
    years = sorted(df["year"].unique())
    palette = V2_IPC_PALETTE

    fig, ax = _new_fig()
    series = {}
    for i, name in enumerate(top5):
        sub = df[df["applicant_norm"] == name]
        g = sub.groupby("year").size().reindex(years, fill_value=0)
        color = palette[i % len(palette)]
        ax.fill_between(g.index, g.values, alpha=0.08, color=color, zorder=1)
        ax.plot(g.index, g.values, marker="o", linewidth=3, markersize=7,
                label=name if len(name) <= 20 else name[:18] + "..", color=color, zorder=2)
        series[name] = {int(y): int(v) for y, v in g.items()}

    ax.set_xlabel("출원년도", fontsize=14)
    _hlabel(ax, "출원건수")
    ax.legend(bbox_to_anchor=(0.5, -0.12), loc="upper center", fontsize=12,
              frameon=False, ncol=min(len(top5), 5))
    _style_ax(ax)
    _mark_incomplete(ax, years)
    fig.subplots_adjust(bottom=0.18)
    _save(fig, out_dir / "chart_8.png")

    return {
        "chart_id": 8, "title": "주요 출원인 연도별 활동 추이",
        "top5": top5,
        "series": series,
    }


def chart9_applicant_country_heatmap(df, out_dir):
    ap = df["applicant_norm"].dropna()
    if ap.empty:
        log("  chart9: no applicant data, skipping")
        return {"chart_id": 9, "title": "출원인-국가 히트맵", "top10": [], "countries": [], "matrix": {}}
    top10 = ap.value_counts().head(10).index.tolist()
    target_countries = ["KR", "US", "JP", "CN"]
    country_labels = ["한국", "미국", "일본", "중국"]

    matrix = []
    for name in top10:
        sub = df[df["applicant_norm"] == name]
        row = []
        for c in target_countries:
            row.append(int((sub["country"] == c).sum()))
        matrix.append(row)
    matrix = np.array(matrix)

    fig, ax = _new_fig()
    im = ax.imshow(matrix, cmap="Blues", aspect="auto")

    # Annotate each cell
    for i in range(len(top10)):
        for j in range(len(target_countries)):
            val = matrix[i, j]
            text_color = "white" if val > matrix.max() * 0.5 else "#333333"
            ax.text(j, i, f"{val:,}", ha="center", va="center",
                    fontsize=13, fontweight="bold", color=text_color)

    # Axis labels
    trunc_names = [n if len(n) <= 20 else n[:18] + ".." for n in top10]
    ax.set_yticks(range(len(top10)))
    ax.set_yticklabels(trunc_names, fontsize=12)
    ax.set_xticks(range(len(target_countries)))
    ax.set_xticklabels(country_labels, fontsize=14)
    ax.tick_params(top=True, bottom=False, labeltop=True, labelbottom=False)

    for spine in ax.spines.values():
        spine.set_visible(False)

    _save(fig, out_dir / "chart_9.png")

    matrix_data = {name: {c: int(matrix[i, j]) for j, c in enumerate(target_countries)}
                   for i, name in enumerate(top10)}
    return {
        "chart_id": 9, "title": "출원인-국가 히트맵",
        "top10": top10,
        "countries": target_countries,
        "matrix": matrix_data,
    }


def chart10_applicant_type(df, out_dir):
    applicants = df["applicant_norm"].dropna().unique()
    if len(applicants) == 0:
        log("  chart10: no applicant data, skipping")
        return {"chart_id": 10, "title": "출원인 유형 분포", "total_applicants": 0, "by_type": {}}

    def classify(name):
        upper = name.upper()
        # University check
        if any(kw in upper for kw in ["UNIVERSITY", "UNIV", "대학", "COLLEGE",
                                       "INSTITUTE OF TECHNOLOGY", "POLYTECHNIC"]):
            return "대학"
        # Research institute check
        if any(kw in upper for kw in ["INSTITUTE", "INST", "연구", "RESEARCH",
                                       "ACADEMY", "CENTER", "CENTRE", "LABORATORY"]):
            return "연구기관"
        # Individual check: 2-4 Korean chars with no spaces, or all-uppercase 2-word Western names
        stripped = name.strip()
        if re.match(r"^[가-힣]{2,4}$", stripped):
            return "개인"
        words = stripped.split()
        if len(words) == 2 and all(w.isupper() and w.isalpha() for w in words):
            return "개인"
        return "기업"

    type_map = {name: classify(name) for name in applicants}
    type_counts = {}
    for name in applicants:
        t = type_map[name]
        type_counts[t] = type_counts.get(t, 0) + 1
    total = sum(type_counts.values())

    # Ensure order
    ordered_types = ["기업", "대학", "연구기관", "개인"]
    type_colors = {"기업": "#2E5B8A", "대학": "#C9A24B", "연구기관": "#3F8E7E", "개인": "#B5483D"}
    values = [type_counts.get(t, 0) for t in ordered_types]
    colors = [type_colors[t] for t in ordered_types]

    # Filter out zero-count types
    filtered = [(t, v, c) for t, v, c in zip(ordered_types, values, colors) if v > 0]
    if not filtered:
        filtered = [("기업", 0, "#2E5B8A")]
    f_types, f_values, f_colors = zip(*filtered)

    fig, ax = _new_fig()
    wedges, texts, autotexts = ax.pie(
        f_values,
        colors=f_colors,
        autopct=lambda pct: f"{pct:.1f}%",
        startangle=90,
        pctdistance=0.75,
        labeldistance=1.15,
        wedgeprops=dict(width=0.48, edgecolor="white", linewidth=2.2),
        textprops={"fontsize": 13},
        shadow=False,
    )

    for at in autotexts:
        at.set_color("white")
        at.set_fontsize(13)
        at.set_fontweight("bold")

    for i, (wedge, t) in enumerate(zip(wedges, f_types)):
        count = f_values[i]
        texts[i].set_text(f"{t}  {count:,}건")
        texts[i].set_fontsize(13)

    ax.text(0, 0.04, f"{total:,}", ha="center", va="center", fontsize=28, fontweight="bold", color="#333333")
    ax.text(0, -0.1, "건", ha="center", va="center", fontsize=16, color="#666666")

    _save(fig, out_dir / "chart_10.png")

    return {
        "chart_id": 10, "title": "출원인 유형 분포",
        "total_applicants": total,
        "by_type": {t: {"count": type_counts.get(t, 0),
                        "pct": round(type_counts.get(t, 0) * 100 / total, 1) if total else 0}
                    for t in ordered_types},
    }


# ---------------- main ----------------
def main():
    if len(sys.argv) < 2:
        print("Usage: python _gen_report_stage_a.py <input_dir> [--column-map map.json]")
        sys.exit(1)
    input_dir = sys.argv[1]
    out_dir = Path(input_dir) / "_report_assets"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Parse optional --column-map argument (Claude provides this for non-standard data)
    explicit_map = None
    if "--column-map" in sys.argv:
        idx = sys.argv.index("--column-map")
        if idx + 1 < len(sys.argv):
            map_path = sys.argv[idx + 1]
            try:
                with open(map_path, "r", encoding="utf-8") as mf:
                    explicit_map = json.load(mf)
                log(f"loaded explicit column map from {map_path}: {explicit_map}")
            except Exception as e:
                log(f"WARN: failed to load column map {map_path}: {e}")

    raw = load_all(input_dir, explicit_map)
    df = preprocess(raw)
    log(f"after preprocess: {len(df)} rows, countries={sorted(df['country'].unique())}, years={df['year'].min()}~{df['year'].max()}")

    all_stats = {}
    for fn, idx in [(chart1_year_country,1),(chart2_country_share,2),(chart3_ipc_top10,3),
                    (chart4_ipc_year_trend,4),(chart5_top_applicants,5),(chart6_grant_rate,6),
                    (chart7_scurve,7),(chart8_applicant_trend,8),
                    (chart9_applicant_country_heatmap,9),(chart10_applicant_type,10)]:
        try:
            log(f"rendering chart {idx}...")
            stats = fn(df, out_dir)
            (out_dir / f"stats_{idx}.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
            all_stats[idx] = stats
        except Exception as e:
            log(f"ERROR rendering chart {idx}: {e}")
            continue

    # summary
    summary = {
        "total_count": int(len(df)),
        "year_range": [int(df["year"].min()), int(df["year"].max())],
        "by_country": df["country"].value_counts().to_dict(),
        "charts": [str(out_dir / f"chart_{i}.png") for i in range(1,11)],
        "stats": [str(out_dir / f"stats_{i}.json") for i in range(1,11)],
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"DONE. assets at: {out_dir}")
    log(f"total patents: {len(df)}, years {df['year'].min()}-{df['year'].max()}")
    log(f"by country: {df['country'].value_counts().to_dict()}")

if __name__ == "__main__":
    main()
