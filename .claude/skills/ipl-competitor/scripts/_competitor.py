# -*- coding: utf-8 -*-
"""
경쟁사(상위 출원인) 정량 집계 + 차트 3종 + 프로파일 골격 JSON.
Usage: python _competitor.py <folder> [--top N]
출력: <folder>/_ipl/competitor/{comp_share.png, comp_trend.png, comp_ipc.png, competitor.json, _stats.json}
competitor.json 은 골격(통계만). profile/momentum/positioning 해석은 Claude(에이전트)가 채운다.
"""
import sys, os, json, re
from collections import Counter, defaultdict
from _ipl_io import (ensure_pkgs, korean_font, load_patents, resolve, ipl_dir, parse_year, clean_id,
                     fmt_patent_no, chart_fig, style_axes, axis_unit, mark_incomplete_year,
                     IPL_PALETTE, IPL_SEQ_CMAP)

ensure_pkgs(["pandas", "numpy", "matplotlib", "openpyxl", "pillow"])
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import rcParams
rcParams["font.family"] = korean_font()
rcParams["axes.unicode_minus"] = False

ACCENT = IPL_PALETTE[0]
PALETTE = IPL_PALETTE   # 보고서 전 장 차트 톤 통일(공유 팔레트)


def norm_applicant(name):
    if name is None or (isinstance(name, float) and np.isnan(name)):
        return None
    s = str(name).strip()
    if not s or s.lower() == "nan":
        return None
    # 다수 출원인은 첫 번째만
    s = re.split(r"[;|/]", s)[0].strip()
    # KIPRIS: 이름 뒤 (주소) 괄호 제거 — 말미 괄호가 길거나(주소 추정) 주소 표지를 포함하면 제거
    s = re.sub(r"\s*\([^)]{5,}\)\s*$", "", s).strip()
    # 법인 접미 제거 → 표기 변형 통합
    s = re.sub(r"\b(주식회사|㈜|\(주\)|유한회사|inc\.?|corp\.?|co\.?,? ?ltd\.?|ltd\.?|llc|gmbh|s\.?a\.?|co\.?)\b",
               "", s, flags=re.IGNORECASE).strip(" ,.")
    if not s:
        return None
    return s


def canonicalize_app_series(s):
    """대소문자·공백만 다른 동일 출원인 표기를 최빈 표기로 통합(특정 기업 하드코딩 없이 일반화).
    같은 casefold 키를 공유하는 표기 중 가장 자주 등장한 것을, 동률이면 고유 대소문자(브랜드
    원표기로 추정)를 우선해 대표 표기로 삼는다. 예: 'iRobot Corporation'과 'IROBOT CORPORATION'을
    빈도 높은 쪽(또는 대소문자 혼용 표기)으로 자동 통합."""
    key = s.astype(str).str.replace(r"\s+", " ", regex=True).str.strip().str.casefold()
    rep = {}
    for k, grp in s.groupby(key):
        vc = grp.value_counts()
        top = vc.max()
        cands = sorted([n for n, cnt in vc.items() if cnt == top],
                       key=lambda n: (0 if any(ch.islower() for ch in n) else 1, n))
        rep[k] = cands[0]
    return key.map(rep)


def ipc_section(code):
    if code is None:
        return None
    m = re.match(r"\s*([A-H])", str(code))
    return m.group(1) if m else None


def main():
    folder = sys.argv[1]
    top_n = 8
    if "--top" in sys.argv:
        top_n = int(sys.argv[sys.argv.index("--top") + 1])

    df = load_patents(folder)
    r = resolve(df)
    out = ipl_dir(folder, "competitor")

    if not r["applicant"]:
        (out / "competitor.json").write_text(json.dumps(
            {"error": "출원인 컬럼 없음", "companies": []}, ensure_ascii=False, indent=2), encoding="utf-8")
        print("[error] 출원인 컬럼을 찾지 못했습니다.")
        return

    df["_app"] = df[r["applicant"]].map(norm_applicant)
    df = df[df["_app"].notna()].copy()
    df["_app"] = canonicalize_app_series(df["_app"])  # 대소문자 변형 표기 통합
    total = len(df)
    df["_year"] = parse_year(df[r["filing_date"]]) if r["filing_date"] else None
    df["_sec"] = df[r["ipc_main"] or r["ipc_all"]].map(ipc_section) if (r["ipc_main"] or r["ipc_all"]) else None

    counts = df["_app"].value_counts()
    top = counts.head(top_n)
    top_names = list(top.index)
    if not top_names:
        (out / "competitor.json").write_text(json.dumps(
            {"error": "유효 출원인 없음", "companies": []}, ensure_ascii=False, indent=2), encoding="utf-8")
        print("[error] 유효 출원인이 없습니다.")
        return

    # ---- chart 1: 점유율 (가로 막대) ----
    fig, ax = chart_fig(9, 5.2)
    vals = top.values[::-1]
    names = top_names[::-1]
    bars = ax.barh(names, vals, color=[PALETTE[i % len(PALETTE)] for i in range(len(names))],
                   height=0.7, edgecolor="white", linewidth=0.6)
    mx = max(vals) if len(vals) else 1
    for b, v in zip(bars, vals):
        ax.text(v + mx * 0.01, b.get_y() + b.get_height() / 2,
                f"{int(v):,} ({v/total*100:.1f}%)", va="center", fontsize=11, color="#333333")
    axis_unit(ax, "출원 건수", "x")
    ax.margins(x=0.14)
    style_axes(ax, grid="x")
    fig.tight_layout()
    fig.savefig(out / "comp_share.png", dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)

    # ---- chart 2: 상위사 연도별 추이 ----
    trend = {}
    if df["_year"].notna().any():
        yrs = sorted(int(y) for y in df["_year"].dropna().unique())
        fig, ax = chart_fig(9.5, 5.2)
        for i, name in enumerate(top_names[:6]):
            sub = df[(df["_app"] == name) & df["_year"].notna()]
            ser = sub["_year"].value_counts().reindex(yrs, fill_value=0).sort_index()
            col = PALETTE[i % len(PALETTE)]
            lbl = name if len(str(name)) <= 22 else str(name)[:20] + ".."
            ax.fill_between(yrs, ser.values, alpha=0.07, color=col, zorder=1)
            ax.plot(yrs, ser.values, marker="o", ms=5, lw=2.4, color=col, label=lbl, zorder=2)
            trend[name] = {int(y): int(v) for y, v in zip(yrs, ser.values)}
        ax.set_xlabel("출원연도", fontsize=12, color="#444444")
        axis_unit(ax, "건수", "y")
        ax.legend(fontsize=9, ncol=2, frameon=False)
        style_axes(ax, grid="y")
        mark_incomplete_year(ax, yrs)
        fig.tight_layout()
        fig.savefig(out / "comp_trend.png", dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
        plt.close(fig)

    # ---- chart 3: 상위사 × IPC 섹션 히트맵 ----
    focus = {}
    if df["_sec"].notna().any():
        secs = [s for s in list("ABCDEFGH") if (df["_sec"] == s).any()]
        mat = np.zeros((len(top_names), len(secs)))
        for i, name in enumerate(top_names):
            sub = df[df["_app"] == name]
            sc = sub["_sec"].value_counts()
            for j, s in enumerate(secs):
                mat[i, j] = sc.get(s, 0)
            row = sub["_sec"].value_counts()
            focus[name] = [str(x) for x in list(row.head(3).index)]
        fig, ax = chart_fig(max(7, len(secs) * 0.9), 5.2)
        im = ax.imshow(mat, cmap=IPL_SEQ_CMAP, aspect="auto")
        ax.set_xticks(range(len(secs))); ax.set_xticklabels(secs, fontsize=12)
        ax.set_yticks(range(len(top_names))); ax.set_yticklabels(top_names, fontsize=11)
        ax.tick_params(length=0, colors="#333333")
        for sp in ax.spines.values():
            sp.set_visible(False)
        for i in range(len(top_names)):
            for j in range(len(secs)):
                if mat[i, j] > 0:
                    ax.text(j, i, int(mat[i, j]), ha="center", va="center", fontsize=10,
                            fontweight="bold", color="white" if mat[i, j] > mat.max() * 0.5 else "#333333")
        fig.colorbar(im, ax=ax, shrink=0.8, label="건수")
        fig.tight_layout()
        fig.savefig(out / "comp_ipc.png", dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
        plt.close(fig)

    # ---- 대표 특허 선정 (피인용→패밀리 우선, 구조화 레코드) ----
    def _num(col, row):
        v = pd.to_numeric(pd.Series([row.get(r[col])]), errors="coerce").iloc[0] if r.get(col) else None
        return None if v is None or pd.isna(v) else int(v)

    def rep_patents(name, k=2):
        sub = df[df["_app"] == name].copy()
        cit = pd.to_numeric(sub[r["citations"]], errors="coerce") if r.get("citations") else None
        fam = pd.to_numeric(sub[r["family"]], errors="coerce") if r.get("family") else None
        if cit is not None and cit.notna().any():
            sub = sub.assign(_s=cit.fillna(0)).sort_values("_s", ascending=False)
        elif fam is not None and fam.notna().any():
            sub = sub.assign(_s=fam.fillna(0)).sort_values("_s", ascending=False)
        reps = []
        for _, row in sub.head(k).iterrows():
            reps.append({
                "number": fmt_patent_no(row[r["number"]]) if r.get("number") else "?",
                "title": str(row[r["title"]])[:90] if r.get("title") else "",
                "year": int(row["_year"]) if pd.notna(row.get("_year")) else None,
                "citations": _num("citations", row), "family": _num("family", row),
                "ipc": str(row[r["ipc_main"] or r["ipc_all"]])[:40] if (r.get("ipc_main") or r.get("ipc_all")) else "",
                "abstract": str(row[r["abstract"]])[:600] if r.get("abstract") and pd.notna(row.get(r["abstract"])) else "",
            })
        return reps

    # ---- competitor.json 골격 ----
    companies = []
    for rank, name in enumerate(top_names, 1):
        cnt = int(top[name])
        # 모멘텀: 최근 절반 vs 이전 절반
        momentum = "n/a"
        if name in trend and trend[name]:
            ys = sorted(trend[name])
            if len(ys) >= 2:
                half = len(ys) // 2
                early = sum(trend[name][y] for y in ys[:half])
                late = sum(trend[name][y] for y in ys[half:])
                momentum = "상승" if late > early else ("하락" if late < early else "유지")
        companies.append({
            "rank": rank, "name": name, "count": cnt, "share": round(cnt / total, 4),
            "focus_ipc": focus.get(name, []), "momentum": momentum,
            "positioning": "",  # Claude가 채움
            "profile": [],      # Claude가 채움
            "rep_patents": rep_patents(name),
        })

    result = {
        "total": total, "top_n": top_n, "companies": companies,
        "others_count": int(total - top.sum()),
        "charts": {
            "share": str(out / "comp_share.png"),
            "trend": str(out / "comp_trend.png") if trend else None,
            "ipc": str(out / "comp_ipc.png") if focus else None,
        },
    }
    (out / "competitor.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "_stats.json").write_text(json.dumps(
        {"trend": trend, "focus": focus}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ok] 상위 {top_n}개사 집계 완료 → {out}")
    print(f"     1위 {top_names[0]} ({int(top.iloc[0])}건, {top.iloc[0]/total*100:.1f}%)")


if __name__ == "__main__":
    main()
