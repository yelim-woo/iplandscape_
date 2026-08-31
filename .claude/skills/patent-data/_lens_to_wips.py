# -*- coding: utf-8 -*-
"""
Lens.org export CSV -> WIPS 스키마 유효데이터.xlsx 변환 + 정제.
- 패밀리 단위 중복제거(Simple Family Members 기준, 대표는 Granted 우선·최신)
- 최근 N년(출원연도) 필터
- WIPS 표준 컬럼명으로 변환하여 기존 patent-trend/patent-quality/ipl-* 스킬과 호환

Usage: python _lens_to_wips.py <lens.csv> <출력폴더> [--years 10] [--asof 2026-06-05] [--legal active|all]
출력: <출력폴더>/유효데이터.xlsx, <출력폴더>/_ipl/data_summary.json
"""
import sys, os, json, re, argparse
from datetime import datetime
import pandas as pd
import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def first_token(val, seps=r"[;|]{1,2}"):
    if pd.isna(val):
        return None
    parts = re.split(seps, str(val))
    return parts[0].strip() if parts else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("outdir")
    ap.add_argument("--years", type=int, default=10)
    ap.add_argument("--asof", default=datetime.today().strftime("%Y-%m-%d"))
    ap.add_argument("--legal", default="all", choices=["all", "active", "granted"])
    args = ap.parse_args()

    asof = datetime.strptime(args.asof, "%Y-%m-%d")
    cutoff = asof.year - args.years
    os.makedirs(args.outdir, exist_ok=True)
    os.makedirs(os.path.join(args.outdir, "_ipl"), exist_ok=True)

    d = pd.read_csv(args.csv, encoding="utf-8", dtype=str, low_memory=False)
    raw = len(d)
    print(f"[lens] 원본 {raw}건 로드", flush=True)

    # 출원연도 (Application Date 없으면 전부 NaN)
    _ad = d.get("Application Date")
    if _ad is None:
        _ad = pd.Series([""] * len(d), index=d.index)
        print("[lens] WARN: 'Application Date' 컬럼 없음 — 출원연도/필터 제한됨", flush=True)
    d["_year"] = pd.to_numeric(_ad.astype(str).str.extract(r"((?:19|20)\d{2})")[0], errors="coerce")

    # 정렬 우선순위: Granted 우선, 최신 출원
    dtype_rank = {"Granted Patent": 0, "Limited Patent": 1, "Patent of Addition": 2,
                  "Patent Application": 3, "Search Report": 9, "Unknown": 8}
    d["_drank"] = d["Document Type"].map(lambda x: dtype_rank.get(str(x), 5))
    d["_yfill"] = d["_year"].fillna(0)
    d = d.sort_values(["_drank", "_yfill"], ascending=[True, False])

    # 패밀리 단위 중복제거: Simple Family Members(없으면 Lens ID, 둘 다 없으면 행 고유키=중복제거 안 함)
    fam_raw = d.get("Simple Family Members")
    lid = d.get("Lens ID")
    uniq = d.index.to_series().astype(str)
    if fam_raw is not None:
        fam_key = fam_raw.where(fam_raw.notna() & (fam_raw.astype(str).str.strip() != ""),
                                lid if lid is not None else uniq)
    elif lid is not None:
        fam_key = lid
    else:
        fam_key = uniq
    d["_famkey"] = fam_key
    before = len(d)
    d = d.drop_duplicates(subset=["_famkey"], keep="first")
    fam_removed = before - len(d)
    print(f"[lens] 패밀리 중복제거: {before} -> {len(d)} ({fam_removed} 제거)", flush=True)

    # 최근 N년
    n_before = len(d)
    d = d[d["_year"] >= cutoff]
    recent_removed = n_before - len(d)

    # 법적상태 필터(선택)
    legal_removed = 0
    if args.legal == "active":
        n = len(d); d = d[d["Legal Status"].astype(str).str.upper().isin(["ACTIVE", "PATENTED"])]; legal_removed = n - len(d)
    elif args.legal == "granted":
        n = len(d); d = d[d["Document Type"].astype(str).isin(["Granted Patent", "Limited Patent", "Patent of Addition"])]; legal_removed = n - len(d)

    # ---- WIPS 스키마로 매핑 ----
    out = pd.DataFrame()
    out["출원번호"] = d.get("Application Number")
    out["등록번호"] = d.get("Display Key")
    out["발명의 명칭"] = d.get("Title")
    out["요약"] = d.get("Abstract")
    _ad2 = d.get("Application Date")
    out["출원일"] = (_ad2.astype(str).str.replace("-", "", regex=False) if _ad2 is not None
                   else pd.Series([""] * len(d), index=d.index))
    out["국가코드"] = d.get("Jurisdiction")
    out["출원인"] = d.get("Applicants").map(first_token)
    out["출원인 대표명화 영문명"] = out["출원인"]
    ipcr = d.get("IPCR Classifications")
    cpc = d.get("CPC Classifications")
    out["Current IPC Main"] = ipcr.map(first_token) if ipcr is not None else None
    out["Current IPC All"] = ipcr if ipcr is not None else cpc
    out["Current CPC All"] = cpc
    out["피인용수"] = d.get("Cited by Patent Count")
    out["인용수"] = d.get("Cites Patent Count")
    out["패밀리수"] = d.get("Simple Family Size")
    out["패밀리 국가수"] = d.get("Simple Family Member Jurisdictions").map(
        lambda v: len(str(v).split(";;")) if pd.notna(v) else None) if "Simple Family Member Jurisdictions" in d else None
    out["법적상태"] = d.get("Legal Status")
    out["Document Type"] = d.get("Document Type")
    out["출원연도"] = d["_year"].astype("Int64")
    out["Lens ID"] = d.get("Lens ID")
    out["URL"] = d.get("URL")

    valid = out.reset_index(drop=True)
    out_path = os.path.join(args.outdir, "유효데이터.xlsx")
    valid.to_excel(out_path, index=False)

    yrs = valid["출원연도"].dropna()
    juris = d["Jurisdiction"].value_counts().head(8).to_dict() if "Jurisdiction" in d.columns else {}
    summary = {
        "raw_count": int(raw), "valid_count": int(len(valid)),
        "excluded_count": int(raw - len(valid)),
        "family_dedup_removed": int(fam_removed),
        "recent_removed": int(recent_removed), "legal_removed": int(legal_removed),
        "year_range": [int(yrs.min()), int(yrs.max())] if len(yrs) else None,
        "asof": args.asof, "years": args.years, "legal_filter": args.legal,
        "jurisdiction_top": {k: int(v) for k, v in juris.items()},
        "criteria_path": f"Lens 변환: 패밀리 중복제거 + 출원연도>={cutoff}" + (f" + 법적상태={args.legal}" if args.legal != "all" else ""),
        "exclude_reasons": {
            "패밀리 중복": int(fam_removed),
            f"출원연도<{cutoff}": int(recent_removed),
            "법적상태 필터": int(legal_removed),
        },
        "valid_path": out_path,
        "note": "Lens 데이터는 해결과제/해결수단 컬럼이 없어 O/S Matrix는 생략(기술흐름도+등고선으로 정성분석).",
    }
    json.dump(summary, open(os.path.join(args.outdir, "_ipl", "data_summary.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("=" * 55, flush=True)
    print(f"[lens] 유효 {len(valid)}건 / 연도 {summary['year_range']} / 관할 {list(juris)[:5]}", flush=True)
    print(f"[lens] 저장: {out_path}", flush=True)
    print("=" * 55, flush=True)


if __name__ == "__main__":
    main()
