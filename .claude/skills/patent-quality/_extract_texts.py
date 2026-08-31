# -*- coding: utf-8 -*-
"""
Stage A: Extract qualitative text fields from patent Excel data.
Outputs JSON files for Claude Code to define categories.

Usage: python _extract_texts.py <input_dir> [--column-map map.json]
"""
import sys, os, glob, json, re, random
from pathlib import Path
import pandas as pd

# ---- Column alias table (reused from patent-trend) ----
COLUMN_ALIASES = {
    # 출원일
    "출원일자": "출원일", "출원 일자": "출원일", "출원일(국제)": "출원일",
    "출원년월일": "출원일", "application date": "출원일", "filing date": "출원일",
    "filing_date": "출원일", "app date": "출원일", "app_date": "출원일",
    "date of application": "출원일", "date of filing": "출원일",
    "earliest filing date": "출원일", "earliest_filing_date": "출원일",
    # 국가코드
    "국가": "국가코드", "country": "국가코드", "country code": "국가코드",
    "country_code": "국가코드", "국가 코드": "국가코드", "출원국": "국가코드",
    "출원국가": "국가코드", "patent office": "국가코드", "office": "국가코드",
    "authority": "국가코드",
}

# Text column candidates (priority order for each field)
SUMMARY_CANDIDATES = [
    "요약-번역문", "요약-기타 원어", "AI 요약[KR,JP,CN,US,EP,PCT]",
    "기술분야 요약[KR,JP,CN,US,EP,PCT]", "요약",
]
PROBLEM_CANDIDATES = [
    "해결과제 요약[KR,JP,CN,US,EP,PCT]",
    "해결과제 요약",
]
SOLUTION_CANDIDATES = [
    "해결수단 요약[KR,JP,CN,US,EP,PCT]",
    "해결수단 요약",
]
TITLE_CANDIDATES = [
    "발명의 명칭-번역문", "발명의 명칭-기타 원어", "발명의 명칭",
]

def log(msg):
    print(f"[extract] {msg}", flush=True)

def _detect_date_column(series):
    sample = series.dropna().head(50).astype(str)
    if len(sample) == 0:
        return False
    date_pat = re.compile(r"^\d{4}[-/.]?\d{2}[-/.]?\d{2}")
    match_count = sum(1 for v in sample if date_pat.match(v.strip()))
    return match_count / len(sample) > 0.5

def auto_map_columns(df, explicit_map=None):
    """Auto-map column names. Only maps 출원일 and 국가코드 (critical for this script)."""
    rename_map = {}
    mapped_targets = set()

    # Exact matches
    for col in ["출원일", "국가코드"]:
        if col in df.columns:
            mapped_targets.add(col)

    # Explicit mapping
    if explicit_map:
        for src, dst in explicit_map.items():
            if src in df.columns and dst not in mapped_targets:
                rename_map[src] = dst
                mapped_targets.add(dst)

    # Alias matching
    for col in df.columns:
        if col in rename_map:
            continue
        key = col.strip().lower()
        if key in COLUMN_ALIASES:
            target = COLUMN_ALIASES[key]
            if target not in mapped_targets:
                rename_map[col] = target
                mapped_targets.add(target)

    # Pattern detection for 출원일
    if "출원일" not in mapped_targets:
        filing_kw = ["출원", "filing", "application", "app_date"]
        unmapped = [c for c in df.columns if c not in rename_map and c not in mapped_targets]
        candidates = [c for c in unmapped if any(k in c.lower() for k in filing_kw)]
        if not candidates:
            candidates = unmapped
        for col in candidates:
            if _detect_date_column(df[col]):
                rename_map[col] = "출원일"
                mapped_targets.add("출원일")
                break

    if rename_map:
        log(f"  column mapping: {rename_map}")
        df = df.rename(columns=rename_map)
    return df

def extract_year(val):
    if pd.isna(val):
        return None
    s = str(val).strip()
    m = re.match(r"^(\d{4})", s)
    if m:
        y = int(m.group(1))
        return y if 1970 <= y <= 2050 else None
    return None

def pick_text(row, candidates):
    """Pick the first non-empty text from candidate columns."""
    for col in candidates:
        if col in row.index:
            val = row[col]
            if pd.notna(val) and str(val).strip():
                return str(val).strip()
    return ""

def compute_periods(years, current_year=None):
    """Compute 4 periods from year list.
    Period 4 = unpublished window (last ~1.5 years).
    Periods 1-3 = remaining range split into 3 equal parts.
    """
    if current_year is None:
        from datetime import datetime
        current_year = datetime.now().year

    min_year = min(years)
    max_year = max(years)

    # Unpublished period: typically patents filed in the last 1.5~2 years aren't published yet
    unpub_start = current_year - 1  # conservative: last 2 years as unpublished
    # But if max_year < current_year - 2, there's no real unpublished window
    if max_year < unpub_start:
        unpub_start = max_year  # no unpublished period

    # Published range
    pub_end = unpub_start - 1
    pub_range = pub_end - min_year + 1

    if pub_range <= 0:
        # All data is in unpublished range
        return [
            {"period": 1, "label": f"1구간({min_year}~{max_year})", "start": min_year, "end": max_year},
        ]

    # Split published range into 3 roughly equal parts
    chunk = max(1, pub_range // 3)
    p1_end = min_year + chunk - 1
    p2_end = min_year + 2 * chunk - 1
    p3_end = pub_end

    periods = [
        {"period": 1, "label": f"1구간({min_year}~{p1_end})", "start": min_year, "end": p1_end},
        {"period": 2, "label": f"2구간({p1_end+1}~{p2_end})", "start": p1_end + 1, "end": p2_end},
        {"period": 3, "label": f"3구간({p2_end+1}~{p3_end})", "start": p2_end + 1, "end": p3_end},
    ]

    if unpub_start <= max_year:
        periods.append({
            "period": 4,
            "label": f"미공개구간({unpub_start}~{max_year})",
            "start": unpub_start,
            "end": max_year,
        })

    return periods

def year_to_period(year, periods):
    for p in periods:
        if p["start"] <= year <= p["end"]:
            return p["period"]
    return None

def main():
    if len(sys.argv) < 2:
        print("Usage: python _extract_texts.py <input_dir> [--column-map map.json]")
        sys.exit(1)

    input_dir = Path(sys.argv[1])
    explicit_map = None
    if "--column-map" in sys.argv:
        idx = sys.argv.index("--column-map")
        map_path = Path(sys.argv[idx + 1])
        with open(map_path, encoding="utf-8") as f:
            explicit_map = json.load(f)

    # Find Excel files
    xlsx_files = sorted(glob.glob(str(input_dir / "*.xlsx")))
    xlsx_files = [f for f in xlsx_files if not os.path.basename(f).startswith("~")]
    if not xlsx_files:
        sys.exit("[extract] ERROR: No .xlsx files found in " + str(input_dir))
    log(f"found {len(xlsx_files)} Excel file(s)")

    # Load and merge all Excel files
    frames = []
    for fp in xlsx_files:
        log(f"  loading: {os.path.basename(fp)}")
        try:
            df = pd.read_excel(fp, engine="openpyxl")
            df = auto_map_columns(df, explicit_map)
            frames.append(df)
        except Exception as e:
            log(f"  WARN: failed to load {fp}: {e}")

    if not frames:
        sys.exit("[extract] ERROR: No data loaded")

    df = pd.concat(frames, ignore_index=True)
    log(f"total rows: {len(df)}")

    # Extract year
    if "출원일" not in df.columns:
        sys.exit("[extract] ERROR: '출원일' column not found")

    df["_year"] = df["출원일"].apply(extract_year)
    df = df.dropna(subset=["_year"])
    df["_year"] = df["_year"].astype(int)
    log(f"rows with valid year: {len(df)}")

    if len(df) == 0:
        sys.exit("[extract] ERROR: No rows with valid year data")

    # Compute periods
    all_years = sorted(df["_year"].unique().tolist())
    periods = compute_periods(all_years)
    df["_period"] = df["_year"].apply(lambda y: year_to_period(y, periods))

    unmatched = df["_period"].isna().sum()
    log(f"year range: {min(all_years)}~{max(all_years)}")
    for p in periods:
        cnt = (df["_period"] == p["period"]).sum()
        log(f"  {p['label']}: {cnt}건")
    if unmatched > 0:
        log(f"  WARNING: {unmatched}건이 어떤 구간에도 매칭되지 않음")

    # Extract text fields
    records = []
    for idx, row in df.iterrows():
        summary = pick_text(row, SUMMARY_CANDIDATES)
        problem = pick_text(row, PROBLEM_CANDIDATES)
        solution = pick_text(row, SOLUTION_CANDIDATES)
        title = pick_text(row, TITLE_CANDIDATES)

        # Skip if all text fields are empty
        if not summary and not problem and not solution:
            continue

        rec = {
            "id": str(row.get("mergeId", row.get("WIPS ON key", idx))),
            "year": int(row["_year"]),
            "period": int(row["_period"]) if pd.notna(row["_period"]) else None,
            "title": title[:200] if title else "",
            "summary": summary[:500] if summary else "",
            "problem": problem[:400] if problem else "",
            "solution": solution[:400] if solution else "",
        }
        records.append(rec)

    log(f"records with text: {len(records)}")

    # Create output directory
    assets = input_dir / "_quality_assets"
    assets.mkdir(exist_ok=True)

    # 1. Save all extracted texts
    with open(assets / "extracted_texts.json", "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    log(f"saved extracted_texts.json ({len(records)} records)")

    # 2. Sample summaries by period (for tech flow categorization)
    sample_summary = {}
    for p in periods:
        period_recs = [r for r in records if r["period"] == p["period"] and r["summary"]]
        sample_size = min(20, len(period_recs))
        sampled = random.sample(period_recs, sample_size) if period_recs else []
        sample_summary[p["label"]] = [
            {"id": r["id"], "year": r["year"], "title": r["title"], "summary": r["summary"]}
            for r in sampled
        ]
    with open(assets / "sample_summary.json", "w", encoding="utf-8") as f:
        json.dump(sample_summary, f, ensure_ascii=False, indent=2)
    log("saved sample_summary.json")

    # 3. Sample O/S texts (for O/S matrix categorization)
    os_recs = [r for r in records if r["problem"] and r["solution"]]
    sample_size = min(40, len(os_recs))
    os_sampled = random.sample(os_recs, sample_size) if os_recs else []
    sample_os = [
        {"id": r["id"], "year": r["year"], "title": r["title"],
         "problem": r["problem"], "solution": r["solution"]}
        for r in os_sampled
    ]
    with open(assets / "sample_os.json", "w", encoding="utf-8") as f:
        json.dump(sample_os, f, ensure_ascii=False, indent=2)
    log(f"saved sample_os.json ({len(sample_os)} samples)")

    # 4. Year info
    period_counts = {}
    for p in periods:
        period_counts[p["label"]] = len([r for r in records if r["period"] == p["period"]])

    year_info = {
        "min_year": min(all_years),
        "max_year": max(all_years),
        "total_records": len(records),
        "total_with_summary": len([r for r in records if r["summary"]]),
        "total_with_problem": len([r for r in records if r["problem"]]),
        "total_with_solution": len([r for r in records if r["solution"]]),
        "periods": periods,
        "period_counts": period_counts,
        "year_counts": {str(y): len([r for r in records if r["year"] == y]) for y in all_years},
    }
    with open(assets / "year_info.json", "w", encoding="utf-8") as f:
        json.dump(year_info, f, ensure_ascii=False, indent=2)
    log("saved year_info.json")

    log("Stage A complete.")

if __name__ == "__main__":
    main()
