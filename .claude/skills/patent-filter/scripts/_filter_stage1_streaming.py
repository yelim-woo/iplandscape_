# -*- coding: utf-8 -*-
"""
대용량(수십만 건/수GB) WIPS raw 폴더용 메모리 안전 1차 필터.
기존 _filter_stage1.py는 전체를 메모리에 올려 OOM 위험 → 이 스크립트는 파일별 스트리밍 + 벡터화 +
필요한 컬럼만 유지한다. 등록 판정 = (등록번호 보유 ∧ 무효성 상태 아님), 출원일 = 최근 N년.

Usage: python _filter_stage1_streaming.py <folder> [--asof 2026-06-05] [--years 10] [--out 유효데이터.xlsx]
출력: <folder>/유효데이터.xlsx, <folder>/_ipl/data_summary.json, <folder>/_filter/stage1_excluded_summary.json
"""
import sys, os, glob, json, re, argparse
from datetime import datetime
import pandas as pd
import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

KEEP = [
    "WIPS ON key", "국가코드", "발명의 명칭", "요약", "AI 요약[KR,JP,CN,US,EP,PCT]",
    "기술분야 요약[KR,JP,CN,US,EP,PCT]", "해결과제 요약[KR,JP,CN,US,EP,PCT]",
    "해결수단 요약[KR,JP,CN,US,EP,PCT]", "특징 요약[KR,JP,CN,US,EP,PCT]", "효과 요약[KR,JP,CN,US,EP,PCT]",
    "대표청구항", "청구항 수", "출원번호", "출원일", "등록번호", "등록일", "공개일",
    "출원인", "출원인 대표명화 영문명", "출원인 대표명화 국문명[KR]", "출원인 국적", "발명자 수",
    "Current IPC Main", "Current IPC All", "Current CPC Main", "Current CPC All",
    "인용 문헌 수(B1)", "피인용 문헌 수(F1)", "WIPS패밀리 문헌 수(출원기준)", "WIPS패밀리 국가 수(출원기준)",
    "상태정보[KR,JP,US,EP,CN,CA,AU]", "DOCDB 법적상태",
    "존속기간(예상)만료일[KR,JP,US,EP,CN,CA,AU]", "관련도",
]
KEEPSET = set(KEEP)
STATUS_COL = "상태정보[KR,JP,US,EP,CN,CA,AU]"
NEG = "취소|무효|소멸|거절|포기|취하|실효|말소|expired|lapsed|revoked|withdrawn|rejected|abandoned|ceased|invalid|refused|dead"


def parse_year_vec(s):
    y = s.astype(str).str.extract(r"((?:19|20)\d{2})")[0]
    return pd.to_numeric(y, errors="coerce")


def clean_applicant(df):
    kr = df.get("출원인 대표명화 국문명[KR]")
    en = df.get("출원인 대표명화 영문명")
    base = df.get("출원인")
    out = base.copy() if base is not None else pd.Series([""] * len(df))
    if kr is not None:
        out = kr.where(kr.notna() & (kr.astype(str).str.strip() != ""), out)
    if en is not None:
        out = out.where(out.notna() & (out.astype(str).str.strip() != ""), en)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--asof", default=datetime.today().strftime("%Y-%m-%d"))
    ap.add_argument("--years", type=int, default=10)
    ap.add_argument("--out", default="유효데이터.xlsx")
    args = ap.parse_args()

    folder = os.path.abspath(args.folder)
    asof = datetime.strptime(args.asof, "%Y-%m-%d")
    cutoff_year = asof.year - args.years
    files = sorted(glob.glob(os.path.join(folder, "*.xlsx")))
    files = [f for f in files if not os.path.basename(f).startswith("~$")
             and os.path.basename(f) not in (args.out, "유효데이터.xlsx")
             and "_filter" not in f and "_ipl" not in f]
    print(f"[stream] {len(files)}개 파일 / cutoff 출원연도 >= {cutoff_year}", flush=True)

    kept = []
    total = 0
    held_blank = 0  # 등록번호·상태정보 둘 다 없어 '판정 보류'로 통과시킨 건수
    excl = {"등록번호 없음(미등록)": 0, "무효성 상태": 0, f"출원일<{cutoff_year}": 0, "출원일 불명": 0}
    for i, f in enumerate(files, 1):
        try:
            df = pd.read_excel(f, engine="openpyxl", usecols=lambda c: c in KEEPSET, dtype=str)
        except Exception as e:
            print(f"[stream] WARN read fail {os.path.basename(f)}: {e}", flush=True)
            continue
        n = len(df)
        total += n

        regnum = df.get("등록번호")
        has_reg = regnum.notna() & (regnum.astype(str).str.strip().replace("nan", "") != "") if regnum is not None else pd.Series(False, index=df.index)
        status = df.get(STATUS_COL)
        if status is not None:
            s_str = status.astype(str).str.strip()
            status_present = status.notna() & (s_str.str.lower() != "nan") & (s_str != "")
            neg = status.astype(str).str.contains(NEG, case=False, na=False)
        else:
            status_present = pd.Series(False, index=df.index)
            neg = pd.Series(False, index=df.index)
        yr = parse_year_vec(df["출원일"]) if "출원일" in df else pd.Series(np.nan, index=df.index)

        # 등록번호도 없고 상태정보도 없어 등록 여부를 판정할 근거 자체가 없는 행은
        # '미등록 제외'가 아니라 '판정 보류'로 통과(전량 탈락 방지 — 해외 데이터 보존).
        unknown = (~has_reg) & (~status_present)
        cond_reg = (has_reg | unknown) & ~neg
        cond_recent = yr >= cutoff_year
        keep = cond_reg & cond_recent

        # 제외 사유 집계 (보류 통과분은 제외로 세지 않는다)
        excl["등록번호 없음(미등록)"] += int((~has_reg & status_present & ~neg).sum())
        excl["무효성 상태"] += int((neg).sum())
        excl["출원일 불명"] += int(yr.isna().sum())
        excl[f"출원일<{cutoff_year}"] += int((yr.notna() & (yr < cutoff_year)).sum())
        held_blank += int((unknown & cond_recent & ~neg).sum())

        sub = df[keep].copy()
        if len(sub):
            sub["출원인"] = clean_applicant(sub)
            kept.append(sub)
        if i % 20 == 0 or i == len(files):
            sofar = sum(len(k) for k in kept)
            print(f"[stream] {i}/{len(files)} 처리 - 누적 통과 {sofar}건 / 누적 검토 {total}건", flush=True)

    if not kept:
        print("[stream] 통과 0건 — 기준을 완화하거나 데이터를 확인하세요.")
        return
    valid = pd.concat(kept, ignore_index=True)
    # 중복 제거 (WIPS ON key 또는 출원번호 기준)
    key = "WIPS ON key" if "WIPS ON key" in valid else ("출원번호" if "출원번호" in valid else None)
    before = len(valid)
    if key:
        valid = valid.drop_duplicates(subset=[key]).reset_index(drop=True)
    dups = before - len(valid)

    out_path = os.path.join(folder, args.out)
    valid.to_excel(out_path, index=False)

    yrs = parse_year_vec(valid["출원일"]) if "출원일" in valid else pd.Series([np.nan])
    os.makedirs(os.path.join(folder, "_ipl"), exist_ok=True)
    summary = {
        "raw_count": int(total), "valid_count": int(len(valid)),
        "excluded_count": int(total - len(valid)), "dup_removed": int(dups),
        "year_range": [int(yrs.min()), int(yrs.max())] if yrs.notna().any() else None,
        "asof": args.asof, "years": args.years, "cutoff_year": int(cutoff_year),
        "criteria_path": "1차 기계필터((등록번호 보유 ∨ 등록·상태정보 없음=판정보류) ∧ 무효성 상태 아님 ∧ 출원연도≥cutoff)",
        "exclude_reasons": excl,
        "status_blank_held": int(held_blank),
        "valid_path": out_path,
    }
    json.dump(summary, open(os.path.join(folder, "_ipl", "data_summary.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    os.makedirs(os.path.join(folder, "_filter"), exist_ok=True)
    json.dump(excl, open(os.path.join(folder, "_filter", "stage1_excluded_summary.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    print("=" * 55, flush=True)
    print(f"[stream] 원본 {total}건 → 유효 {len(valid)}건 (중복 {dups} 제거)", flush=True)
    if held_blank:
        print(f"[stream] ※ 등록·상태정보 없음 {held_blank}건 '판정 보류'로 통과(해외 데이터 보존, 2차 의미판정에서 확인)", flush=True)
    print(f"[stream] 출원연도 {summary['year_range']}", flush=True)
    print(f"[stream] 저장: {out_path}", flush=True)
    print("=" * 55, flush=True)


if __name__ == "__main__":
    main()
