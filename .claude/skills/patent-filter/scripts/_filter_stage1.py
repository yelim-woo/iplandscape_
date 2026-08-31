# -*- coding: utf-8 -*-
"""
Stage 1 filter: raw patent xlsx folder -> 1차 필터링 (법적상태=등록 + 출원일 최근 N년).

- 폴더 안의 모든 .xlsx 를 읽어 하나로 합침 (원본 컬럼 전부 보존)
- 컬럼 자동매핑(WIPS 별칭 + 키워드 + 데이터 패턴)으로 출원일/법적상태/명칭/요약/청구항 위치 탐지
- 법적상태 == 등록(granted/registered) 인 행만 1차 통과
- 출원일 >= (기준일 - N년) 인 행만 1차 통과
- 통과/제외 결과를 <폴더>/_filter/ 에 저장하고, 2차(LLM) 판정용 경량 JSON 도 생성

Usage:
  python _filter_stage1.py <raw_folder> [--asof YYYY-MM-DD] [--years 10] [--column-map map.json]

출력 (<raw_folder>/_filter/):
  stage1_pass.xlsx       1차 통과 (모든 원본 컬럼 + _uid)
  stage1_excluded.xlsx   1차 제외 (모든 원본 컬럼 + _uid + 제외단계 + 제외사유)
  stage1_pass.json       2차 판정용 경량 레코드 [{uid, 출원번호, 명칭, 요약, IPC, 청구항}]
  _meta.json             컬럼 매핑 결과 + 집계 통계
"""
import sys, os, glob, json, re, argparse
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd

# Windows cp949 콘솔에서도 한글·특수문자(— ※ 등) 로그가 깨지거나 크래시하지 않도록 stdout을 utf-8로 고정
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def log(msg):
    print(f"[stage1] {msg}", flush=True)


# ---------------- 강건한 엑셀 리더 (KIPRIS 손상 스타일 + 헤더 오프셋 대응) ----------------
_HEADER_HINTS = ["발명의명칭", "발명의 명칭", "출원번호", "출원일", "출원인", "ipc", "title",
                 "applicant", "filing date", "application number", "요약", "abstract",
                 "공개번호", "등록번호", "피인용", "lens id", "jurisdiction"]


def _read_any(path, **kw):
    last = None
    for eng in ("openpyxl", "calamine"):
        try:
            if eng == "calamine":
                try:
                    import python_calamine  # noqa
                except ImportError:
                    import subprocess
                    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "python-calamine"])
            return pd.read_excel(path, engine=eng, **kw)
        except Exception as e:
            last = e
    raise last


def _find_header_row(path):
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


def robust_read(path):
    return _read_any(path, header=_find_header_row(path))


# ---------------- 컬럼 별칭 (소문자 키 -> 표준 역할) ----------------
# 역할(role)별로 흔한 컬럼명을 모아둔다. patent-trend 의 별칭표와 호환.
ALIASES = {
    "출원일": [
        "출원일", "출원일자", "출원 일자", "출원년월일", "출원(국제)일", "출원일(국제)",
        "application date", "filing date", "filing_date", "app date", "app_date",
        "date of application", "date of filing", "earliest filing date",
        "earliest_filing_date", "출원국제일자",
    ],
    "법적상태": [
        "상태정보[kr,jp,us,ep,cn,ca,au]", "상태정보", "법적상태", "법적 상태", "상태",
        "권리상태", "등록사항", "legal status", "legal_status", "status",
        "patent status", "patent_status", "현재상태",
    ],
    "발명의명칭": [
        "발명의 명칭", "발명의명칭", "명칭", "발명명칭", "title", "invention title",
        "발명의 명칭-원문", "title of invention",
    ],
    "요약": [
        "요약", "초록", "abstract", "summary", "요약-원문", "ai 요약",
    ],
    "청구항": [
        "대표청구항", "청구항", "대표 청구항", "청구범위", "claims", "claim",
        "representative claim", "first claim", "독립청구항",
    ],
    "출원번호": [
        "출원번호", "application number", "application no", "app no", "appln no",
        "출원 번호", "출원번호(국제)",
    ],
    "ipc": [
        "current ipc main", "current ipc all", "ipc", "ipc code", "ipc분류",
        "ipc 분류", "main ipc", "대표ipc", "ipc(대표)",
    ],
}

DATE_PAT = re.compile(r"^\s*(\d{4})[-/.]?(\d{2})?[-/.]?(\d{2})?")
IPC_PAT = re.compile(r"[A-H]\d{2}[A-Z]")

# 법적상태: 유효(등록)로 인정할 긍정 키워드
POSITIVE_STATUS = ["등록", "granted", "registered", "grant", "in force", "active"]
# 등록 글자가 있어도 사실상 무효인 케이스 (등록취소/등록무효/등록소멸 등) -> 제외
NEGATIVE_STATUS = [
    "취소", "무효", "소멸", "거절", "포기", "취하", "실효", "말소",
    "expired", "lapsed", "revoked", "withdrawn", "rejected", "abandoned",
    "ceased", "invalid", "refused", "dead",
]


def _norm(s):
    return str(s).strip().lower()


def find_column(df, role, explicit_map=None):
    """역할(role)에 해당하는 실제 컬럼명을 찾는다. 못 찾으면 None.
    우선순위: explicit_map > 별칭 정확매칭 > 별칭 부분매칭 > 패턴감지."""
    cols = list(df.columns)
    norm_cols = {c: _norm(c) for c in cols}

    # 1) 사용자 명시 매핑 (역방향: {원본컬럼: 역할})
    if explicit_map:
        for src, dst in explicit_map.items():
            if dst == role and src in df.columns:
                return src

    aliases = ALIASES.get(role, [])

    # 2) 별칭 정확 매칭
    for c in cols:
        if norm_cols[c] in aliases:
            return c

    # 3) 별칭 부분 매칭 (컬럼명이 별칭을 포함)
    for c in cols:
        for a in aliases:
            if a in norm_cols[c]:
                return c

    # 4) 패턴 감지 (출원일/법적상태/ipc 한정)
    if role == "출원일":
        for c in cols:
            if "출원" in str(c) or "filing" in norm_cols[c] or "application" in norm_cols[c]:
                if _looks_like_date(df[c]):
                    return c
        for c in cols:
            if _looks_like_date(df[c]):
                return c
    elif role == "ipc":
        for c in cols:
            if _looks_like_ipc(df[c]):
                return c
    elif role == "법적상태":
        for c in cols:
            sample = df[c].dropna().astype(str).head(50)
            hits = sum(1 for v in sample if any(k in _norm(v) for k in POSITIVE_STATUS + NEGATIVE_STATUS))
            if len(sample) and hits / len(sample) > 0.4:
                return c
    return None


def _looks_like_date(series):
    sample = series.dropna().astype(str).head(50)
    if len(sample) == 0:
        return False
    hits = sum(1 for v in sample if DATE_PAT.match(v.strip()))
    return hits / len(sample) > 0.5


def _looks_like_ipc(series):
    sample = series.dropna().astype(str).head(50)
    if len(sample) == 0:
        return False
    hits = sum(1 for v in sample if IPC_PAT.search(v.strip().upper()))
    return hits / len(sample) > 0.3


def parse_filing_date(val):
    """출원일 셀 -> datetime (날짜 불명이면 None). 연도만 있으면 그 해 1월 1일."""
    if pd.isna(val):
        return None
    s = str(val).strip()
    if not s:
        return None
    m = DATE_PAT.match(s)
    if not m:
        return None
    y = int(m.group(1))
    if not (1900 <= y <= 2100):
        return None
    mo = int(m.group(2)) if m.group(2) else 1
    da = int(m.group(3)) if m.group(3) else 1
    mo = min(max(mo, 1), 12)
    da = min(max(da, 1), 28) if not (1 <= da <= 31) else da
    try:
        return datetime(y, mo, da)
    except ValueError:
        try:
            return datetime(y, mo, 1)
        except ValueError:
            return datetime(y, 1, 1)


def status_is_blank(val):
    """법적상태 값이 비어 있는지(=등록 여부를 판정할 정보 자체가 없음).
    KIPRIS 해외검색 결과처럼 국내 스키마의 법적상태 컬럼이 통째로 공란인 국가 데이터가 여기 해당한다.
    NaN·빈문자·'nan'/'none' 등을 정보 없음으로 본다."""
    if pd.isna(val):
        return True
    s = _norm(val)
    return s in ("", "nan", "none", "-")


def status_is_registered(val):
    """법적상태가 '등록(유효)'인지. (등록/granted/registered, 단 취소·무효·소멸 등은 제외)"""
    if pd.isna(val):
        return False
    s = _norm(val)
    if not s:
        return False
    has_pos = any(k in s for k in POSITIVE_STATUS)
    if not has_pos:
        return False
    # '등록' 다음에 부정어가 붙은 경우(등록취소/등록무효 등) 제외
    has_neg = any(k in s for k in NEGATIVE_STATUS)
    return has_pos and not has_neg


def load_folder(folder):
    """폴더 내 모든 xlsx 를 읽어 하나의 DataFrame 으로 합친다 (원본 컬럼 보존)."""
    files = sorted(glob.glob(os.path.join(folder, "*.xlsx")))
    files = [f for f in files if not os.path.basename(f).startswith("~$")
             and os.path.basename(f) not in ("유효데이터.xlsx", "제외로그.xlsx")
             and "_filter" not in f and "_ipl" not in f]
    if not files:
        raise SystemExit(f"[stage1] ERROR: {folder} 에 .xlsx 파일이 없습니다.")
    frames = []
    for f in files:
        try:
            d = robust_read(f)
        except Exception as e:
            log(f"WARN read fail: {f} ({e})")
            continue
        d["_원본파일"] = os.path.basename(f)
        frames.append(d)
        log(f"읽음: {os.path.basename(f)} ({len(d)}건, {d.shape[1]}컬럼)")
    if not frames:
        raise SystemExit("[stage1] ERROR: 읽을 수 있는 파일이 없습니다.")
    df = pd.concat(frames, ignore_index=True, sort=False)
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--asof", default=None, help="기준일 YYYY-MM-DD (기본: 오늘)")
    ap.add_argument("--years", type=int, default=10, help="최근 N년 (기본 10)")
    ap.add_argument("--column-map", default=None, help="{원본컬럼: 역할} JSON 파일")
    args = ap.parse_args()

    folder = os.path.abspath(args.folder)
    asof = datetime.strptime(args.asof, "%Y-%m-%d") if args.asof else datetime.today()
    cutoff = datetime(asof.year - args.years, asof.month, asof.day)
    log(f"기준일 {asof.date()} / 최근 {args.years}년 -> 출원일 cutoff = {cutoff.date()}")

    explicit_map = None
    if args.column_map and os.path.exists(args.column_map):
        explicit_map = json.load(open(args.column_map, encoding="utf-8"))

    df = load_folder(folder)
    df.insert(0, "_uid", range(1, len(df) + 1))
    log(f"총 {len(df)}건 병합 (컬럼 {df.shape[1]}개)")

    # 국내/해외 스키마 정합: 이름만 갈라진 개념 컬럼(명칭·IPC 등) 통합.
    # 여기서 먼저 합쳐야 컬럼 탐지·2차 판정용 stage1_pass.json이 해외 명칭/IPC까지 담는다.
    try:
        from _apply_verdicts import unify_columns
        df = unify_columns(df)
    except Exception as e:
        log(f"WARN: 컬럼 통합 건너뜀 ({e})")

    # --- 컬럼 위치 탐지 ---
    col = {role: find_column(df, role, explicit_map) for role in ALIASES}
    log(f"컬럼 매핑: " + ", ".join(f"{r}->{c}" for r, c in col.items()))

    if not col["법적상태"]:
        log("WARN: 법적상태 컬럼을 못 찾음 -> 법적상태 필터를 건너뜀(전부 통과). column-map 권장.")
    if not col["출원일"]:
        log("WARN: 출원일 컬럼을 못 찾음 -> 출원일 필터를 건너뜀(전부 통과). column-map 권장.")

    # --- 행별 1차 판정 ---
    reasons = []       # 제외사유 ("" 면 통과)
    held_blank = 0     # 법적상태 공란 → '판정 보류'로 통과시킨 건수(전량 제외 방지)
    for _, row in df.iterrows():
        why = []
        # 법적상태: 값이 있으면 '등록'만 통과. 단 값이 통째로 비어(정보 없음) 등록 판정 자체가
        # 불가능한 행(KIPRIS 해외검색 등)은 제외하지 않고 '판정 보류'로 통과시켜 2차 의미판정으로 넘긴다.
        if col["법적상태"]:
            v = row[col["법적상태"]]
            if status_is_blank(v):
                held_blank += 1
            elif not status_is_registered(v):
                why.append(f"법적상태 비등록[{str(v).strip()}]")
        # 출원일
        if col["출원일"]:
            d = parse_filing_date(row[col["출원일"]])
            if d is None:
                why.append("출원일 불명")
            elif d < cutoff:
                why.append(f"출원일 {d.date()} < {cutoff.date()}")
        reasons.append(" / ".join(why))

    df["_제외사유"] = reasons
    passed = df[df["_제외사유"] == ""].copy()
    excluded = df[df["_제외사유"] != ""].copy()

    out_dir = os.path.join(folder, "_filter")
    os.makedirs(out_dir, exist_ok=True)

    # 통과본: 보조 컬럼 정리 (_uid 는 유지, _제외사유 제거)
    pass_out = passed.drop(columns=["_제외사유"])
    pass_out.to_excel(os.path.join(out_dir, "stage1_pass.xlsx"), index=False)

    # 제외본: 제외단계 + 제외사유 부여
    excl_out = excluded.copy()
    excl_out.insert(1, "제외단계", "1차")
    excl_out.rename(columns={"_제외사유": "제외사유"}, inplace=True)
    excl_out.to_excel(os.path.join(out_dir, "stage1_excluded.xlsx"), index=False)

    # 2차용 경량 JSON
    def cell(row, role, limit=None):
        c = col.get(role)
        if not c or c not in row or pd.isna(row[c]):
            return ""
        s = str(row[c]).strip()
        return s[:limit] if limit else s

    records = []
    for _, row in passed.iterrows():
        records.append({
            "uid": int(row["_uid"]),
            "출원번호": cell(row, "출원번호"),
            "명칭": cell(row, "발명의명칭"),
            "요약": cell(row, "요약", 1200),
            "ipc": cell(row, "ipc", 200),
            "청구항": cell(row, "청구항", 1000),
        })
    json.dump(records, open(os.path.join(out_dir, "stage1_pass.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    meta = {
        "folder": folder,
        "asof": asof.strftime("%Y-%m-%d"),
        "years": args.years,
        "cutoff": cutoff.strftime("%Y-%m-%d"),
        "column_map": col,
        "total": int(len(df)),
        "stage1_pass": int(len(passed)),
        "stage1_excluded": int(len(excluded)),
        "status_blank_held": int(held_blank),
    }
    json.dump(meta, open(os.path.join(out_dir, "_meta.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    log("=" * 50)
    log(f"총 {len(df)}건 -> 1차 통과 {len(passed)}건 / 제외 {len(excluded)}건")
    if held_blank:
        log(f"※ 법적상태 공란 {held_blank}건은 '판정 보류'로 통과 "
            f"(KIPRIS 해외검색 등 법적상태 미제공 데이터 — 등록 여부는 2차 의미판정에서 확인)")
    log(f"2차 판정 대상 {len(records)}건 -> {os.path.join(out_dir, 'stage1_pass.json')}")
    log("=" * 50)


if __name__ == "__main__":
    main()
