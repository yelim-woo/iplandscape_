# -*- coding: utf-8 -*-
"""
기술흐름도(tech_flow.png) + O/S Matrix 전체 히트맵(os_matrix.png)
유효데이터.xlsx(load_patents, 전 관할)만 사용해 등고선/구간매트릭스와 동일 모집단으로 생성.
- tech_flow: 로봇 기술주제(7~8개) 연도별 stacked area
- os_matrix: Object(해결과제) × Solution(해결수단) 공동분류 빈도 히트맵(전체)
카테고리(O/S)는 os_categories.json 재사용, 기술주제는 내장 로봇 주제.
Usage: python _qual_flow_osheat.py <folder>
출력: <folder>/_ipl/qualitative/{tech_flow.png, os_matrix.png} (+ 통계 반환)
"""
import sys, os, json
from collections import Counter, defaultdict
from _ipl_io import (ensure_pkgs, korean_font, load_patents, resolve, ipl_dir, parse_year,
                     chart_fig, style_axes, axis_unit, mark_incomplete_year, IPL_PALETTE)

ensure_pkgs(["pandas", "numpy", "matplotlib", "openpyxl", "pillow"])
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import rcParams
rcParams["font.family"] = korean_font()
rcParams["axes.unicode_minus"] = False

# 로봇/로보틱스 기술주제 (요약+명칭 매칭). 변별력 있는 도메인 용어 위주.
TECH_THEMES = [
    ["이동·자율주행 로봇", ["mobile robot", "autonomous", "self-driving", "agv", "amr", "travel", "locomotion",
                     "주행", "이동로봇", "자율주행", "무인운반"]],
    ["매니퓰레이터·파지", ["manipulator", "robot arm", "gripper", "grasp", "grip", "end effector", "pick",
                     "manipulation", "매니퓰레이터", "로봇팔", "그리퍼", "파지", "말단"]],
    ["SLAM·인식·비전", ["slam", "localization", "mapping", "vision", "camera", "lidar", "point cloud",
                     "recognition", "detection", "인식", "비전", "지도작성", "측위"]],
    ["경로계획·모션제어", ["path planning", "trajectory", "motion planning", "navigation", "waypoint",
                     "control algorithm", "feedback control", "경로", "궤적", "모션", "제어"]],
    ["기구·액추에이터·구동", ["actuator", "motor", "joint", "servo", "drivetrain", "mechanism", "linkage",
                     "wheel drive", "액추에이터", "관절", "구동", "기구", "메커니즘"]],
    ["휴머노이드·보행·소셜", ["humanoid", "legged", "biped", "walking", "gait", "wearable", "exoskeleton",
                     "social robot", "휴머노이드", "보행", "이족", "웨어러블", "외골격"]],
    ["수술·의료·재활 로봇", ["surgical", "surgery", "medical robot", "catheter", "rehabilitation", "endoscop",
                     "수술", "의료로봇", "재활", "내시경"]],
    ["협동·군집·원격제어", ["collaborative", "cobot", "multi-robot", "swarm", "fleet", "teleoperation",
                     "remote control", "human-robot", "협동", "군집", "원격", "협업"]],
]


def load_cats(folder):
    for sub in ("qualitative", "competitor"):
        p = os.path.join(folder, "_ipl", sub, "os_categories.json")
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as f:
                    c = json.load(f)
                if c.get("object") and c.get("solution"):
                    return c
            except Exception:
                pass
    return None


def classify_multi(text, group):
    """다중 분류: 매칭되는 모든 라벨 반환."""
    if not isinstance(text, str) or not text.strip():
        return []
    t = text.lower()
    hit = []
    for label, kws in group:
        if any(k.lower() in t for k in kws):
            hit.append(label)
    return hit


def main():
    folder = sys.argv[1]
    df = load_patents(folder)
    r = resolve(df)
    out = ipl_dir(folder, "qualitative")
    cats = load_cats(folder)
    if not cats:
        print("[error] os_categories.json 없음"); sys.exit(1)
    objs_def, sols_def = cats["object"], cats["solution"]

    def big_text(row):
        parts = []
        for role in ("abstract", "title", "problem", "solution"):
            col = r.get(role)
            if col and pd.notna(row.get(col)):
                parts.append(str(row[col]))
        return " ".join(parts)
    df["_txt"] = df.apply(big_text, axis=1)
    df["_year"] = parse_year(df[r["filing_date"]]) if r.get("filing_date") else None

    # ---------- 기술흐름도 ----------
    yrs = pd.to_numeric(df["_year"], errors="coerce")
    ymax = int(yrs.dropna().max())
    ymin = int(yrs.dropna().min())
    # 흐름도는 최근 12년으로 제한(초기 희소 연도 제거)
    y_start = max(ymin, ymax - 12)
    years = list(range(y_start, ymax + 1))
    theme_names = [t[0] for t in TECH_THEMES]
    flow = {th: {y: 0 for y in years} for th in theme_names}
    theme_total = Counter()
    for _, row in df.iterrows():
        y = row["_year"]
        if pd.isna(y):
            continue
        y = int(y)
        if y < y_start or y > ymax:
            continue
        hits = classify_multi(row["_txt"], TECH_THEMES)
        for h in hits:
            flow[h][y] += 1
            theme_total[h] += 1

    fig, ax = chart_fig(w=9.5, h=5.3)
    ys = np.array(years)
    stack = np.array([[flow[th][y] for y in years] for th in theme_names])
    # 총량 큰 주제부터 아래에 쌓기
    order = np.argsort(-stack.sum(axis=1))
    stack_o = stack[order]
    labels_o = [theme_names[i] for i in order]
    colors = [IPL_PALETTE[i % len(IPL_PALETTE)] for i in range(len(labels_o))]
    ax.stackplot(ys, stack_o, labels=labels_o, colors=colors, alpha=0.9, edgecolor="white", linewidth=0.4)
    style_axes(ax, grid="y")
    axis_unit(ax, "건수", axis="y")
    ax.set_xlim(years[0], years[-1])
    ax.set_xticks(years)
    ax.tick_params(axis="x", labelrotation=0)
    if len(years) >= 4:
        mark_incomplete_year(ax, years)
    ax.legend(loc="upper left", fontsize=8, ncol=2, frameon=False)
    fig.tight_layout()
    fig.savefig(out / "tech_flow.png", dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)

    # ---------- O/S Matrix 전체 히트맵 ----------
    obj_labels = [o for o, _ in objs_def]
    sol_labels = [s for s, _ in sols_def]
    mat = np.zeros((len(sol_labels), len(obj_labels)), dtype=int)  # 행=Solution, 열=Object
    n_class = 0
    for _, row in df.iterrows():
        o_hits = classify_multi(row["_txt"], objs_def)
        s_hits = classify_multi(row["_txt"], sols_def)
        if o_hits and s_hits:
            n_class += 1
        for o in o_hits:
            for s in s_hits:
                mat[sol_labels.index(s)][obj_labels.index(o)] += 1

    fig2, ax2 = plt.subplots(figsize=(9.8, 6.4), dpi=150)
    fig2.set_facecolor("#ffffff"); ax2.set_facecolor("#ffffff")
    im = ax2.imshow(mat, cmap="YlGnBu", aspect="auto")
    ax2.set_xticks(range(len(obj_labels)))
    ax2.set_xticklabels(obj_labels, rotation=30, ha="right", fontsize=9)
    ax2.set_yticks(range(len(sol_labels)))
    ax2.set_yticklabels(sol_labels, fontsize=9)
    ax2.set_xlabel("Object (목적·해결과제)", fontsize=10, color="#444")
    ax2.set_ylabel("Solution (수단·해결수단)", fontsize=10, color="#444")
    mx = mat.max() if mat.max() > 0 else 1
    for i in range(len(sol_labels)):
        for j in range(len(obj_labels)):
            v = mat[i][j]
            ax2.text(j, i, str(v), ha="center", va="center", fontsize=8.5,
                     color="white" if v > mx * 0.55 else "#333", fontweight="bold")
    cb = fig2.colorbar(im, ax=ax2, fraction=0.035, pad=0.02)
    cb.ax.tick_params(labelsize=8)
    for sp in ax2.spines.values():
        sp.set_visible(False)
    ax2.tick_params(length=0)
    fig2.tight_layout()
    fig2.savefig(out / "os_matrix.png", dpi=150, bbox_inches="tight", facecolor="#ffffff")
    plt.close(fig2)

    stats = {
        "tech_flow": {"years": years, "themes": {th: theme_total[th] for th in theme_names},
                      "by_year": {th: [flow[th][y] for y in years] for th in theme_names}},
        "os_matrix": {"objects": obj_labels, "solutions": sol_labels,
                      "matrix": mat.tolist(), "n_classified": n_class,
                      "obj_totals": {o: int(mat[:, j].sum()) for j, o in enumerate(obj_labels)},
                      "sol_totals": {s: int(mat[i, :].sum()) for i, s in enumerate(sol_labels)}},
    }
    (out / "_flow_osheat_stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")
    print("[ok] tech_flow.png / os_matrix.png 생성")
    print("  themes:", dict(theme_total.most_common()))
    print("  os n_classified:", n_class, "| max cell:", int(mat.max()))


if __name__ == "__main__":
    main()
