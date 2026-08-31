# -*- coding: utf-8 -*-
"""
특허맵 등고선(landscape contour). IPC 서브클래스 기반 기술공간을 2D로 투영(PCA)하고
가우시안 KDE 밀도를 등고선으로 그린다. 핫스팟(밀집)과 White Space(저밀도) 후보를 표시.

Usage: python _contour.py <folder>
출력(모드별):
  --mode ipc      → <folder>/_ipl/qualitative/{contour_map_ipc.png, contour_ipc.json}   (핫스팟 키 'ipc')
  --mode keyword  → <folder>/_ipl/qualitative/{contour_map_tech.png, contour_tech.json}  (핫스팟 키 'term')
hotspots/whitespace 는 라벨이 달린 통계. 의미 해석은 Claude가 채운다.
"""
import sys, os, json, re
from collections import Counter
from _ipl_io import ensure_pkgs, korean_font, load_patents, resolve, ipl_dir

ensure_pkgs(["pandas", "numpy", "matplotlib", "openpyxl", "pillow"])
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import rcParams
rcParams["font.family"] = korean_font()
rcParams["axes.unicode_minus"] = False

IPC_RE = re.compile(r"([A-H]\d{2}[A-Z])")  # 서브클래스 4자리 (예: H01M)


def extract_subclasses(val):
    if val is None:
        return []
    return list(dict.fromkeys(IPC_RE.findall(str(val).upper())))  # 중복 제거, 순서 유지


def pca_2d(X):
    """numpy SVD 기반 2D PCA. X: (n, d)."""
    Xc = X - X.mean(axis=0, keepdims=True)
    U, S, Vt = np.linalg.svd(Xc, full_matrices=False)
    comp = Vt[:2].T          # (d, 2)
    return Xc @ comp


def gaussian_kde_grid(pts, gx, gy, bw):
    """격자(gx,gy) 위 가우시안 KDE 밀도. pts:(n,2)."""
    XX, YY = np.meshgrid(gx, gy)
    Z = np.zeros_like(XX, dtype=float)
    inv2b2 = 1.0 / (2 * bw * bw)
    for px, py in pts:
        Z += np.exp(-((XX - px) ** 2 + (YY - py) ** 2) * inv2b2)
    return XX, YY, Z


# ---- 키워드(기술주제) 모드 ----
STOP = set((
    "the a an and or of to in for with on at by from as is are be was were this that these those it its their "
    "system method device apparatus comprising said wherein according present invention having includes including "
    "based use used using provide provided providing module unit means thereof such can may also one first second "
    "least via between each into out over under more less than which has have when then them they our we per said "
    "configured plurality least may including related field background summary embodiment example figure said "
    "relates capable respectively corresponding associated "
    # 특허/일반 잡음어
    "same value values data signal information time number portion surface side member part body structure layer "
    "region area amount level state mode operation process processing output input line point position direction "
    "range end top bottom inner outer set group type form shape size high low large small total main sub multi "
    "single common general specific various different certain predetermined respective includes included provides "
    "allows enables comprises further thereby therein thereto whereby claim claims control controlling controlled "
    "connected coupled disposed arranged formed defined extending extends side second third fourth plurality "
    "comprise device unit assembly component element components elements result results function functions object "
    "objects step steps detail details aspect aspects feature features manner non "
    # Lens/중국 초록 상투어
    "include included through discloses disclose disclosed disclosure model utility technical improved present "
    "herein relating regarding solution problem effect belongs namely whole provided mounted installed equipment "
    "able about above within without while during after before both either neither "
    # 특허/명세서 보일러플레이트 — 거의 모든 특허에 나와 변별력 없음(단수만 등록, 복수는 _canon이 정규화)
    "composition formulation mixture agent compound preparation product substance ingredient material "
    "method system device apparatus means step process unit module assembly content concentration property "
    "characteristic treatment application use product invention embodiment example figure aspect feature "
    "extract extraction extracting containing contain effective effectiveness efficacy prepared obtained "
    "derived manufacture manufacturing produce produced producing addition additional comprising including "
    "providing relating disclosed component element function object result detail manner technology technique "
    "field present novel improved high low good excellent superior suitable desired predetermined "
    # JP/INPIT 영문초록 푸터·상투어 + 잔여 보일러플레이트
    "jpo inpit copyright drawing selected select selecting relate relates relating none kind type "
    "preparing prepare produce producing solving solved selectively respectively wherein said problem").split())
TOK = re.compile(r"[A-Za-z][A-Za-z\-]{2,}")


def _canon(t):
    """복수형 → 단수형 단순 정규화(집계 통합 + 단수 STOP로 복수 차단). 보수적 규칙."""
    if len(t) > 4 and t.endswith("ies"):
        return t[:-3] + "y"                       # properties->property
    if len(t) > 4 and t.endswith(("ses", "xes", "ches", "shes", "zes")):
        return t[:-2]                             # processes->process
    if len(t) > 3 and t.endswith("s") and not t.endswith(("ss", "us", "is", "ous", "sis", "as", "os")):
        return t[:-1]                             # methods->method, systems->system
    return t


def extract_terms(text):
    if text is None:
        return []
    out = []
    for raw in (x.lower() for x in TOK.findall(str(text))):
        c = _canon(raw)
        # 원형·정규형 둘 다 STOP 체크(정규화가 불용어를 변형해 통과하는 것 방지)
        if len(c) > 2 and raw not in STOP and c not in STOP:
            out.append(c)
    return list(dict.fromkeys(out))               # 문서 내 중복 제거(문서빈도 집계용)


def build_features_ipc(df, r):
    ipc_col = r["ipc_all"] or r["ipc_main"]
    if not ipc_col:
        return None, "IPC 컬럼 없음"
    df["_feat"] = df[ipc_col].map(extract_subclasses)
    df2 = df[df["_feat"].map(len) > 0].copy()
    if len(df2) < 10:
        return None, f"IPC 보유 특허 {len(df2)}건 — 부족"
    allt = Counter(s for fs in df2["_feat"] for s in fs)
    K = min(40, len(allt)); top = [s for s, _ in allt.most_common(K)]
    tset = set(top); freq = dict(allt)
    M = np.zeros((len(df2), K)); idx = {s: i for i, s in enumerate(top)}; dom = []
    for i, fs in enumerate(df2["_feat"].tolist()):
        hit = [s for s in fs if s in tset]
        for s in hit:
            M[i, idx[s]] = 1.0
        dom.append(min(hit, key=lambda s: freq[s]) if hit else None)  # 가장 특이한 분류
    return (M, dom, top, df2), None


def build_features_keyword(df, r):
    tcol, acol = r.get("title"), r.get("abstract")
    if not (tcol or acol):
        return None, "제목/초록 컬럼 없음"
    def terms(row):
        t = (str(row[tcol]) if tcol and pd.notna(row[tcol]) else "") + " " + \
            (str(row[acol]) if acol and pd.notna(row[acol]) else "")
        return extract_terms(t)
    df["_feat"] = df.apply(terms, axis=1)
    df2 = df[df["_feat"].map(len) >= 3].copy()
    if len(df2) < 20:
        return None, f"텍스트 보유 특허 {len(df2)}건 — 부족"
    dfreq = Counter(t for fs in df2["_feat"] for t in fs)
    # 너무 흔하거나(>25% — 거의 모든 특허에 나오는 비변별 용어) 너무 드문(<1.5%) 용어 제외 후 top-K
    n = len(df2)
    cand = [(t, c) for t, c in dfreq.items() if 0.015 * n <= c <= 0.25 * n]
    cand.sort(key=lambda x: -x[1])
    K = min(60, len(cand)); top = [t for t, _ in cand[:K]]
    tset = set(top); freq = {t: dfreq[t] for t in top}
    M = np.zeros((len(df2), K)); idx = {t: i for i, t in enumerate(top)}; dom = []
    for i, fs in enumerate(df2["_feat"].tolist()):
        hit = [t for t in fs if t in tset]
        for t in hit:
            M[i, idx[t]] = 1.0
        dom.append(min(hit, key=lambda t: freq[t]) if hit else None)  # 가장 특이한 용어
    keep = M.sum(axis=1) > 0
    return (M[keep], [d for d, k in zip(dom, keep) if k], top, df2[keep]), None


MODES = {
    "ipc": {"build": build_features_ipc, "label": "ipc", "fname": "contour_map_ipc.png",
            "json": "contour_ipc.json", "title": "특허맵 — IPC 기술분류 등고선",
            "xlabel": "기술축 1 (IPC 주성분)", "ylabel": "기술축 2 (IPC 주성분)",
            "note": "축은 IPC 공동출현 기반 PCA 주성분(무차원). 군집·밀도·공백 패턴을 해석할 것."},
    "keyword": {"build": build_features_keyword, "label": "term", "fname": "contour_map_tech.png",
                "json": "contour_tech.json", "title": "특허맵 — 기술주제(키워드) 등고선",
                "xlabel": "주제축 1 (용어 주성분)", "ylabel": "주제축 2 (용어 주성분)",
                "note": "축은 제목·초록 용어 공동출현 기반 PCA 주성분. IPC 분류와 달리 '무엇에 관한 특허인가'(주제) 관점의 지형."},
}


def main():
    folder = sys.argv[1]
    mode = "ipc"
    if "--mode" in sys.argv:
        mode = sys.argv[sys.argv.index("--mode") + 1]
    cfg = MODES[mode]
    df = load_patents(folder)
    r = resolve(df)
    out = ipl_dir(folder, "qualitative")

    built, err = cfg["build"](df, r)
    if err:
        (out / cfg["json"]).write_text(json.dumps({"error": err, "mode": mode}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[error] ({mode}) {err}")
        return
    M, dom, top_terms, _ = built
    if M.shape[0] < 5 or M.shape[1] < 2:
        (out / cfg["json"]).write_text(json.dumps(
            {"error": f"({mode}) 2D 투영에 부족한 데이터 — 특허 {M.shape[0]}건·특징 {M.shape[1]}개", "mode": mode},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[error] ({mode}) 특징 차원 부족(특허 {M.shape[0]}·특징 {M.shape[1]}) — 등고선 생략")
        return

    # 2D 투영 + 지터
    P = pca_2d(M)
    rng = np.random.RandomState(42)
    span = (P.max(0) - P.min(0))
    P = P + rng.normal(0, 1, P.shape) * (span * 0.012 + 1e-6)

    x, y = P[:, 0], P[:, 1]
    pad = 0.08
    xr = (x.min() - (x.max() - x.min()) * pad, x.max() + (x.max() - x.min()) * pad)
    yr = (y.min() - (y.max() - y.min()) * pad, y.max() + (y.max() - y.min()) * pad)
    gx = np.linspace(*xr, 70)
    gy = np.linspace(*yr, 70)
    bw = 0.18 * np.hypot(x.std(), y.std()) + 1e-6
    XX, YY, Z = gaussian_kde_grid(P, gx, gy, bw)

    # ---- 핫스팟: 밀도 상위 셀에서 '지역 과대표현' 상위 라벨 추출 (M 기반) ----
    label_key = cfg["label"]
    gcount = M.sum(axis=0) + 1.0           # 전역 빈도(+smooth)
    top_arr = np.array(top_terms)
    used_labels = set()

    def region_label(cxv, cyv, radius):
        mask = np.hypot(x - cxv, y - cyv) < radius
        if mask.sum() == 0:
            return []
        reg = M[mask].sum(axis=0)           # 지역 내 빈도(주요 테마)
        order = np.argsort(-reg)
        return [top_terms[i] for i in order if reg[i] > 0][:8]

    hotspots = []
    used = np.zeros_like(Z, dtype=bool)
    for _ in range(6):
        if len(hotspots) >= 4:
            break
        idx = np.unravel_index(np.argmax(np.where(used, -1, Z)), Z.shape)
        cy, cx = idx
        cxv, cyv = gx[cx], gy[cy]
        labs = region_label(cxv, cyv, bw * 1.6)
        used[max(0, cy - 7):cy + 8, max(0, cx - 7):cx + 8] = True
        lab = next((l for l in labs if l not in used_labels), labs[0] if labs else None)
        if not lab:
            continue
        used_labels.add(lab)
        hotspots.append({label_key: lab, "density": round(float(Z[cy, cx]), 3),
                         "n_near": int((np.hypot(x - cxv, y - cyv) < bw * 1.6).sum()),
                         "xy": [round(cxv, 3), round(cyv, 3)]})

    # ---- White Space: 데이터 범위 내부지만 저밀도인 셀 ----
    inside = Z > Z.max() * 0.02
    low = (Z < Z.max() * 0.12) & inside
    ws_pts = []
    ys, xs = np.where(low)
    if len(xs) > 0:
        sel = np.linspace(0, len(xs) - 1, min(3, len(xs))).astype(int)
        for k in sel:
            cxv, cyv = gx[xs[k]], gy[ys[k]]
            labs = region_label(cxv, cyv, bw * 2.2)[:2]
            ws_pts.append({"xy": [round(cxv, 3), round(cyv, 3)],
                           "near_ipc": labs,
                           "density": round(float(Z[ys[k], xs[k]]), 3)})

    # ---- 렌더 ----
    fig, ax = plt.subplots(figsize=(10, 7.5))
    fig.set_facecolor("#fafafa")
    cf = ax.contourf(XX, YY, Z, levels=14, cmap="YlOrRd", alpha=0.9)
    ax.contour(XX, YY, Z, levels=14, colors="white", linewidths=0.4, alpha=0.5)
    ax.scatter(x, y, s=6, c="#1f2937", alpha=0.25, linewidths=0)
    for h in hotspots:
        ax.annotate(h[label_key], h["xy"], fontsize=11, fontweight="bold", color="#111827",
                    ha="center", va="center",
                    bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="#dc2626", alpha=0.9))
    for w in ws_pts:
        ax.annotate("White Space", w["xy"], fontsize=8, color="#1d4ed8", ha="center",
                    bbox=dict(boxstyle="round,pad=0.2", fc="#dbeafe", ec="#1d4ed8", alpha=0.85))
    # 차트 내 제목은 생략(보고서가 〈그림 N-M〉 캡션을 붙임) — 전 장 차트와 통일
    ax.set_xlabel(cfg["xlabel"], fontsize=12, color="#444444")
    ax.set_ylabel(cfg["ylabel"], fontsize=12, color="#444444")
    ax.tick_params(labelsize=11, colors="#333333")
    fig.colorbar(cf, ax=ax, shrink=0.8, label="특허 밀도")
    fig.tight_layout()
    fig.savefig(out / cfg["fname"], dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)

    result = {
        "mode": mode, "n_patents": int(len(P)), "n_features": len(top_terms),
        "top_terms": top_terms[:18], "hotspots": hotspots, "whitespace": ws_pts,
        "chart": str(out / cfg["fname"]), "note": cfg["note"],
    }
    (out / cfg["json"]).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ok] ({mode}) 등고선 생성 → {out/cfg['fname']}")
    print(f"     핫스팟 {len(hotspots)}개: {[h[label_key] for h in hotspots]}")
    print(f"     White Space 후보 {len(ws_pts)}개")


if __name__ == "__main__":
    main()
