# -*- coding: utf-8 -*-
"""
Stage 3: 2차 LLM 판정 결과(stage2_verdicts.json)를 1차 통과본에 적용해
최종 유효데이터 엑셀 + 제외로그 엑셀을 만든다.

입력 (<raw_folder>/_filter/):
  stage1_pass.xlsx        1차 통과본 (모든 원본 컬럼 + _uid)
  stage1_excluded.xlsx    1차 제외본 (제외단계/제외사유 포함)
  stage2_verdicts.json    [{uid, valid, reason}]  (Claude 가 작성)

출력 (<raw_folder>/):
  유효데이터.xlsx          1차+2차 모두 통과 (원본 컬럼만, 보조컬럼 제거)
  제외로그.xlsx            1차 제외 + 2차 제외 통합 (제외단계/제외사유 포함)

Usage:
  python _apply_verdicts.py <raw_folder> [--keep-uid]
"""
import sys, os, re, json, argparse
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def log(msg):
    print(f"[stage3] {msg}", flush=True)


# 같은 개념인데 이름만 다른 컬럼 그룹(대표 이름을 첫 항목으로, 대소문자/공백 무시로 매칭).
# KIPRIS 국내+해외 익스포트처럼 스키마가 섞이면 '발명의명칭' vs '발명의 명칭', 'IPC분류' vs 'IPC'
# 처럼 이름이 미세하게 갈라져, 통합하지 않으면 해외행의 IPC·명칭이 다른 컬럼에 남아
# 정량(IPC 분포)·정성(등고선·기술흐름) 차트에서 통째로 누락된다.
_CONCEPT_GROUPS = [
    ["발명의명칭", "발명의 명칭", "발명의명칭(국문)", "invention title", "title"],
    ["IPC분류", "IPC", "IPC 분류", "current ipc main", "current ipc all"],
    ["CPC분류", "CPC", "CPC 분류"],
    ["요약", "abstract", "초록"],
    ["출원인", "applicant"],
    ["출원일자", "출원일", "filing date"],
    ["등록번호", "registration number"],
    ["국가", "국가코드", "country"],
]


def _norm_name(x):
    return re.sub(r"\s+", "", str(x)).lower()


def unify_columns(df):
    """국내/해외 스키마가 섞인 입력에서 같은 개념이 이름만 달라 갈라진 컬럼을 하나로 합친다.
    대표(첫 등장) 컬럼의 빈칸을 변형 컬럼 값으로 채우고 중복 컬럼은 제거한다. 추가로 국가가
    비어 있고 출원번호가 숫자만이면(=국내 출원번호) 'KR'로 보정한다. 원본 대비 병합된 그룹을 로그로 남긴다."""
    def _empty(s):
        return s.isna() | s.astype(str).str.strip().str.lower().isin(["", "nan", "none"])

    cols_lower = {c: _norm_name(c) for c in df.columns}
    merged = []
    for group in _CONCEPT_GROUPS:
        gset = {_norm_name(v) for v in group}
        members = [c for c in df.columns if cols_lower.get(c) in gset]
        if len(members) < 2:
            continue
        canon = members[0]
        for other in members[1:]:
            mask = _empty(df[canon]) & ~_empty(df[other])
            df.loc[mask, canon] = df.loc[mask, other]
        drop = [m for m in members[1:] if m in df.columns]
        df = df.drop(columns=drop)
        merged.append(f"{canon} <- {', '.join(drop)}")

    # 국가 보정: 국가 컬럼이 있는데 비어 있고 출원번호가 숫자만이면 KR(국내 출원번호 형식)
    ctry_col = next((c for c in df.columns if cols_lower.get(c) in {"국가", "국가코드", "country"}), None)
    appno_col = next((c for c in df.columns if _norm_name(c) in {"출원번호", "applicationnumber"}), None)
    if ctry_col and appno_col:
        blank = _empty(df[ctry_col])
        digit_appno = df[appno_col].astype(str).str.strip().str.match(r"^\d{6,}$")
        fillmask = blank & digit_appno
        n = int(fillmask.sum())
        if n:
            df.loc[fillmask, ctry_col] = "KR"
            merged.append(f"{ctry_col} 빈칸 {n}건 -> 'KR'(국내 출원번호)")

    if merged:
        log("컬럼 통합(국내/해외 스키마 정합): " + " | ".join(merged))
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--keep-uid", action="store_true", help="출력에 _uid 컬럼 유지")
    args = ap.parse_args()

    folder = os.path.abspath(args.folder)
    fdir = os.path.join(folder, "_filter")
    pass_xlsx = os.path.join(fdir, "stage1_pass.xlsx")
    excl_xlsx = os.path.join(fdir, "stage1_excluded.xlsx")
    verdicts_json = os.path.join(fdir, "stage2_verdicts.json")

    for p in (pass_xlsx, verdicts_json):
        if not os.path.exists(p):
            raise SystemExit(f"[stage3] ERROR: 파일 없음 {p}")

    passed = pd.read_excel(pass_xlsx, engine="openpyxl")
    verdicts = json.load(open(verdicts_json, encoding="utf-8"))
    vmap = {int(v["uid"]): v for v in verdicts}

    # uid 누락 검사: 판정 안 된 건은 보수적으로 '제외(미판정)' 처리
    valid_uids, invalid_rows = [], []
    for _, row in passed.iterrows():
        uid = int(row["_uid"])
        v = vmap.get(uid)
        if v is None:
            invalid_rows.append((uid, "2차 미판정"))
        elif v.get("valid"):
            valid_uids.append(uid)
        else:
            invalid_rows.append((uid, "기준 비부합: " + str(v.get("reason", "")).strip()))

    valid_df = passed[passed["_uid"].isin(valid_uids)].copy()

    # 2차 제외분 = stage1 통과했으나 valid=False
    inv_uid_set = {u for u, _ in invalid_rows}
    stage2_excl = passed[passed["_uid"].isin(inv_uid_set)].copy()
    reason_map = {u: r for u, r in invalid_rows}
    stage2_excl.insert(1, "제외단계", "2차")
    stage2_excl["제외사유"] = stage2_excl["_uid"].map(reason_map)

    # 1차 제외분 로드 (있으면)
    parts = []
    if os.path.exists(excl_xlsx):
        s1 = pd.read_excel(excl_xlsx, engine="openpyxl")
        parts.append(s1)
    parts.append(stage2_excl)
    excl_log = pd.concat(parts, ignore_index=True, sort=False) if parts else pd.DataFrame()

    # 출력: 보조 컬럼 정리
    drop_cols = [] if args.keep_uid else ["_uid"]
    valid_out = valid_df.drop(columns=[c for c in drop_cols if c in valid_df.columns])
    # 국내/해외 스키마 정합: 갈라진 개념 컬럼(명칭·IPC 등) 통합 → 해외행이 정량/정성 차트에 반영됨
    valid_out = unify_columns(valid_out)
    if not args.keep_uid and "_uid" in excl_log.columns:
        excl_log = excl_log.drop(columns=["_uid"])

    out_valid = os.path.join(folder, "유효데이터.xlsx")
    out_log = os.path.join(folder, "제외로그.xlsx")
    valid_out.to_excel(out_valid, index=False)
    excl_log.to_excel(out_log, index=False)

    log("=" * 50)
    log(f"최종 유효데이터: {len(valid_out)}건 -> {out_valid}")
    log(f"제외로그: {len(excl_log)}건 (1차+2차) -> {out_log}")
    log("=" * 50)


if __name__ == "__main__":
    main()
