# -*- coding: utf-8 -*-
"""
구간형 O/S Matrix (전체) — Object(해결과제) × Solution(해결수단) 매트릭스를
출원 구간(1·2·3구간)으로 쪼개, 각 조합의 '대각선(같은 구간끼리)'에만 건수를 표기한다.
대각선(1구간→2→3)을 따라 읽으면 그 조합의 시계열 증감이 보이고, 조합은 성장/공백/신규/무의미로 색분류된다.

- 행=Solution(해결수단, 상위 N), 각 행은 1·2·3구간 서브행
- 열=Object(해결과제, 상위 N), 각 열은 1·2·3구간 서브열
- 값 셀 = (O,S,구간 p)의 대각선 칸(가로구간=세로구간=p). 비대각선은 옅은 사선(빈칸)
- 범주: 신규(1·2구간0·3구간≥1) / 성장(3구간>1구간·총합≥3) / 무의미(총합1~2) / 공백(셀0이나 해당 O·S는 타 조합에서 활발) / 일반

카테고리(키워드)는 <folder>/_ipl/{competitor,qualitative}/os_categories.json 재사용(없으면 내장 기본값).
Usage: python _os_matrix.py <folder> [--top 6] [--periods 3]
출력: <folder>/_ipl/qualitative/{os_matrix_periods.png, os_matrix_periods.json}
"""
import sys, os, json, re
from collections import Counter
from _ipl_io import (ensure_pkgs, korean_font, load_patents, resolve, ipl_dir, parse_year,
                     IPL_PALETTE)

ensure_pkgs(["pandas", "numpy", "matplotlib", "openpyxl", "pillow"])
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyBboxPatch
from matplotlib import rcParams
rcParams["font.family"] = korean_font()
rcParams["axes.unicode_minus"] = False

# 범주 색 (에디토리얼 톤) — 특이범주는 또렷하게, 일반(활성)은 옅은 중립색
CAT_COLOR = {
    "성숙": "#34495E",    # 진한 차콜네이비 — 핵심·주류(전 구간 꾸준+다량, 레드오션)
    "성장": "#2E8B6F",    # 초록(틸) — 구간 증가
    "공백": "#5B8FC9",    # 파랑 — White Space(빈 기회 칸, 점선)
    "신규": "#E08A2B",    # 주황 — 최근 등장
    "일반": "#D7DEE5",    # 옅은 중립 슬레이트 — 활성 baseline(특이범주 아님)
}
WS_MIN = 3       # 공백 판정: 해당 O·S 행/열 총합이 이 이상이면 '활발'로 보고 빈칸을 기회로 표시
CORE_FLOOR = 8   # 성숙 판정 최소 총합 하한(데이터 분포의 상위 분위와 함께 사용)

DEFAULT_CATS = {
    "object": [["피부 미백", ["미백", "whiten", "brighten", "melanin", "tyrosinase"]],
               ["주름·항노화", ["주름", "노화", "anti-aging", "wrinkle", "antiaging", "elasticity"]],
               ["보습·장벽", ["보습", "수분", "장벽", "moistur", "hydrat", "barrier"]],
               ["항염·진정", ["항염", "진정", "anti-inflamm", "soothing", "irritation"]],
               ["항산화", ["항산화", "antioxidant", "radical", "oxidative"]],
               ["항균·여드름", ["항균", "여드름", "antibacterial", "acne", "antimicrobial"]],
               ["모발·두피", ["모발", "두피", "탈모", "hair", "scalp", "alopecia"]],
               ["체중·대사", ["체중", "비만", "대사", "obesity", "metabolic", "weight"]]],
    "solution": [["식물 추출물", ["추출물", "extract", "추출"]],
                 ["복합 추출물", ["복합", "혼합", "combination", "complex", "mixture"]],
                 ["발효물", ["발효", "ferment"]],
                 ["단일 분리성분", ["분리", "정제", "단일", "isolat", "purif", "compound"]],
                 ["제형·전달체", ["제형", "리포좀", "나노", "전달", "formulation", "liposome", "nano", "carrier"]],
                 ["제조·공정", ["제조방법", "공정", "process", "method for prepar", "manufactur"]]],
}


def load_cats(folder):
    for sub in ("competitor", "qualitative"):
        p = os.path.join(folder, "_ipl", sub, "os_categories.json")
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as f:
                    c = json.load(f)
                if c.get("object") and c.get("solution"):
                    return c
            except Exception:
                pass
    return DEFAULT_CATS


def classify(text, group):
    if not isinstance(text, str) or not text.strip():
        return None
    t = text.lower()
    for label, kws in group:
        if any(k.lower() in t for k in kws):
            return label
    return None


def period_of(year, y0, y1):
    if year is None or pd.isna(year):
        return None
    if year <= y0:
        return 1
    if year <= y1:
        return 2
    return 3


def categorize(series, t_core):
    """구간 series=[c1,c2,c3] → 범주. t_core=성숙(핵심) 총합 임계."""
    c1, c2, c3 = series
    total = c1 + c2 + c3
    if total == 0:
        return "공백후보"                      # 0칸 — 행/열 활성도 보고 공백 확정
    if c1 == 0 and c2 == 0 and c3 >= 1:
        return "신규"                          # 최근(3구간)에만 등장
    if min(c1, c2, c3) >= 1 and total >= t_core:
        return "성숙"                          # 전 구간 꾸준 + 다량 = 핵심·주류(레드오션)
    if total >= 3 and c3 > c1:
        return "성장"                          # 증가 추세(아직 핵심 수준은 아님)
    return "일반"                              # 활성 baseline


def main():
    folder = sys.argv[1]
    topn = int(sys.argv[sys.argv.index("--top") + 1]) if "--top" in sys.argv else 6
    df = load_patents(folder)
    r = resolve(df)
    out = ipl_dir(folder, "qualitative")
    cats = load_cats(folder)
    objs_def, sols_def = cats["object"], cats["solution"]

    # 텍스트(요약+명칭+과제+수단)·연도
    def big_text(row):
        parts = []
        for role in ("abstract", "title", "problem", "solution"):
            col = r.get(role)
            if col and pd.notna(row.get(col)):
                parts.append(str(row[col]))
        return " ".join(parts)
    df["_txt"] = df.apply(big_text, axis=1)
    df["_year"] = parse_year(df[r["filing_date"]]) if r.get("filing_date") else None
    df["_obj"] = df["_txt"].map(lambda t: classify(t, objs_def))
    df["_sol"] = df["_txt"].map(lambda t: classify(t, sols_def))

    yrs = pd.to_numeric(df["_year"], errors="coerce").dropna()
    if yrs.empty:
        (out / "os_matrix_periods.json").write_text(json.dumps({"error": "출원연도 없음"}, ensure_ascii=False), encoding="utf-8")
        print("[error] 출원연도 컬럼 없음"); return
    ymin, ymax = int(yrs.min()), int(yrs.max())
    span = max(1, (ymax - ymin))
    y0, y1 = ymin + span / 3.0, ymin + 2 * span / 3.0
    df["_p"] = df["_year"].map(lambda y: period_of(y, y0, y1))

    sub = df[df["_obj"].notna() & df["_sol"].notna() & df["_p"].notna()].copy()
    if len(sub) < 5:
        (out / "os_matrix_periods.json").write_text(json.dumps(
            {"error": f"분류된 특허 {len(sub)}건 — 부족"}, ensure_ascii=False), encoding="utf-8")
        print(f"[error] 분류 {len(sub)}건 — 부족"); return

    # 상위 N Object·Solution
    top_obj = [o for o, _ in Counter(sub["_obj"]).most_common(topn)]
    top_sol = [s for s, _ in Counter(sub["_sol"]).most_common(topn)]
    nO, nS, P = len(top_obj), len(top_sol), 3

    # counts[o][s][p]
    cnt = {o: {s: [0, 0, 0] for s in top_sol} for o in top_obj}
    for _, row in sub.iterrows():
        o, s, p = row["_obj"], row["_sol"], int(row["_p"])
        if o in cnt and s in cnt[o]:
            cnt[o][s][p - 1] += 1

    # 행/열 총합(공백 판정용)
    obj_tot = {o: sum(sum(cnt[o][s]) for s in top_sol) for o in top_obj}
    sol_tot = {s: sum(sum(cnt[o][s]) for o in top_obj) for s in top_sol}

    # 성숙(핵심) 총합 임계 — 양수 조합 총합의 상위 분위와 하한 중 큰 값
    pos_tot = [sum(cnt[o][s]) for o in top_obj for s in top_sol if sum(cnt[o][s]) > 0]
    t_core = max(CORE_FLOOR, int(np.percentile(pos_tot, 70))) if pos_tot else CORE_FLOOR

    # 조합 범주
    combo_cat = {}
    for o in top_obj:
        for s in top_sol:
            cat = categorize(cnt[o][s], t_core)
            if cat == "공백후보":
                cat = "공백" if (obj_tot[o] >= WS_MIN and sol_tot[s] >= WS_MIN) else "_빈칸"
            combo_cat[(o, s)] = cat

    # 공백(White Space) 기회점수·순위 — Object·Solution 각각은 활발한데 교차가 빌수록↑(잠재 결합기회)
    ws = []
    for o in top_obj:
        for s in top_sol:
            if combo_cat[(o, s)] == "공백":
                opp = float(np.sqrt(obj_tot[o] * sol_tot[s]))   # 양 margin의 기하평균
                ws.append((o, s, round(opp, 1)))
    ws.sort(key=lambda x: -x[2])
    ws_rank = {(o, s): i + 1 for i, (o, s, _) in enumerate(ws)}   # 1 = 최우선 기회
    TOPK = min(6, len(ws))
    CIRC = "①②③④⑤⑥⑦⑧⑨⑩"

    # ---------- 렌더 ----------
    CW, RH = 1.0, 1.0                 # 셀 크기(데이터 좌표)
    lab_w = 3.6                       # 좌측 Solution 라벨 폭
    top_h = 2.2                       # 상단 Object 라벨 높이
    NC, NR = nO * P, nS * P
    fig_w = max(12.5, (NC * CW + lab_w) * 0.62)
    fig_h = max(7.5, (NR * RH + top_h) * 0.62)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=150)
    fig.set_facecolor("#ffffff"); ax.set_facecolor("#ffffff")

    def cell_xy(ci, ri):
        # ci: 0..NC-1 (좌→우), ri: 0..NR-1 (위→아래)
        return ci * CW, (NR - 1 - ri) * RH

    maxv = max([cnt[o][s][p] for o in top_obj for s in top_sol for p in range(P)] + [1])

    for oi, o in enumerate(top_obj):
        for si, s in enumerate(top_sol):
            cat = combo_cat[(o, s)]
            base = CAT_COLOR.get(cat) if cat in CAT_COLOR else None
            for p in range(P):
                # 대각선 칸: 가로구간 p == 세로구간 p
                ci, ri = oi * P + p, si * P + p
                x, y = cell_xy(ci, ri)
                v = cnt[o][s][p]
                if v > 0 and base:
                    # 일반(활성)은 옅게, 특이범주(성장/신규/무의미)는 또렷하게
                    if cat == "일반":
                        alpha = 0.30 + 0.32 * (v / maxv)
                    else:
                        alpha = 0.45 + 0.50 * (v / maxv)
                    ax.add_patch(Rectangle((x, y), CW, RH, facecolor=base, alpha=alpha,
                                           edgecolor="white", linewidth=1.0, zorder=2))
                    dark = (cat != "일반") and alpha > 0.6
                    ax.text(x + CW / 2, y + RH / 2, str(v), ha="center", va="center",
                            fontsize=9.5, fontweight="bold",
                            color="white" if dark else "#222222", zorder=3)
                elif cat == "공백":
                    # White Space: 상위 기회는 밝게+순위 마커, 그 외는 옅은 점선
                    rk = ws_rank.get((o, s))
                    top = rk is not None and rk <= TOPK
                    ax.add_patch(Rectangle((x, y), CW, RH,
                                           facecolor=CAT_COLOR["공백"], alpha=0.42 if top else 0.12,
                                           edgecolor=CAT_COLOR["공백"], linewidth=1.4 if top else 0.8,
                                           linestyle="solid" if top else (0, (2, 2)), zorder=2))
                    if top and p == 1:   # 블록 중앙(2구간) 칸에 순위 마커
                        ax.text(x + CW / 2, y + RH / 2, CIRC[rk - 1] if rk <= 10 else str(rk),
                                ha="center", va="center", fontsize=13, fontweight="bold",
                                color="white", zorder=3)
            # 비대각선 사선(빈칸) — 블록 내 off-diagonal
            for pr in range(P):
                for pc in range(P):
                    if pr == pc:
                        continue
                    ci, ri = oi * P + pc, si * P + pr
                    x, y = cell_xy(ci, ri)
                    ax.add_patch(Rectangle((x, y), CW, RH, facecolor="none",
                                           edgecolor="#f0f0f0", linewidth=0.6, hatch="////", zorder=1))

    # 블록 경계선(Object/Solution 그룹 구분)
    for oi in range(nO + 1):
        ax.plot([oi * P * CW, oi * P * CW], [0, NR * RH], color="#c9c9c9", lw=1.1, zorder=4)
    for si in range(nS + 1):
        ax.plot([0, NC * CW], [si * P * RH, si * P * RH], color="#c9c9c9", lw=1.1, zorder=4)
    # 옅은 셀 격자
    for ci in range(NC + 1):
        ax.plot([ci * CW, ci * CW], [0, NR * RH], color="#ededed", lw=0.5, zorder=0)
    for ri in range(NR + 1):
        ax.plot([0, NC * CW], [ri * RH, ri * RH], color="#ededed", lw=0.5, zorder=0)

    # 상단 Object 라벨 + 구간 서브라벨
    for oi, o in enumerate(top_obj):
        cx = (oi * P + P / 2) * CW
        ax.text(cx, NR * RH + 1.05, o, ha="center", va="bottom", fontsize=10,
                fontweight="bold", color="#2b2b2b", wrap=True)
        for p in range(P):
            ax.text((oi * P + p) * CW + CW / 2, NR * RH + 0.18, f"{p+1}구간",
                    ha="center", va="bottom", fontsize=7.0, color="#888888")
    # 좌측 Solution 라벨 + 구간 서브라벨
    for si, s in enumerate(top_sol):
        cy = (NR - (si * P + P / 2)) * RH
        ax.text(-lab_w + 0.15, cy, s, ha="left", va="center", fontsize=10,
                fontweight="bold", color="#2b2b2b")
        for p in range(P):
            yy = (NR - 1 - (si * P + p)) * RH + RH / 2
            ax.text(-0.12, yy, f"{p+1}구간", ha="right", va="center", fontsize=7.0, color="#888888")

    # 모서리 라벨
    ax.text(-lab_w + 0.15, NR * RH + 1.05, "Solution(수단) ↓ / Object(목적) →", ha="left", va="bottom",
            fontsize=9, color="#666666", style="italic")

    # 범례
    leg_items = [("공백", "공백·진입기회 ①②③"), ("성장", "성장(구간↑)"), ("신규", "신규(최근 등장)"), ("성숙", "성숙(핵심·레드오션)")]
    lx0 = 0
    ly = -1.35
    for i, (k, lab) in enumerate(leg_items):
        lx = lx0 + i * (NC * CW / len(leg_items))
        ax.add_patch(Rectangle((lx, ly), 0.7, 0.6, facecolor=CAT_COLOR[k], alpha=0.75,
                               edgecolor="white", lw=0.8, clip_on=False, zorder=5))
        ax.text(lx + 0.9, ly + 0.3, lab, ha="left", va="center", fontsize=8.5, color="#444444")

    ax.set_xlim(-lab_w, NC * CW + 0.1)
    ax.set_ylim(-1.9, NR * RH + top_h)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(out / "os_matrix_periods.png", dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)

    # ---------- JSON ----------
    result = {
        "objects": top_obj, "solutions": top_sol, "periods": ["1구간", "2구간", "3구간"],
        "year_bands": {"1구간": f"~{int(y0)}", "2구간": f"{int(y0)+1}~{int(y1)}", "3구간": f"{int(y1)+1}~{ymax}"},
        "classified": int(len(sub)),
        "cells": [{"object": o, "solution": s, "by_period": cnt[o][s],
                   "total": sum(cnt[o][s]), "category": combo_cat[(o, s)]}
                  for o in top_obj for s in top_sol if combo_cat[(o, s)] != "_빈칸" or sum(cnt[o][s]) > 0],
        "mature": [f"{o}×{s}" for o in top_obj for s in top_sol if combo_cat[(o, s)] == "성숙"],
        "growth": [f"{o}×{s}" for o in top_obj for s in top_sol if combo_cat[(o, s)] == "성장"],
        "new": [f"{o}×{s}" for o in top_obj for s in top_sol if combo_cat[(o, s)] == "신규"],
        "white_space": [{"rank": ws_rank[(o, s)], "object": o, "solution": s, "opportunity": sc,
                         "object_total": obj_tot[o], "solution_total": sol_tot[s]}
                        for (o, s, sc) in ws],
        "chart": str(out / "os_matrix_periods.png"),
    }
    (out / "os_matrix_periods.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ok] 구간형 O/S Matrix → {out/'os_matrix_periods.png'}")
    print(f"     분류 {len(sub)}건 · Object {nO} × Solution {nS} · 구간 {P}")
    print(f"     성숙 {len(result['mature'])} · 성장 {len(result['growth'])} · 신규 {len(result['new'])} · 공백 {len(result['white_space'])}")


if __name__ == "__main__":
    main()
