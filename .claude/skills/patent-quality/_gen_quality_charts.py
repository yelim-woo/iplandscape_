# -*- coding: utf-8 -*-
"""
Stage A2: Classify patents by keyword matching + render 3 qualitative charts.
Reads categories.json (defined by Claude) and extracted_texts.json (from Stage A).

Usage: python _gen_quality_charts.py <input_dir>
"""
import sys, os, json, re
from pathlib import Path
from collections import defaultdict
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import matplotlib.ticker as mticker
from matplotlib import rcParams
from matplotlib.colors import LinearSegmentedColormap
import platform

def _detect_korean_font():
    system = platform.system()
    if system == "Windows":
        return "Malgun Gothic"
    elif system == "Darwin":
        return "AppleGothic"
    else:
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

# ---- Color palette ----
THEME_COLORS = [
    "#4A90D9", "#E07070", "#5DC49E", "#F5B84C", "#9B7BD4",
    "#E8917A", "#6BC5D2", "#B8D458", "#D4A0C0", "#8B9DC3",
]
HEATMAP_CMAP = LinearSegmentedColormap.from_list(
    "custom_blues", ["#FFFFFF", "#D6E8F7", "#7CB5D9", "#2E6DA4", "#1A3A5C"]
)
PERIOD_CMAPS = [
    LinearSegmentedColormap.from_list("p1", ["#FFFFFF", "#B3CDE3", "#4A90D9"]),
    LinearSegmentedColormap.from_list("p2", ["#FFFFFF", "#FADBD8", "#E07070"]),
    LinearSegmentedColormap.from_list("p3", ["#FFFFFF", "#D5F5E3", "#27AE60"]),
    LinearSegmentedColormap.from_list("p4", ["#FFFFFF", "#FEF9E7", "#F5B84C"]),
]

FIG_W, FIG_H, DPI = 16, 9, 110

def log(msg):
    print(f"[charts] {msg}", flush=True)


# ---- Keyword matching ----
def build_keyword_pattern(keywords):
    """Build compiled regex pattern from keyword list."""
    escaped = [re.escape(k.lower()) for k in keywords if k.strip()]
    if not escaped:
        return None
    return re.compile("|".join(escaped), re.IGNORECASE)

def classify_text(text, categories):
    """Classify a text into categories by keyword matching.
    Returns list of matched category IDs.
    """
    if not text:
        return []
    text_lower = text.lower()
    matched = []
    for cat in categories:
        pattern = cat.get("_pattern")
        if pattern and pattern.search(text_lower):
            matched.append(cat["id"])
    return matched


# ---- Chart 1: Technology Flow (Stacked Area) ----
def render_tech_flow(records, categories, year_info, output_path):
    """Stacked area chart of technology themes over years."""
    themes = categories.get("tech_themes", [])
    if not themes:
        log("  WARN: no tech_themes defined, skipping chart 1")
        return None

    # Compile patterns
    for t in themes:
        t["_pattern"] = build_keyword_pattern(t.get("keywords", []))

    # Classify each record
    year_theme = defaultdict(lambda: defaultdict(int))
    for rec in records:
        if not rec.get("summary"):
            continue
        text = rec["title"] + " " + rec["summary"]
        matched = classify_text(text, themes)
        if not matched:
            matched = ["기타"]
        for tid in matched:
            year_theme[rec["year"]][tid] += 1

    # Build matrix
    years = sorted(year_theme.keys())
    theme_ids = [t["id"] for t in themes]
    theme_names = {t["id"]: t["name"] for t in themes}

    # Add "기타" if present
    has_etc = any("기타" in year_theme[y] for y in years)
    if has_etc:
        theme_ids.append("기타")
        theme_names["기타"] = "기타"

    data = np.zeros((len(theme_ids), len(years)))
    for j, y in enumerate(years):
        for i, tid in enumerate(theme_ids):
            data[i][j] = year_theme[y].get(tid, 0)

    # Render
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))

    colors = THEME_COLORS[:len(theme_ids)]
    if len(theme_ids) > len(THEME_COLORS):
        colors += ["#CCCCCC"] * (len(theme_ids) - len(THEME_COLORS))

    ax.stackplot(years, data, labels=[theme_names.get(tid, tid) for tid in theme_ids],
                 colors=colors, alpha=0.85, edgecolor="white", linewidth=0.5)

    ax.set_xlabel("출원연도", fontsize=13, fontweight="bold")
    ax.set_ylabel("특허 건수", fontsize=13, fontweight="bold")
    ax.set_title("연도별 기술흐름도", fontsize=18, fontweight="bold", pad=20)
    ax.legend(loc="upper left", fontsize=10, framealpha=0.9, ncol=min(4, len(theme_ids)))
    ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    ax.grid(axis="y", alpha=0.3)
    ax.set_xlim(years[0], years[-1])

    plt.tight_layout()
    fig.savefig(output_path, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    log(f"  chart_q1.png saved")

    # Stats
    stats = {
        "chart_id": "q1",
        "title": "연도별 기술흐름도",
        "year_range": f"{years[0]}~{years[-1]}",
        "themes": [],
    }
    for tid in theme_ids:
        total = sum(year_theme[y].get(tid, 0) for y in years)
        peak_year = max(years, key=lambda y: year_theme[y].get(tid, 0))
        peak_val = year_theme[peak_year].get(tid, 0)
        # Growth trend: compare first half vs second half
        mid = len(years) // 2
        first_half = sum(year_theme[y].get(tid, 0) for y in years[:mid])
        second_half = sum(year_theme[y].get(tid, 0) for y in years[mid:])
        trend = "증가" if second_half > first_half * 1.2 else ("감소" if second_half < first_half * 0.8 else "유지")
        stats["themes"].append({
            "id": tid,
            "name": theme_names.get(tid, tid),
            "total": int(total),
            "peak_year": int(peak_year),
            "peak_count": int(peak_val),
            "trend": trend,
        })
    return stats


# ---- Chart 2: O/S Matrix Overall (Heatmap) ----
def render_os_matrix(records, categories, output_path):
    """Heatmap of Object × Solution categories."""
    obj_cats = categories.get("object_categories", [])
    sol_cats = categories.get("solution_categories", [])
    if not obj_cats or not sol_cats:
        log("  WARN: O/S categories not defined, skipping chart 2")
        return None

    for c in obj_cats:
        c["_pattern"] = build_keyword_pattern(c.get("keywords", []))
    for c in sol_cats:
        c["_pattern"] = build_keyword_pattern(c.get("keywords", []))

    # Classify
    matrix = defaultdict(lambda: defaultdict(int))
    total_classified = 0
    for rec in records:
        if not rec.get("problem") or not rec.get("solution"):
            continue
        o_matched = classify_text(rec["problem"], obj_cats)
        s_matched = classify_text(rec["solution"], sol_cats)
        if not o_matched:
            o_matched = ["O_etc"]
        if not s_matched:
            s_matched = ["S_etc"]
        for oid in o_matched:
            for sid in s_matched:
                matrix[oid][sid] += 1
        total_classified += 1

    obj_ids = [c["id"] for c in obj_cats]
    sol_ids = [c["id"] for c in sol_cats]
    obj_names = {c["id"]: c["name"] for c in obj_cats}
    sol_names = {c["id"]: c["name"] for c in sol_cats}

    # Add "기타" rows/cols if they have data
    if any("O_etc" in matrix for _ in [1]):
        if matrix.get("O_etc"):
            obj_ids.append("O_etc")
            obj_names["O_etc"] = "기타"
    if any("S_etc" in matrix[o] for o in matrix):
        sol_ids.append("S_etc")
        sol_names["S_etc"] = "기타"

    # Build numpy matrix
    data = np.zeros((len(obj_ids), len(sol_ids)))
    for i, oid in enumerate(obj_ids):
        for j, sid in enumerate(sol_ids):
            data[i][j] = matrix[oid].get(sid, 0)

    # Render
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))

    vmax = data.max() if data.max() > 0 else 1
    im = ax.imshow(data, cmap=HEATMAP_CMAP, aspect="auto", vmin=0, vmax=vmax)

    # Annotations
    for i in range(len(obj_ids)):
        for j in range(len(sol_ids)):
            val = int(data[i][j])
            if val > 0:
                color = "white" if val > vmax * 0.6 else "black"
                ax.text(j, i, str(val), ha="center", va="center",
                        fontsize=12, fontweight="bold", color=color)

    ax.set_xticks(range(len(sol_ids)))
    ax.set_xticklabels([sol_names.get(s, s) for s in sol_ids], rotation=30, ha="right", fontsize=11)
    ax.set_yticks(range(len(obj_ids)))
    ax.set_yticklabels([obj_names.get(o, o) for o in obj_ids], fontsize=11)
    ax.set_xlabel("Solution (해결수단)", fontsize=13, fontweight="bold")
    ax.set_ylabel("Object (해결과제)", fontsize=13, fontweight="bold")
    ax.set_title("O/S Matrix 전체 현황", fontsize=18, fontweight="bold", pad=20)

    cbar = fig.colorbar(im, ax=ax, shrink=0.8, pad=0.02)
    cbar.set_label("특허 건수", fontsize=11)

    plt.tight_layout()
    fig.savefig(output_path, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    log(f"  chart_q2.png saved")

    # Stats
    stats = {
        "chart_id": "q2",
        "title": "O/S Matrix 전체 현황",
        "total_classified": total_classified,
        "object_categories": [obj_names.get(o, o) for o in obj_ids],
        "solution_categories": [sol_names.get(s, s) for s in sol_ids],
        "top_cells": [],
        "blank_cells": [],
    }
    # Top cells
    cells = []
    for i, oid in enumerate(obj_ids):
        for j, sid in enumerate(sol_ids):
            cells.append((obj_names.get(oid, oid), sol_names.get(sid, sid), int(data[i][j])))
    cells.sort(key=lambda x: x[2], reverse=True)
    stats["top_cells"] = [{"object": c[0], "solution": c[1], "count": c[2]} for c in cells[:5]]
    stats["blank_cells"] = [{"object": c[0], "solution": c[1]} for c in cells if c[2] == 0]

    return stats


# ---- Chart 3: O/S Matrix by Period (2x2 subplot) ----
def render_os_period(records, categories, year_info, output_path):
    """2×2 heatmap subplots showing O/S matrix per period with growth indicators."""
    obj_cats = categories.get("object_categories", [])
    sol_cats = categories.get("solution_categories", [])
    periods = year_info.get("periods", [])

    if not obj_cats or not sol_cats or not periods:
        log("  WARN: insufficient data for period chart, skipping chart 3")
        return None

    for c in obj_cats:
        c["_pattern"] = build_keyword_pattern(c.get("keywords", []))
    for c in sol_cats:
        c["_pattern"] = build_keyword_pattern(c.get("keywords", []))

    obj_ids = [c["id"] for c in obj_cats]
    sol_ids = [c["id"] for c in sol_cats]
    obj_names = {c["id"]: c["name"] for c in obj_cats}
    sol_names = {c["id"]: c["name"] for c in sol_cats}

    # Classify per period
    period_matrices = {}
    for p in periods:
        period_matrices[p["period"]] = defaultdict(lambda: defaultdict(int))

    for rec in records:
        if not rec.get("problem") or not rec.get("solution") or rec.get("period") is None:
            continue
        o_matched = classify_text(rec["problem"], obj_cats)
        s_matched = classify_text(rec["solution"], sol_cats)
        if not o_matched or not s_matched:
            continue
        for oid in o_matched:
            if oid not in obj_ids:
                continue
            for sid in s_matched:
                if sid not in sol_ids:
                    continue
                period_matrices[rec["period"]][oid][sid] += 1

    # Build numpy arrays per period
    n_periods = len(periods)
    # Ensure we have exactly 4 subplots (pad if fewer periods)
    subplot_count = min(4, n_periods)
    nrows = 2 if subplot_count > 2 else 1
    ncols = 2

    period_data = {}
    global_max = 0
    for p in periods[:4]:
        mat = np.zeros((len(obj_ids), len(sol_ids)))
        for i, oid in enumerate(obj_ids):
            for j, sid in enumerate(sol_ids):
                mat[i][j] = period_matrices[p["period"]][oid].get(sid, 0)
        period_data[p["period"]] = mat
        if mat.max() > global_max:
            global_max = mat.max()

    if global_max == 0:
        global_max = 1

    # Render
    fig, axes = plt.subplots(nrows, ncols, figsize=(FIG_W, FIG_H))
    if nrows == 1:
        axes = np.array([axes]) if ncols > 1 else np.array([[axes]])
    axes_flat = axes.flatten()

    for idx, p in enumerate(periods[:4]):
        if idx >= len(axes_flat):
            break
        ax = axes_flat[idx]
        mat = period_data[p["period"]]
        im = ax.imshow(mat, cmap=PERIOD_CMAPS[idx % len(PERIOD_CMAPS)],
                       aspect="auto", vmin=0, vmax=global_max)

        # Annotations with growth indicators
        for i in range(len(obj_ids)):
            for j in range(len(sol_ids)):
                val = int(mat[i][j])
                if val > 0:
                    color = "white" if val > global_max * 0.6 else "black"
                    # Growth indicator: compare with previous period
                    indicator = ""
                    if idx > 0:
                        prev_p = periods[idx - 1]
                        prev_val = period_data[prev_p["period"]][i][j]
                        if prev_val == 0 and val > 0:
                            indicator = " ★"  # new appearance
                        elif prev_val > 0 and val >= prev_val * 2:
                            indicator = " ▲"  # rapid growth
                        elif prev_val > 0 and val > prev_val:
                            indicator = " △"  # growth
                    ax.text(j, i, f"{val}{indicator}", ha="center", va="center",
                            fontsize=9, fontweight="bold", color=color)

        ax.set_xticks(range(len(sol_ids)))
        ax.set_xticklabels([sol_names.get(s, s)[:6] for s in sol_ids],
                           rotation=30, ha="right", fontsize=8)
        ax.set_yticks(range(len(obj_ids)))
        ax.set_yticklabels([obj_names.get(o, o)[:8] for o in obj_ids], fontsize=8)
        ax.set_title(p["label"], fontsize=12, fontweight="bold", pad=8)

    # Hide unused subplots
    for idx in range(len(periods[:4]), len(axes_flat)):
        axes_flat[idx].set_visible(False)

    fig.suptitle("O/S Matrix 구간별 변화", fontsize=18, fontweight="bold", y=1.02)

    # Legend for indicators
    legend_text = "★ 신규 출현  ▲ 급상승(2배↑)  △ 성장"
    fig.text(0.5, -0.02, legend_text, ha="center", fontsize=11,
             style="italic", color="#555555")

    plt.tight_layout()
    fig.savefig(output_path, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    log(f"  chart_q3.png saved")

    # Stats
    stats = {
        "chart_id": "q3",
        "title": "O/S Matrix 구간별 변화",
        "periods": [p["label"] for p in periods[:4]],
        "growth_cells": [],
        "new_cells": [],
        "blank_cells": [],
    }

    # Analyze changes across periods
    for i, oid in enumerate(obj_ids):
        for j, sid in enumerate(sol_ids):
            vals = [int(period_data[p["period"]][i][j]) for p in periods[:4]]
            o_name = obj_names.get(oid, oid)
            s_name = sol_names.get(sid, sid)

            # All-zero = blank
            if all(v == 0 for v in vals):
                stats["blank_cells"].append({"object": o_name, "solution": s_name})
            # Rapid growth
            elif len(vals) >= 2:
                for k in range(1, len(vals)):
                    if vals[k-1] > 0 and vals[k] >= vals[k-1] * 2:
                        stats["growth_cells"].append({
                            "object": o_name, "solution": s_name,
                            "from_period": periods[k-1]["label"],
                            "to_period": periods[k]["label"],
                            "from_val": vals[k-1], "to_val": vals[k],
                            "type": "급상승",
                        })
                    elif vals[k-1] == 0 and vals[k] > 0:
                        stats["new_cells"].append({
                            "object": o_name, "solution": s_name,
                            "period": periods[k]["label"],
                            "count": vals[k],
                            "type": "신규",
                        })

    return stats


# ---- Dashboard Data Builder ----
def build_dashboard_data(records, categories, year_info):
    """Build structured JSON for interactive dashboard (Sankey + O/S Matrix)."""
    themes = categories.get("tech_themes", [])
    obj_cats = categories.get("object_categories", [])
    sol_cats = categories.get("solution_categories", [])
    periods = year_info.get("periods", [])[:4]

    # Compile patterns
    for t in themes:
        t["_pattern"] = build_keyword_pattern(t.get("keywords", []))
    for c in obj_cats:
        c["_pattern"] = build_keyword_pattern(c.get("keywords", []))
    for c in sol_cats:
        c["_pattern"] = build_keyword_pattern(c.get("keywords", []))

    theme_names = {t["id"]: t["name"] for t in themes}
    obj_names = {c["id"]: c["name"] for c in obj_cats}
    sol_names = {c["id"]: c["name"] for c in sol_cats}
    theme_ids = [t["id"] for t in themes]
    obj_ids = [c["id"] for c in obj_cats]
    sol_ids = [c["id"] for c in sol_cats]

    # --- Sankey data: year-by-year theme counts ---
    year_theme = defaultdict(lambda: defaultdict(int))
    for rec in records:
        if not rec.get("summary"):
            continue
        text = (rec.get("title", "") + " " + rec["summary"])
        matched = classify_text(text, themes)
        if not matched:
            continue
        for tid in matched:
            if tid in theme_ids:
                year_theme[rec["year"]][tid] += 1

    all_years = sorted(year_theme.keys())
    yearly_data = {}
    for tid in theme_ids:
        yearly_data[tid] = [year_theme[y].get(tid, 0) for y in all_years]

    # --- O/S Matrix data: obj × sol × period ---
    os_matrix = {}
    for rec in records:
        if not rec.get("problem") or not rec.get("solution") or rec.get("period") is None:
            continue
        o_matched = classify_text(rec["problem"], obj_cats)
        s_matched = classify_text(rec["solution"], sol_cats)
        if not o_matched or not s_matched:
            continue
        for oid in o_matched:
            if oid not in obj_ids:
                continue
            for sid in s_matched:
                if sid not in sol_ids:
                    continue
                key = f"{oid}_{sid}"
                if key not in os_matrix:
                    os_matrix[key] = {p["period"]: 0 for p in periods}
                os_matrix[key][rec["period"]] = os_matrix[key].get(rec["period"], 0) + 1

    # Build raw cells first (no tags yet)
    raw_cells = []
    period_spans = [max(1, p["end"] - p["start"] + 1) for p in periods]

    for oid in obj_ids:
        for sid in sol_ids:
            key = f"{oid}_{sid}"
            period_vals = [os_matrix.get(key, {}).get(p["period"], 0) for p in periods]
            total = sum(period_vals)
            # Growth rate: latest non-zero annual avg / first non-zero annual avg
            annuals = [period_vals[i] / period_spans[i] for i in range(len(period_vals))]
            first_nz = next((a for a in annuals if a > 0), 0)
            latest_nz = next((a for a in reversed(annuals) if a > 0), 0)
            growth_ratio = (latest_nz / first_nz) if first_nz > 0 else 0
            # Early presence: sum of period 1+2
            early_sum = sum(period_vals[:2])

            raw_cells.append({
                "objectId": oid,
                "objectName": obj_names.get(oid, oid),
                "solutionId": sid,
                "solutionName": sol_names.get(sid, sid),
                "periods": period_vals,
                "total": total,
                "growth_ratio": growth_ratio,
                "early_sum": early_sum,
                "annuals": annuals,
            })

    # --- Relative tagging using percentiles ---
    # Filter out all-zero cells first
    nonzero_cells = [c for c in raw_cells if c["total"] > 0]
    zero_cells = [c for c in raw_cells if c["total"] == 0]

    if nonzero_cells:
        # Sort by growth_ratio and total for percentile thresholds
        growth_ratios = sorted([c["growth_ratio"] for c in nonzero_cells])
        totals_sorted = sorted([c["total"] for c in nonzero_cells])
        early_sums = sorted([c["early_sum"] for c in nonzero_cells])

        def percentile(sorted_list, pct):
            idx = int(len(sorted_list) * pct / 100)
            return sorted_list[min(idx, len(sorted_list) - 1)]

        # Thresholds
        growth_threshold = percentile(growth_ratios, 75)   # top 25% = growth
        blank_threshold = percentile(totals_sorted, 25)    # bottom 25% = blank
        # New: early_sum in bottom 10% AND growth_ratio in top 50%
        early_threshold = percentile(early_sums, 10) if early_sums else 0
        growth_median = percentile(growth_ratios, 50)

        log(f"  relative thresholds: growth_ratio>={growth_threshold:.2f} (top25%), "
            f"total<={blank_threshold} (bot25%), early_sum<={early_threshold} (bot10%)")

    cells = []
    for c in raw_cells:
        tags = []
        if c["total"] == 0:
            tags.append("meaningless")
        elif not nonzero_cells:
            pass
        else:
            # 신규: early presence in bottom 10% AND recent growth above median
            is_new = (c["early_sum"] <= early_threshold and
                      c["growth_ratio"] >= growth_median and
                      c["total"] > blank_threshold)
            # 성장: growth_ratio in top 25%
            is_growth = c["growth_ratio"] >= growth_threshold
            # 공백: total in bottom 25%
            is_blank = c["total"] <= blank_threshold

            # Priority: 신규 > 성장 > 공백
            if is_new and not is_growth:
                tags.append("new")
            elif is_growth:
                tags.append("growth")
            elif is_blank:
                tags.append("blank")

        cells.append({
            "objectId": c["objectId"],
            "objectName": c["objectName"],
            "solutionId": c["solutionId"],
            "solutionName": c["solutionName"],
            "periods": c["periods"],
            "total": c["total"],
            "tags": tags,
        })

    return {
        "sankey": {
            "years": all_years,
            "themes": [{"id": t, "name": theme_names.get(t, t)} for t in theme_ids],
            "data": yearly_data,
            "periods": [{"period": p["period"], "label": p["label"]} for p in periods],
        },
        "osMatrix": {
            "objects": [{"id": o, "name": obj_names.get(o, o)} for o in obj_ids],
            "solutions": [{"id": s, "name": sol_names.get(s, s)} for s in sol_ids],
            "periods": [{"period": p["period"], "label": p["label"]} for p in periods],
            "cells": cells,
        },
        "detailOsMatrix": build_detail_os(records, categories, periods, period_spans, log),
    }


# ---- Chart 4: Detail O/S Matrix Overall (Heatmap) ----
def render_detail_os_matrix(records, categories, output_path):
    """Heatmap of detailed Object × Solution categories."""
    d_obj = categories.get("detail_object_categories", [])
    d_sol = categories.get("detail_solution_categories", [])
    if not d_obj or not d_sol:
        log("  WARN: detail O/S categories not defined, skipping chart 4")
        return None

    for c in d_obj:
        c["_pattern"] = build_keyword_pattern(c.get("keywords", []))
    for c in d_sol:
        c["_pattern"] = build_keyword_pattern(c.get("keywords", []))

    # Classify
    matrix = defaultdict(lambda: defaultdict(int))
    total_classified = 0
    for rec in records:
        if not rec.get("problem") or not rec.get("solution"):
            continue
        o_matched = classify_text(rec["problem"], d_obj)
        s_matched = classify_text(rec["solution"], d_sol)
        if not o_matched or not s_matched:
            continue
        for oid in o_matched:
            for sid in s_matched:
                matrix[oid][sid] += 1
        total_classified += 1

    obj_ids = [c["id"] for c in d_obj]
    sol_ids = [c["id"] for c in d_sol]
    obj_names = {c["id"]: c["name"] for c in d_obj}
    sol_names = {c["id"]: c["name"] for c in d_sol}

    data = np.zeros((len(obj_ids), len(sol_ids)))
    for i, oid in enumerate(obj_ids):
        for j, sid in enumerate(sol_ids):
            data[i][j] = matrix[oid].get(sid, 0)

    # Render — larger figure for 10-14 categories
    fig_h = max(FIG_H, 9 + len(obj_ids) * 0.3)
    fig, ax = plt.subplots(figsize=(FIG_W, fig_h))

    vmax = data.max() if data.max() > 0 else 1
    im = ax.imshow(data, cmap=HEATMAP_CMAP, aspect="auto", vmin=0, vmax=vmax)

    for i in range(len(obj_ids)):
        for j in range(len(sol_ids)):
            val = int(data[i][j])
            if val > 0:
                color = "white" if val > vmax * 0.6 else "black"
                fontsize = 10 if len(sol_ids) <= 10 else 8
                ax.text(j, i, str(val), ha="center", va="center",
                        fontsize=fontsize, fontweight="bold", color=color)

    ax.set_xticks(range(len(sol_ids)))
    ax.set_xticklabels([sol_names.get(s, s) for s in sol_ids], rotation=40, ha="right", fontsize=9)
    ax.set_yticks(range(len(obj_ids)))
    ax.set_yticklabels([obj_names.get(o, o) for o in obj_ids], fontsize=9)
    ax.set_xlabel("Solution (해결수단) — 세부", fontsize=13, fontweight="bold")
    ax.set_ylabel("Object (해결과제) — 세부", fontsize=13, fontweight="bold")
    ax.set_title("O/S Matrix 세부 전체 현황", fontsize=18, fontweight="bold", pad=20)

    cbar = fig.colorbar(im, ax=ax, shrink=0.8, pad=0.02)
    cbar.set_label("특허 건수", fontsize=11)

    plt.tight_layout()
    fig.savefig(output_path, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    log(f"  chart_q4.png saved")

    # Stats
    stats = {
        "chart_id": "q4",
        "title": "O/S Matrix 세부 전체 현황",
        "total_classified": total_classified,
        "object_categories": [obj_names.get(o, o) for o in obj_ids],
        "solution_categories": [sol_names.get(s, s) for s in sol_ids],
        "top_cells": [],
        "blank_cells": [],
    }
    cells = []
    for i, oid in enumerate(obj_ids):
        for j, sid in enumerate(sol_ids):
            cells.append((obj_names.get(oid, oid), sol_names.get(sid, sid), int(data[i][j])))
    cells.sort(key=lambda x: x[2], reverse=True)
    stats["top_cells"] = [{"object": c[0], "solution": c[1], "count": c[2]} for c in cells[:10]]
    stats["blank_cells"] = [{"object": c[0], "solution": c[1]} for c in cells if c[2] == 0]
    return stats


# ---- Chart 5: Detail O/S Matrix by Period (2x2 subplot) ----
def render_detail_os_period(records, categories, year_info, output_path):
    """2×2 heatmap subplots showing detail O/S matrix per period."""
    d_obj = categories.get("detail_object_categories", [])
    d_sol = categories.get("detail_solution_categories", [])
    periods = year_info.get("periods", [])

    if not d_obj or not d_sol or not periods:
        log("  WARN: insufficient data for detail period chart, skipping chart 5")
        return None

    for c in d_obj:
        c["_pattern"] = build_keyword_pattern(c.get("keywords", []))
    for c in d_sol:
        c["_pattern"] = build_keyword_pattern(c.get("keywords", []))

    obj_ids = [c["id"] for c in d_obj]
    sol_ids = [c["id"] for c in d_sol]
    obj_names = {c["id"]: c["name"] for c in d_obj}
    sol_names = {c["id"]: c["name"] for c in d_sol}

    period_matrices = {}
    for p in periods:
        period_matrices[p["period"]] = defaultdict(lambda: defaultdict(int))

    for rec in records:
        if not rec.get("problem") or not rec.get("solution") or rec.get("period") is None:
            continue
        o_matched = classify_text(rec["problem"], d_obj)
        s_matched = classify_text(rec["solution"], d_sol)
        if not o_matched or not s_matched:
            continue
        for oid in o_matched:
            if oid not in obj_ids:
                continue
            for sid in s_matched:
                if sid not in sol_ids:
                    continue
                period_matrices[rec["period"]][oid][sid] += 1

    subplot_count = min(4, len(periods))
    nrows = 2 if subplot_count > 2 else 1
    ncols = 2

    period_data = {}
    global_max = 0
    for p in periods[:4]:
        mat = np.zeros((len(obj_ids), len(sol_ids)))
        for i, oid in enumerate(obj_ids):
            for j, sid in enumerate(sol_ids):
                mat[i][j] = period_matrices[p["period"]][oid].get(sid, 0)
        period_data[p["period"]] = mat
        if mat.max() > global_max:
            global_max = mat.max()

    if global_max == 0:
        global_max = 1

    fig_h = max(FIG_H, 9 + len(obj_ids) * 0.2)
    fig, axes = plt.subplots(nrows, ncols, figsize=(FIG_W, fig_h))
    if nrows == 1:
        axes = np.array([axes]) if ncols > 1 else np.array([[axes]])
    axes_flat = axes.flatten()

    for idx, p in enumerate(periods[:4]):
        if idx >= len(axes_flat):
            break
        ax = axes_flat[idx]
        mat = period_data[p["period"]]
        im = ax.imshow(mat, cmap=PERIOD_CMAPS[idx % len(PERIOD_CMAPS)],
                       aspect="auto", vmin=0, vmax=global_max)

        fontsize = 7 if len(sol_ids) > 10 else 8
        for i in range(len(obj_ids)):
            for j in range(len(sol_ids)):
                val = int(mat[i][j])
                if val > 0:
                    color = "white" if val > global_max * 0.6 else "black"
                    indicator = ""
                    if idx > 0:
                        prev_p = periods[idx - 1]
                        prev_val = period_data[prev_p["period"]][i][j]
                        if prev_val == 0 and val > 0:
                            indicator = " ★"
                        elif prev_val > 0 and val >= prev_val * 2:
                            indicator = " ▲"
                        elif prev_val > 0 and val > prev_val:
                            indicator = " △"
                    ax.text(j, i, f"{val}{indicator}", ha="center", va="center",
                            fontsize=fontsize, fontweight="bold", color=color)

        label_len = 5 if len(sol_ids) > 10 else 6
        ax.set_xticks(range(len(sol_ids)))
        ax.set_xticklabels([sol_names.get(s, s)[:label_len] for s in sol_ids],
                           rotation=40, ha="right", fontsize=7)
        ax.set_yticks(range(len(obj_ids)))
        ax.set_yticklabels([obj_names.get(o, o)[:7] for o in obj_ids], fontsize=7)
        ax.set_title(p["label"], fontsize=12, fontweight="bold", pad=8)

    for idx in range(len(periods[:4]), len(axes_flat)):
        axes_flat[idx].set_visible(False)

    fig.suptitle("O/S Matrix 세부 구간별 변화", fontsize=18, fontweight="bold", y=1.02)
    legend_text = "★ 신규 출현  ▲ 급상승(2배↑)  △ 성장"
    fig.text(0.5, -0.02, legend_text, ha="center", fontsize=11,
             style="italic", color="#555555")

    plt.tight_layout()
    fig.savefig(output_path, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    log(f"  chart_q5.png saved")

    # Stats
    stats = {
        "chart_id": "q5",
        "title": "O/S Matrix 세부 구간별 변화",
        "periods": [p["label"] for p in periods[:4]],
        "growth_cells": [],
        "new_cells": [],
        "blank_cells": [],
    }
    for i, oid in enumerate(obj_ids):
        for j, sid in enumerate(sol_ids):
            vals = [int(period_data[p["period"]][i][j]) for p in periods[:4]]
            o_name = obj_names.get(oid, oid)
            s_name = sol_names.get(sid, sid)
            if all(v == 0 for v in vals):
                stats["blank_cells"].append({"object": o_name, "solution": s_name})
            elif len(vals) >= 2:
                for k in range(1, len(vals)):
                    if vals[k-1] > 0 and vals[k] >= vals[k-1] * 2:
                        stats["growth_cells"].append({
                            "object": o_name, "solution": s_name,
                            "from_period": periods[k-1]["label"],
                            "to_period": periods[k]["label"],
                            "from_val": vals[k-1], "to_val": vals[k],
                            "type": "급상승",
                        })
                    elif vals[k-1] == 0 and vals[k] > 0:
                        stats["new_cells"].append({
                            "object": o_name, "solution": s_name,
                            "period": periods[k]["label"],
                            "count": vals[k],
                            "type": "신규",
                        })
    return stats


def build_detail_os(records, categories, periods, period_spans, log):
    """Build detailed O/S matrix from detail_object/solution_categories."""
    d_obj = categories.get("detail_object_categories", [])
    d_sol = categories.get("detail_solution_categories", [])
    if not d_obj or not d_sol:
        return None

    for c in d_obj:
        c["_pattern"] = build_keyword_pattern(c.get("keywords", []))
    for c in d_sol:
        c["_pattern"] = build_keyword_pattern(c.get("keywords", []))

    d_obj_ids = [c["id"] for c in d_obj]
    d_sol_ids = [c["id"] for c in d_sol]
    d_obj_names = {c["id"]: c["name"] for c in d_obj}
    d_sol_names = {c["id"]: c["name"] for c in d_sol}

    # Classify
    os_mat = {}
    for rec in records:
        if not rec.get("problem") or not rec.get("solution") or rec.get("period") is None:
            continue
        o_matched = classify_text(rec["problem"], d_obj)
        s_matched = classify_text(rec["solution"], d_sol)
        if not o_matched or not s_matched:
            continue
        for oid in o_matched:
            if oid not in d_obj_ids:
                continue
            for sid in s_matched:
                if sid not in d_sol_ids:
                    continue
                key = f"{oid}_{sid}"
                if key not in os_mat:
                    os_mat[key] = {p["period"]: 0 for p in periods}
                os_mat[key][rec["period"]] = os_mat[key].get(rec["period"], 0) + 1

    # Build raw cells
    raw_cells = []
    for oid in d_obj_ids:
        for sid in d_sol_ids:
            key = f"{oid}_{sid}"
            pvals = [os_mat.get(key, {}).get(p["period"], 0) for p in periods]
            total = sum(pvals)
            annuals = [pvals[i] / period_spans[i] for i in range(len(pvals))]
            first_nz = next((a for a in annuals if a > 0), 0)
            latest_nz = next((a for a in reversed(annuals) if a > 0), 0)
            growth_ratio = (latest_nz / first_nz) if first_nz > 0 else 0
            early_sum = sum(pvals[:2])
            raw_cells.append({
                "objectId": oid, "objectName": d_obj_names.get(oid, oid),
                "solutionId": sid, "solutionName": d_sol_names.get(sid, sid),
                "periods": pvals, "total": total,
                "growth_ratio": growth_ratio, "early_sum": early_sum,
            })

    # Relative tagging
    nonzero = [c for c in raw_cells if c["total"] > 0]
    if nonzero:
        gr_sorted = sorted([c["growth_ratio"] for c in nonzero])
        tot_sorted = sorted([c["total"] for c in nonzero])
        es_sorted = sorted([c["early_sum"] for c in nonzero])
        def pct(lst, p):
            return lst[min(int(len(lst) * p / 100), len(lst) - 1)]
        g_th = pct(gr_sorted, 75)
        b_th = pct(tot_sorted, 25)
        e_th = pct(es_sorted, 10)
        g_med = pct(gr_sorted, 50)
        log(f"  detail thresholds: growth>={g_th:.2f}, blank<={b_th}, early<={e_th}")
    else:
        g_th = b_th = e_th = g_med = 0

    cells = []
    for c in raw_cells:
        tags = []
        if c["total"] == 0:
            tags.append("meaningless")
        elif nonzero:
            is_new = (c["early_sum"] <= e_th and c["growth_ratio"] >= g_med and c["total"] > b_th)
            is_growth = c["growth_ratio"] >= g_th
            is_blank = c["total"] <= b_th
            if is_new and not is_growth:
                tags.append("new")
            elif is_growth:
                tags.append("growth")
            elif is_blank:
                tags.append("blank")
        cells.append({
            "objectId": c["objectId"], "objectName": c["objectName"],
            "solutionId": c["solutionId"], "solutionName": c["solutionName"],
            "periods": c["periods"], "total": c["total"], "tags": tags,
        })

    return {
        "objects": [{"id": o, "name": d_obj_names.get(o, o)} for o in d_obj_ids],
        "solutions": [{"id": s, "name": d_sol_names.get(s, s)} for s in d_sol_ids],
        "periods": [{"period": p["period"], "label": p["label"]} for p in periods],
        "cells": cells,
    }


# ---- Main ----
def main():
    if len(sys.argv) < 2:
        print("Usage: python _gen_quality_charts.py <input_dir>")
        sys.exit(1)

    input_dir = Path(sys.argv[1])
    assets = input_dir / "_quality_assets"

    # Load inputs
    cat_path = assets / "categories.json"
    texts_path = assets / "extracted_texts.json"
    info_path = assets / "year_info.json"

    for p in [cat_path, texts_path, info_path]:
        if not p.exists():
            sys.exit(f"[charts] ERROR: {p.name} not found in {assets}")

    with open(cat_path, encoding="utf-8") as f:
        categories = json.load(f)
    with open(texts_path, encoding="utf-8") as f:
        records = json.load(f)
    with open(info_path, encoding="utf-8") as f:
        year_info = json.load(f)

    log(f"loaded: {len(records)} records, {len(categories.get('tech_themes', []))} themes, "
        f"{len(categories.get('object_categories', []))} O-cats, "
        f"{len(categories.get('solution_categories', []))} S-cats, "
        f"{len(categories.get('detail_object_categories', []))} detail-O, "
        f"{len(categories.get('detail_solution_categories', []))} detail-S")

    # Chart 1: Tech Flow
    log("rendering chart 1: 기술흐름도...")
    stats1 = render_tech_flow(records, categories, year_info, assets / "chart_q1.png")
    if stats1:
        with open(assets / "stats_q1.json", "w", encoding="utf-8") as f:
            json.dump(stats1, f, ensure_ascii=False, indent=2)

    # Chart 2: O/S Matrix Overall
    log("rendering chart 2: O/S Matrix 전체...")
    stats2 = render_os_matrix(records, categories, assets / "chart_q2.png")
    if stats2:
        with open(assets / "stats_q2.json", "w", encoding="utf-8") as f:
            json.dump(stats2, f, ensure_ascii=False, indent=2)

    # Chart 3: O/S Matrix by Period
    log("rendering chart 3: O/S Matrix 구간별...")
    stats3 = render_os_period(records, categories, year_info, assets / "chart_q3.png")
    if stats3:
        with open(assets / "stats_q3.json", "w", encoding="utf-8") as f:
            json.dump(stats3, f, ensure_ascii=False, indent=2)

    # Chart 4: Detail O/S Matrix Overall
    log("rendering chart 4: O/S Matrix 세부 전체...")
    stats4 = render_detail_os_matrix(records, categories, assets / "chart_q4.png")
    if stats4:
        with open(assets / "stats_q4.json", "w", encoding="utf-8") as f:
            json.dump(stats4, f, ensure_ascii=False, indent=2)

    # Chart 5: Detail O/S Matrix by Period
    log("rendering chart 5: O/S Matrix 세부 구간별...")
    stats5 = render_detail_os_period(records, categories, year_info, assets / "chart_q5.png")
    if stats5:
        with open(assets / "stats_q5.json", "w", encoding="utf-8") as f:
            json.dump(stats5, f, ensure_ascii=False, indent=2)

    # ---- Dashboard JSON (interactive Sankey + O/S Matrix) ----
    log("generating dashboard_data.json...")
    dashboard = build_dashboard_data(records, categories, year_info)
    with open(assets / "dashboard_data.json", "w", encoding="utf-8") as f:
        json.dump(dashboard, f, ensure_ascii=False, indent=2)
    log("saved dashboard_data.json")

    log("Stage A2 complete.")

if __name__ == "__main__":
    main()
