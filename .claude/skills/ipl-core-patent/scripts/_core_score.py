# -*- coding: utf-8 -*-
"""
핵심특허 정량 스코어링. 가용한 정량지표를 자동 감지해 정규화 가중합 점수를 산출하고,
상위 후보를 AI 의미검토용으로 추출한다.

지표(가용한 것만 사용, 가중치 자동 재정규화):
  citations(피인용) 0.35 / family(패밀리) 0.25 / claims(청구항수) 0.20
  / remaining_term(잔여존속기간, 출원일+20년 가정) 0.10 / ipc_breadth(IPC 폭) 0.10

Usage: python _core_score.py <folder> [--top 30] [--final 12] [--weights weights.json]
출력: <folder>/_ipl/core/{core_scores.csv, candidates.json, core_patents.json}
core_patents.json 은 잠정(상위 final건, reason 비어있음). AI 검토 후 Claude가 reason을 채우고 부적합을 교체한다.
"""
import sys, os, json, re
from _ipl_io import ensure_pkgs, load_patents, resolve, ipl_dir, parse_year, clean_id, fmt_patent_no

ensure_pkgs(["pandas", "numpy", "openpyxl"])
import numpy as np
import pandas as pd

DEFAULT_W = {"citations": 0.35, "family": 0.25, "claims": 0.20,
             "remaining_term": 0.10, "ipc_breadth": 0.10}
ASOF_YEAR = 2026  # 잔여존속기간 기준연도 (필요시 인자화)


def minmax(s):
    s = pd.to_numeric(s, errors="coerce")
    lo, hi = s.min(), s.max()
    if pd.isna(lo) or hi == lo:
        return pd.Series(np.where(s.notna(), 0.5, 0.0), index=s.index)
    return ((s - lo) / (hi - lo)).fillna(0.0)


def count_claims_text(v):
    if v is None:
        return np.nan
    s = str(v)
    # "청구항 1", "1." 패턴 또는 줄 수로 추정
    m = re.findall(r"(?:^|\n)\s*(?:청구항\s*)?\d+[\.\s]", s)
    return len(m) if m else (np.nan if len(s) < 5 else 1)


def count_ipc(v):
    if v is None:
        return np.nan
    return len(set(re.findall(r"[A-H]\d{2}[A-Z]", str(v).upper()))) or np.nan


def main():
    folder = sys.argv[1]
    top = int(sys.argv[sys.argv.index("--top") + 1]) if "--top" in sys.argv else 30
    final = int(sys.argv[sys.argv.index("--final") + 1]) if "--final" in sys.argv else 12
    weights = dict(DEFAULT_W)
    if "--weights" in sys.argv:
        with open(sys.argv[sys.argv.index("--weights") + 1], encoding="utf-8") as _wf:
            weights.update(json.load(_wf))

    df = load_patents(folder).reset_index(drop=True)
    r = resolve(df)
    out = ipl_dir(folder, "core")

    metrics = {}
    avail = {}
    # citations
    if r["citations"] and pd.to_numeric(df[r["citations"]], errors="coerce").notna().any():
        metrics["citations"] = pd.to_numeric(df[r["citations"]], errors="coerce"); avail["citations"] = True
    # family
    if r["family"] and pd.to_numeric(df[r["family"]], errors="coerce").notna().any():
        metrics["family"] = pd.to_numeric(df[r["family"]], errors="coerce"); avail["family"] = True
    # claims (숫자 컬럼 우선, 없으면 청구항 텍스트에서 카운트)
    if r["claims"] and pd.to_numeric(df[r["claims"]], errors="coerce").notna().any():
        metrics["claims"] = pd.to_numeric(df[r["claims"]], errors="coerce"); avail["claims"] = True
    elif r["claims_text"]:
        c = df[r["claims_text"]].map(count_claims_text)
        if c.notna().any():
            metrics["claims"] = c; avail["claims"] = True
    # remaining_term
    if r["filing_date"]:
        yr = parse_year(df[r["filing_date"]])
        rt = (yr + 20 - ASOF_YEAR).clip(lower=0)
        if rt.notna().any():
            metrics["remaining_term"] = rt; avail["remaining_term"] = True
            df["_year"] = yr
    # ipc_breadth
    ipc_col = r["ipc_all"] or r["ipc_main"]
    if ipc_col:
        ib = df[ipc_col].map(count_ipc)
        if ib.notna().any():
            metrics["ipc_breadth"] = ib; avail["ipc_breadth"] = True

    if not metrics:
        # 정량지표 전무 → AI 100% 신호
        (out / "candidates.json").write_text(json.dumps(
            {"no_metrics": True, "note": "정량지표 컬럼이 전혀 없음 — AI 의미판단 100%로 진행",
             "candidates": []}, ensure_ascii=False, indent=2), encoding="utf-8")
        print("[warn] 정량지표 없음 — candidates.json에 표시. Claude가 텍스트로 직접 선별 필요.")
        return

    # 가중치: 가용 지표만으로 재정규화
    wsum = sum(weights[k] for k in metrics)
    w = {k: weights[k] / wsum for k in metrics}

    norm = pd.DataFrame({k: minmax(v) for k, v in metrics.items()})
    score = sum(norm[k] * w[k] for k in metrics)
    df["_score"] = score

    # core_scores.csv
    cols_csv = {}
    if r["number"]: cols_csv["번호"] = df[r["number"]]
    if r["title"]: cols_csv["명칭"] = df[r["title"]]
    if r["applicant"]: cols_csv["출원인"] = df[r["applicant"]]
    if "_year" in df: cols_csv["출원연도"] = df["_year"]
    for k in metrics:
        cols_csv[f"raw_{k}"] = metrics[k]
        cols_csv[f"n_{k}"] = norm[k].round(3)
    cols_csv["score"] = df["_score"].round(4)
    csvdf = pd.DataFrame(cols_csv).sort_values("score", ascending=False)
    csvdf.to_csv(out / "core_scores.csv", index=False, encoding="utf-8-sig")

    # 상위 후보 (AI 검토용 텍스트 포함)
    order = df["_score"].sort_values(ascending=False).index[:top]
    cands = []
    for rank, i in enumerate(order, 1):
        row = df.loc[i]
        cands.append({
            "rank": rank,
            "number": fmt_patent_no(row[r["number"]]) if r["number"] else f"row{i}",
            "title": str(row[r["title"]])[:120] if r["title"] else "",
            "applicant": str(row[r["applicant"]])[:60] if r["applicant"] else "",
            "year": int(row["_year"]) if "_year" in df and pd.notna(row.get("_year")) else None,
            "score": round(float(row["_score"]), 4),
            "metrics": {k: (None if pd.isna(metrics[k].loc[i]) else float(metrics[k].loc[i])) for k in metrics},
            "abstract": str(row[r["abstract"]])[:500] if r["abstract"] else "",
            "problem": str(row[r["problem"]])[:300] if r["problem"] else "",
            "solution": str(row[r["solution"]])[:300] if r["solution"] else "",
        })
    (out / "candidates.json").write_text(json.dumps(
        {"weights_used": w, "metrics_available": list(metrics.keys()),
         "candidates": cands}, ensure_ascii=False, indent=2), encoding="utf-8")

    # 잠정 core_patents.json (상위 final, reason 비움)
    prov = []
    for c in cands[:final]:
        prov.append({"rank": c["rank"], "number": c["number"], "title": c["title"],
                     "applicant": c["applicant"], "year": c["year"], "score": c["score"],
                     "metrics": c["metrics"], "reason": ""})
    (out / "core_patents.json").write_text(json.dumps(prov, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[ok] 스코어링 완료. 가용지표={list(metrics.keys())} 가중치={ {k:round(v,2) for k,v in w.items()} }")
    print(f"     상위 후보 {len(cands)}건 → candidates.json (AI 검토 대상)")
    print(f"     잠정 핵심특허 {len(prov)}건 → core_patents.json")
    print(f"     1위: {cands[0]['number']} {cands[0]['title'][:40]} (score={cands[0]['score']})")


if __name__ == "__main__":
    main()
