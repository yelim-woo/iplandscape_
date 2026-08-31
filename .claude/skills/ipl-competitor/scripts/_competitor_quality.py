# -*- coding: utf-8 -*-
"""
상위 출원인(경쟁사) 정성분석 — 기술흐름도 + O/S Matrix.
- 기술흐름도: 상위 출원인 patents의 IPC 서브클래스 구성을 연도 구간별로 적층(area)해 기술 진화를 본다.
- O/S Matrix: 해결과제(Object) × 해결수단(Solution) 카테고리로 요약(abstract)을 분류해 집중/공백 셀을 본다.
  카테고리는 <folder>/_ipl/competitor/os_categories.json 로 받는다(없으면 내장 EV 기본값). 분석가가 도메인에 맞게 정의.

Usage: python _competitor_quality.py <folder> [--top 8]
출력: <folder>/_ipl/competitor/{comp_techflow.png, comp_osmatrix.png, comp_quality.json}
"""
import sys, os, json, re
from collections import Counter, defaultdict
from _ipl_io import (ensure_pkgs, korean_font, load_patents, resolve, ipl_dir, parse_year,
                     chart_fig, style_axes, axis_unit, IPL_PALETTE, IPL_DENS_CMAP)

ensure_pkgs(["pandas", "numpy", "matplotlib", "openpyxl", "pillow"])
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import rcParams
rcParams["font.family"] = korean_font()
rcParams["axes.unicode_minus"] = False

PALETTE = IPL_PALETTE   # 보고서 전 장 차트 톤 통일(공유 팔레트)
IPC_RE = re.compile(r"([A-H]\d{2}[A-Z])")

# 내장 EV/배터리 도메인 O/S 기본 카테고리 (영문 초록 기준 키워드)
DEFAULT_CATS = {
    "object": [
        ["충전·충전인프라", ["charging", "charger", "charge station", "recharg", "plug"]],
        ["배터리 셀·에너지", ["energy density", "capacity", "electrode", "lithium", "anode", "cathode", "cell "]],
        ["안전·열관리", ["thermal", "cooling", "safety", "temperature", "overheat", "fire"]],
        ["수명·신뢰성", ["lifespan", "degradation", "durabilit", "aging", "longevity", "reliab", "life of"]],
        ["구동·동력", ["motor", "powertrain", "traction", "propulsion", "torque", "drive system"]],
        ["배터리관리·진단", ["management system", "bms", "state of charge", "soc", "soh", "monitor", "diagnos", "estimat"]],
        ["배터리교환·모듈", ["swap", "exchange", "replaceable", "removable", "battery module", "cartridge", "quick-change"]],
        ["전력망·V2G", ["grid", "v2g", "vehicle-to-grid", "power supply", "energy storage", "discharg"]],
    ],
    "solution": [
        ["구조·기계설계", ["structure", "housing", "frame", "bracket", "mechanical", "arrangement", "assembly", "mounting"]],
        ["소재·화학", ["material", "electrolyte", "coating", "composite", "additive", "membrane", "chemical"]],
        ["제어·알고리즘", ["control", "algorithm", "method for", "estimat", "model", "predict", "schedul", "optimiz"]],
        ["회로·전력전자", ["circuit", "converter", "inverter", "dc-dc", "power electronic", "switching", "rectif"]],
        ["통신·데이터·SW", ["communication", "data", "software", "network", "cloud", "server", "wireless", "protocol"]],
        ["냉각·열설계", ["coolant", "heat exchang", "fluid", "radiator", "cooling channel", "heat dissipat"]],
    ],
}


def norm_applicant(name):
    if name is None or (isinstance(name, float) and np.isnan(name)):
        return None
    s = re.split(r"[;|/]", str(name))[0].strip()
    s = re.sub(r"\s*\([^)]{5,}\)\s*$", "", s).strip()  # KIPRIS 말미 (주소) 제거
    s = re.sub(r"\b(주식회사|㈜|\(주\)|유한회사|inc\.?|corp\.?|co\.?,? ?ltd\.?|ltd\.?|llc|gmbh|s\.?a\.?|co\.?)\b",
               "", s, flags=re.IGNORECASE).strip(" ,.")
    if not s:
        return None
    return s


def canonicalize_app_series(s):
    """대소문자·공백만 다른 동일 출원인 표기를 최빈 표기로 통합(특정 기업 하드코딩 없이 일반화).
    같은 casefold 키의 표기 중 최빈(동률이면 대소문자 혼용 표기)을 대표로 삼는다."""
    key = s.astype(str).str.replace(r"\s+", " ", regex=True).str.strip().str.casefold()
    rep = {}
    for k, grp in s.groupby(key):
        vc = grp.value_counts()
        top = vc.max()
        cands = sorted([n for n, cnt in vc.items() if cnt == top],
                       key=lambda n: (0 if any(ch.islower() for ch in n) else 1, n))
        rep[k] = cands[0]
    return key.map(rep)


def classify(text, cats):
    if not isinstance(text, str) or not text.strip():
        return None, None
    t = text.lower()
    def pick(group):
        for label, kws in group:
            if any(k in t for k in kws):
                return label
        return None
    return pick(cats["object"]), pick(cats["solution"])


def main():
    folder = sys.argv[1]
    top_n = int(sys.argv[sys.argv.index("--top") + 1]) if "--top" in sys.argv else 8
    df = load_patents(folder)
    r = resolve(df)
    out = ipl_dir(folder, "competitor")

    if not r["applicant"]:
        (out / "comp_quality.json").write_text(json.dumps({"error": "출원인 컬럼 없음"}, ensure_ascii=False), encoding="utf-8")
        print("[error] 출원인 컬럼 없음"); return

    df["_app"] = df[r["applicant"]].map(norm_applicant)
    df = df[df["_app"].notna()].copy()
    df["_app"] = canonicalize_app_series(df["_app"])  # 대소문자 변형 표기 통합
    top_names = list(df["_app"].value_counts().head(top_n).index)
    sub = df[df["_app"].isin(top_names)].copy()
    sub["_year"] = parse_year(sub[r["filing_date"]]) if r["filing_date"] else np.nan
    ipc_col = r["ipc_all"] or r["ipc_main"]
    sub["_subs"] = sub[ipc_col].map(lambda v: list(dict.fromkeys(IPC_RE.findall(str(v).upper()))) if pd.notna(v) else []) if ipc_col else [[] for _ in range(len(sub))]

    cats = DEFAULT_CATS
    cf = out / "os_categories.json"
    if cf.exists():
        with open(cf, encoding="utf-8") as _cf:
            cats = json.load(_cf)

    result = {"top_names": top_names, "n_patents": int(len(sub))}

    # ---------- 기술흐름도: 연도 구간 × top IPC 서브클래스 적층 ----------
    yrs = sub["_year"].dropna()
    techflow = {}
    if len(yrs) and ipc_col:
        y0, y1 = int(yrs.min()), int(yrs.max())
        # 3개 구간
        edges = np.linspace(y0, y1 + 1, 4).astype(int)
        periods = [(edges[i], edges[i + 1] - 1) for i in range(3)]
        allsub = Counter(s for subs in sub["_subs"] for s in subs)
        topk = [s for s, _ in allsub.most_common(6)]
        mat = np.zeros((len(topk), len(periods)))
        for pi, (a, b) in enumerate(periods):
            seg = sub[(sub["_year"] >= a) & (sub["_year"] <= b)]
            cnt = Counter(s for subs in seg["_subs"] for s in subs if s in topk)
            for si, s in enumerate(topk):
                mat[si, pi] = cnt.get(s, 0)
        fig, ax = chart_fig(9.5, 5.3)
        xs = [f"{a}~{b}" for a, b in periods]
        bottom = np.zeros(len(periods))
        for si, s in enumerate(topk):
            ax.bar(xs, mat[si], bottom=bottom, label=s, color=PALETTE[si % len(PALETTE)],
                   width=0.55, edgecolor="white", linewidth=0.8)
            bottom += mat[si]
        ax.set_xlabel("출원 구간", fontsize=12, color="#444444")
        axis_unit(ax, "출원 건수", "y")
        ax.legend(title="IPC 서브클래스", fontsize=9, ncol=3, loc="upper left", frameon=False)
        style_axes(ax, grid="y")
        fig.tight_layout(); fig.savefig(out / "comp_techflow.png", dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor()); plt.close(fig)
        techflow = {"periods": xs, "ipc": topk,
                    "matrix": {topk[si]: {xs[pi]: int(mat[si, pi]) for pi in range(len(periods))} for si in range(len(topk))}}
        result["techflow"] = techflow
        print(f"[ok] 기술흐름도 → comp_techflow.png  구간 {xs}  IPC {topk}")

    # ---------- O/S Matrix ----------
    if r["abstract"]:
        O = [o[0] for o in cats["object"]]
        Sx = [s[0] for s in cats["solution"]]
        M = np.zeros((len(O), len(Sx)))
        oi = {o: i for i, o in enumerate(O)}; si = {s: i for i, s in enumerate(Sx)}
        classified = 0
        for _, row in sub.iterrows():
            o, s = classify(row.get(r["abstract"]), cats)
            if o and s:
                M[oi[o], si[s]] += 1; classified += 1
        fig, ax = chart_fig(max(8, len(Sx) * 1.3), max(5.5, len(O) * 0.7))
        im = ax.imshow(M, cmap=IPL_DENS_CMAP, aspect="auto")
        ax.set_xticks(range(len(Sx))); ax.set_xticklabels(Sx, rotation=25, ha="right", fontsize=10)
        ax.set_yticks(range(len(O))); ax.set_yticklabels(O, fontsize=10)
        ax.tick_params(length=0, colors="#333333")
        for sp in ax.spines.values():
            sp.set_visible(False)
        for i in range(len(O)):
            for j in range(len(Sx)):
                if M[i, j] > 0:
                    ax.text(j, i, int(M[i, j]), ha="center", va="center", fontsize=9,
                            fontweight="bold", color="white" if M[i, j] > M.max() * 0.55 else "#333333")
        ax.set_xlabel("해결수단 (Solution)", fontsize=12, color="#444444")
        ax.set_ylabel("해결과제 (Object)", fontsize=12, color="#444444")
        fig.colorbar(im, ax=ax, shrink=0.8, label="특허 건수")
        fig.tight_layout(); fig.savefig(out / "comp_osmatrix.png", dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor()); plt.close(fig)
        # 상위/공백 셀
        flat = [(O[i], Sx[j], int(M[i, j])) for i in range(len(O)) for j in range(len(Sx))]
        hot = sorted(flat, key=lambda x: -x[2])[:5]
        empty = [(o, s) for o, s, c in flat if c == 0][:6]
        result["osmatrix"] = {"objects": O, "solutions": Sx, "classified": int(classified),
                              "hot_cells": [{"object": o, "solution": s, "count": c} for o, s, c in hot],
                              "empty_cells": [{"object": o, "solution": s} for o, s in empty]}
        print(f"[ok] O/S Matrix → comp_osmatrix.png  분류 {classified}/{len(sub)}건")
        print(f"     집중 셀: {[(h[0],h[1],h[2]) for h in hot[:3]]}")

    (out / "comp_quality.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
