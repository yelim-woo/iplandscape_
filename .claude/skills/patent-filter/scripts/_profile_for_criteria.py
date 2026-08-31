# -*- coding: utf-8 -*-
"""
선정기준 자동 생성용 데이터 프로파일러.
1차 통과본(stage1_pass.json)을 읽어, Claude 가 선정기준 초안을 작성할 수 있도록
대표성 있는 요약 프로파일을 만든다 — 전체를 다 읽지 않아도 기술 범위를 파악하게 함.

출력 (<raw_folder>/_filter/data_profile.json):
  total            1차 통과 건수
  ipc_top          IPC 서브클래스(B25J 등) 상위 분포 [{code, count}]
  samples          IPC 서브클래스별로 고르게 뽑은 대표 레코드 [{uid, 명칭, 요약(앞부분), ipc}]

Usage:
  python _profile_for_criteria.py <raw_folder> [--n 40]
"""
import os, json, re, argparse
from collections import Counter, defaultdict

IPC_SUB = re.compile(r"[A-H]\d{2}[A-Z]")


def subclasses(ipc_str):
    if not ipc_str:
        return []
    out = []
    for p in re.split(r"[;,|\n]+", str(ipc_str)):
        m = IPC_SUB.search(p.strip().upper())
        if m:
            out.append(m.group(0))
    return list(dict.fromkeys(out))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--n", type=int, default=40, help="대표 샘플 개수")
    args = ap.parse_args()

    folder = os.path.abspath(args.folder)
    pass_json = os.path.join(folder, "_filter", "stage1_pass.json")
    if not os.path.exists(pass_json):
        raise SystemExit(f"[profile] ERROR: 먼저 1차 필터를 실행하세요. 없음: {pass_json}")

    recs = json.load(open(pass_json, encoding="utf-8"))
    total = len(recs)

    # IPC 서브클래스 분포
    ipc_counter = Counter()
    by_sub = defaultdict(list)
    for r in recs:
        subs = subclasses(r.get("ipc", ""))
        key = subs[0] if subs else "기타"
        by_sub[key].append(r)
        for s in (subs or ["기타"]):
            ipc_counter[s] += 1

    ipc_top = [{"code": c, "count": n} for c, n in ipc_counter.most_common(15)]

    # IPC 서브클래스별로 라운드로빈하여 고르게 샘플링 (대표성 확보)
    groups = sorted(by_sub.items(), key=lambda kv: -len(kv[1]))
    samples, idx = [], 0
    while len(samples) < min(args.n, total):
        progressed = False
        for _, items in groups:
            if idx < len(items):
                r = items[idx]
                samples.append({
                    "uid": r["uid"],
                    "명칭": r.get("명칭", ""),
                    "요약": (r.get("요약", "") or "")[:300],
                    "ipc": r.get("ipc", ""),
                })
                progressed = True
                if len(samples) >= min(args.n, total):
                    break
        if not progressed:
            break
        idx += 1

    out = {"total": total, "ipc_top": ipc_top, "samples": samples}
    out_path = os.path.join(folder, "_filter", "data_profile.json")
    json.dump(out, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"[profile] 1차 통과 {total}건 -> 대표샘플 {len(samples)}건, IPC상위 {len(ipc_top)}종 -> {out_path}")


if __name__ == "__main__":
    main()
