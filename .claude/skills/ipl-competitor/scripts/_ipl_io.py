# -*- coding: utf-8 -*-
"""
ipl 공통 입출력 헬퍼 — 신규 IP Landscape 스킬들이 공유한다.
- ensure_pkgs(): 필요한 패키지 자동 설치
- korean_font(): OS별 한글 폰트명
- load_patents(folder): 폴더의 모든 xlsx를 읽어 단일 DataFrame
- resolve(df): 역할별 컬럼명 매핑 {role: colname or None}
- ipl_dir(folder, *sub): <folder>/_ipl[/sub] 생성 후 반환
"""
import sys, os, subprocess, glob, json, platform
from pathlib import Path


def ensure_pkgs(pkgs):
    for p in pkgs:
        mod = {"pillow": "PIL", "scikit-learn": "sklearn"}.get(p, p)
        try:
            __import__(mod)
        except ImportError:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", p])


def korean_font():
    s = platform.system()
    if s == "Windows":
        return "Malgun Gothic"
    if s == "Darwin":
        return "AppleGothic"
    for name in ["NanumGothic", "NanumBarunGothic", "UnDotum", "DejaVu Sans"]:
        try:
            from matplotlib.font_manager import findfont, FontProperties
            if findfont(FontProperties(family=name), fallback_to_default=False):
                return name
        except Exception:
            continue
    return "sans-serif"


def korean_font_path():
    """reportlab 등록용 ttf 경로 (없으면 None)."""
    cands = []
    s = platform.system()
    if s == "Windows":
        cands = [r"C:\Windows\Fonts\malgun.ttf", r"C:\Windows\Fonts\malgunsl.ttf",
                 r"C:\Windows\Fonts\gulim.ttc", r"C:\Windows\Fonts\batang.ttc"]
    elif s == "Darwin":
        cands = ["/System/Library/Fonts/AppleSDGothicNeo.ttc",
                 "/Library/Fonts/AppleGothic.ttf"]
    else:
        cands = ["/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
                 "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]
    for c in cands:
        if os.path.exists(c):
            return c
    return None


_ROLE_ALIASES = {
    "filing_date": ["출원일", "filing date", "filing_date", "출원일자", "application date", "출원년월일"],
    "applicant": ["출원인 대표명화", "출원인 대표명화 영문명", "출원인", "applicant", "assignee",
                  "권리자", "특허권자", "patentee", "current assignee", "출원인명"],
    "ipc_main": ["current ipc main", "ipc main", "대표ipc", "ipc(대표)", "main ipc", "ipc 대표"],
    "ipc_all": ["current ipc all", "ipc all", "ipc 전체", "ipc(전체)", "ipc", "ipc code", "ipc분류"],
    "country": ["국가코드", "country", "country code", "출원국", "출원국가", "office", "authority"],
    "number": ["등록번호", "출원번호", "registration no", "patent no", "patent number",
               "application number", "공개번호", "문헌번호", "lens id", "doc number"],
    "title": ["발명의 명칭", "발명의명칭", "title", "발명명칭", "명칭", "invention title"],
    "abstract": ["요약", "abstract", "초록", "summary"],
    "problem": ["해결과제 요약", "해결하려는 과제", "해결과제", "기술적 과제", "problem", "objective"],
    "solution": ["해결수단 요약", "해결수단", "과제의 해결수단", "solution", "means"],
    "citations": ["피인용수", "피인용", "인용수", "cited by", "forward citation", "forward citations",
                  "citing patents count", "cited by patent count", "피인용 횟수"],
    "family": ["패밀리수", "패밀리", "family size", "patent family", "simple family size",
               "family count", "패밀리 국가수", "패밀리국가수"],
    "claims": ["청구항수", "청구항 수", "claim count", "claims count", "number of claims", "독립청구항수"],
    "claims_text": ["청구항", "claims", "대표청구항", "독립청구항"],
    "legal_status": ["법적상태", "법적 상태", "legal status", "상태정보", "status", "권리상태"],
}


def resolve(df):
    cols = list(df.columns)
    low = {str(c).strip().lower(): c for c in cols}
    out = {}
    for role, aliases in _ROLE_ALIASES.items():
        found = None
        for a in aliases:
            al = a.lower()
            if al in low:
                found = low[al]; break
        if not found:
            for a in aliases:
                al = a.lower()
                for lc, orig in low.items():
                    if al in lc:
                        found = orig; break
                if found:
                    break
        out[role] = found
    return out


def load_patents(folder):
    import pandas as pd
    files = sorted(glob.glob(os.path.join(folder, "*.xlsx")))
    pref = [f for f in files if "유효" in os.path.basename(f) and not os.path.basename(f).startswith("~$")]
    use = pref if pref else [f for f in files if not os.path.basename(f).startswith("~$")
                             and "제외" not in os.path.basename(f)]
    if not use:
        raise FileNotFoundError(f"{folder} 에 분석할 xlsx가 없습니다.")
    frames = []
    for f in use:
        try:
            frames.append(read_excel_safe(f))
        except Exception as e:
            print(f"[warn] {f} 읽기 실패: {e}")
    if not frames:
        raise RuntimeError("xlsx를 하나도 읽지 못했습니다.")
    return pd.concat(frames, ignore_index=True)


# 헤더 행 자동탐지용 키워드 (KIPRIS/WIPS/Lens 공통)
_HEADER_HINTS = ["발명의명칭", "발명의 명칭", "출원번호", "출원일", "출원인", "ipc", "title",
                 "applicant", "filing date", "application number", "요약", "abstract",
                 "공개번호", "등록번호", "피인용", "lens id", "jurisdiction"]


def _read_any(path, **kw):
    """openpyxl 실패 시 calamine(스타일 무시·강건)로 폴백."""
    import pandas as pd
    last = None
    for eng in ("openpyxl", "calamine"):
        try:
            if eng == "calamine":
                ensure_pkgs(["python-calamine"])
            return pd.read_excel(path, engine=eng, **kw)
        except Exception as e:
            last = e
    raise last


def _find_header_row(path):
    """상단에 제목/검색식 블록이 있는 익스포트(KIPRIS 등)에서 실제 헤더 행을 찾는다."""
    import pandas as pd
    try:
        probe = _read_any(path, header=None, nrows=25)
    except Exception:
        return 0
    best, best_hits = 0, 0
    for i in range(len(probe)):
        cells = [str(v).strip().lower() for v in probe.iloc[i].tolist()]
        nonnull = sum(1 for c in cells if c and c != "nan")
        hits = sum(1 for c in cells for h in _HEADER_HINTS if h in c)
        if hits > best_hits and nonnull >= 4:
            best, best_hits = i, hits
        if best_hits >= 4:
            break
    return best if best_hits >= 2 else 0


def read_excel_safe(path, **kw):
    """강건한 엑셀 리더: 손상된 스타일시트(calamine 폴백) + 헤더 행 자동탐지.
    호출자가 header를 명시하면 그대로 존중한다."""
    if "header" in kw:
        return _read_any(path, **kw)
    return _read_any(path, header=_find_header_row(path), **kw)


def clean_id(v):
    """특허번호 등 ID가 float로 읽힌 경우 '1021467080000.0' → '1021467080000' 로 정리."""
    import pandas as pd
    if v is None:
        return ""
    try:
        if isinstance(v, float):
            if pd.isna(v):
                return ""
            if float(v).is_integer():
                return str(int(v))
    except Exception:
        pass
    s = str(v).strip()
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return s


def fmt_patent_no(v):
    """KR 특허번호를 사람이 읽는 형태로 정리(멱등). 그 외(JP/US 등)는 원본 유지.

    KIPRIS는 KR 번호를 13자리 무하이픈으로 내보낸다:
      - 등록번호: '10' + 7자리 등록번호 + '0000'  → 10-2463374
      - 출원번호: '10' + 연도(YYYY) + 7자리 일련번호 → 10-2018-0012345
    이미 하이픈/문자 접두가 있거나 패턴이 모호하면 원본을 그대로 돌려준다(오변환 방지)."""
    s = clean_id(v)
    if not s or "-" in s or not s.isdigit():
        return s
    if len(s) == 13 and s[:2] in ("10", "20", "30", "40"):
        kind = s[:2]
        if s[9:13] == "0000":                      # 등록번호: 10-XXXXXXX
            return f"{kind}-{s[2:9]}"
        try:
            y = int(s[2:6])
        except ValueError:
            return s
        if 1948 <= y <= 2099:                       # 출원번호: 10-YYYY-NNNNNNN
            return f"{kind}-{s[2:6]}-{s[6:]}"
    return s


def trunc(s, n):
    """n자 초과 시 말줄임표(…)로 자른다(글자 단위 뚝 잘림 방지)."""
    s = "" if s is None else str(s)
    return s if len(s) <= n else s[: max(1, n - 1)].rstrip() + "…"


def clean_label(s):
    """표시용 짧은 라벨 정리: 깨진 글자(U+FFFD)·제어문자 제거, 공백 정규화."""
    import re as _re
    s = "" if s is None else str(s)
    s = s.replace("�", "")
    s = _re.sub(r"[\x00-\x1f\x7f]", " ", s)
    return _re.sub(r"\s+", " ", s).strip()


def ipl_dir(folder, *sub):
    p = Path(folder) / "_ipl"
    for s in sub:
        p = p / s
    p.mkdir(parents=True, exist_ok=True)
    return p


def parse_year(series):
    import re
    def _y(v):
        if v is None:
            return None
        m = re.search(r"(19|20)\d{2}", str(v))
        return int(m.group(0)) if m else None
    return series.map(_y)


# ===== 차트 공통 스타일 (patent-trend stage_a 프리미엄 룩과 통일) =====
# 보고서 전 장의 차트 톤을 맞추기 위한 공유 팔레트·축 스타일.
# 절제된 에디토리얼 팔레트(차분한 채도) — 엑셀 기본색 느낌을 피한다.
IPL_PALETTE = ["#2E4A6B", "#B5483D", "#3F8E7E", "#7E5A8C", "#C9A24B", "#5E7E9B", "#9C5B3B", "#8A8A8A"]
IPL_COUNTRY_COLOR = {"KR": "#2E5B8A", "US": "#B5483D", "JP": "#3F8E7E",
                     "CN": "#C9A24B", "EP": "#7E5A8C", "WO": "#AEB4BB"}
IPL_FIG_BG = "#ffffff"      # 흰 배경(깔끔)
IPL_GRID = "#ededed"        # 매우 옅은 그리드
IPL_TICK = "#6b6b6b"        # 눈금 라벨색
IPL_SEQ_CMAP = "Blues"      # 순차형(히트맵)
IPL_DENS_CMAP = "YlOrRd"    # 밀도/등고선


def chart_fig(w=9.5, h=5.3, dpi=150):
    """프리미엄 룩 figure/axes (흰 배경 + 흰 plot 영역)."""
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(w, h), dpi=dpi)
    fig.set_facecolor(IPL_FIG_BG)
    ax.set_facecolor("#ffffff")
    return fig, ax


def style_axes(ax, grid="y"):
    """스파인 제거 + 옅은 실선 그리드(한 축만) + 얇은 베이스라인 + 통일 눈금.
    점선·진한 그리드·박스 프레임을 없애 엑셀풍을 탈피하고 에디토리얼 톤을 준다."""
    import matplotlib.ticker as mticker
    for sp in ax.spines.values():
        sp.set_visible(False)
    if grid in ("y", "both"):
        ax.grid(axis="y", which="major", color=IPL_GRID, linewidth=0.9, zorder=0)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{int(v):,}"))
        # 가로 막대(grid='x')가 아니면 좌측 눈금 기준선 역할의 옅은 baseline
        ax.spines["bottom"].set_visible(True)
        ax.spines["bottom"].set_color(IPL_GRID); ax.spines["bottom"].set_linewidth(1.0)
    if grid in ("x", "both"):
        ax.grid(axis="x", which="major", color=IPL_GRID, linewidth=0.9, zorder=0)
        if grid == "x":
            ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{int(v):,}"))
    ax.set_axisbelow(True)
    ax.tick_params(labelsize=11.5, colors=IPL_TICK, length=0)


def axis_unit(ax, text, axis="y"):
    """축 단위 라벨을 '가로'로 배치(한글이 세로 한 글자씩 쓰이는 것 방지).
    y축은 plot 상단 좌측에 가로로 얹는다."""
    if axis == "y":
        ax.set_ylabel("")
        ax.annotate(text, xy=(0.0, 1.02), xycoords="axes fraction", ha="left", va="bottom",
                    fontsize=11, color="#666666", annotation_clip=False)
    else:
        ax.set_xlabel(text, fontsize=12, color="#444444")


def mark_incomplete_year(ax, years, note="최근(공개 시차)"):
    """시계열 차트의 마지막 연도(공개 18개월 시차로 미집계)를 회색 해치로 표시.
    마지막 해의 급락이 실제 감소가 아니라 집계 artifact임을 시각적으로 알린다.
    연도가 4개 이상인 추세 차트에만 적용."""
    ys = [int(y) for y in (years or []) if y is not None]
    if len(ys) < 4:
        return
    y = max(ys)
    ax.axvspan(y - 0.5, y + 0.5, facecolor="#9aa3af", alpha=0.13, zorder=0)
    ax.annotate(note, xy=(y, 1.0), xycoords=("data", "axes fraction"),
                xytext=(0, -3), textcoords="offset points", ha="center", va="top",
                fontsize=8.5, color="#9aa3af", annotation_clip=False)
