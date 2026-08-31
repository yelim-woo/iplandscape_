"""
Lens.org 수집 JSON → patent-trend/patent-quality 호환 엑셀 변환
"""

import argparse
import json
import os
import sys

import pandas as pd


def safe_get(d, *keys, default=""):
    """중첩 딕셔너리에서 안전하게 값 추출"""
    for key in keys:
        if isinstance(d, dict):
            d = d.get(key, default)
        elif isinstance(d, list) and isinstance(key, int) and key < len(d):
            d = d[key]
        else:
            return default
    return d if d is not None else default


def join_list(items, key="extracted_name", sep="; "):
    """리스트에서 특정 키 값을 추출하여 구분자로 결합"""
    if not isinstance(items, list):
        return ""
    values = []
    for item in items:
        if isinstance(item, dict):
            v = item.get(key, "") or item.get("name", "")
            if v:
                values.append(str(v))
    return sep.join(values)


def join_classifications(cls_data, sep="; "):
    """IPC/CPC 분류 코드 추출"""
    if not isinstance(cls_data, dict):
        return ""
    classifications = cls_data.get("classifications", [])
    if not isinstance(classifications, list):
        return ""
    symbols = []
    for c in classifications:
        if isinstance(c, dict):
            sym = c.get("symbol", "")
            if sym:
                symbols.append(str(sym))
    return sep.join(symbols)


def convert_record(record):
    """Lens JSON 레코드 → 엑셀 행 딕셔너리"""
    biblio = record.get("biblio", {}) or {}
    app_ref = biblio.get("application_reference", {}) or {}
    pub_ref = biblio.get("publication_reference", {}) or {}
    parties = biblio.get("parties", {}) or {}
    legal = record.get("legal_status", {}) or {}

    # 발명의 명칭: 다국어 중 첫 번째
    titles = biblio.get("invention_title", []) or []
    title = titles[0].get("text", "") if titles and isinstance(titles[0], dict) else ""

    # 요약: 다국어 중 첫 번째
    abstracts = record.get("abstract", []) or []
    abstract = abstracts[0].get("text", "") if abstracts and isinstance(abstracts[0], dict) else ""

    # 출원인
    applicants = parties.get("applicants", []) or []
    applicant_str = join_list(applicants)

    # 발명자
    inventors = parties.get("inventors", []) or []
    inventor_str = join_list(inventors)

    # IPC / CPC
    ipc_data = biblio.get("classifications_ipc", {}) or {}
    cpc_data = biblio.get("classifications_cpc", {}) or {}
    ipc_str = join_classifications(ipc_data)
    cpc_str = join_classifications(cpc_data)

    return {
        "Lens ID": record.get("lens_id", ""),
        "출원번호": safe_get(app_ref, "doc_number"),
        "출원일": safe_get(app_ref, "date"),
        "공개번호": safe_get(pub_ref, "doc_number"),
        "공개일": record.get("date_published", ""),
        "출원인": applicant_str,
        "발명자": inventor_str,
        "발명의 명칭": title,
        "요약": abstract,
        "IPC": ipc_str,
        "CPC": cpc_str,
        "출원국": record.get("country", ""),
        "문서유형": record.get("document_type", ""),
        "법적상태": safe_get(legal, "patent_status"),
        "등록여부": "Y" if safe_get(legal, "granted") is True else "N",
    }


def main():
    parser = argparse.ArgumentParser(description="Lens JSON → 엑셀 변환")
    parser.add_argument("--input", required=True, help="입력 JSON 파일 경로")
    parser.add_argument("--output", required=True, help="출력 폴더 경로")
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        raw = json.load(f)

    records = raw.get("data", [])
    if not records:
        print("[WARN] 수집된 데이터가 없습니다.", file=sys.stderr)
        sys.exit(0)

    rows = [convert_record(r) for r in records]
    df = pd.DataFrame(rows)

    os.makedirs(args.output, exist_ok=True)
    output_path = os.path.join(args.output, "lens_data.xlsx")
    df.to_excel(output_path, index=False, engine="openpyxl")

    print(f"엑셀 변환 완료: {output_path}")
    print(f"  총 {len(df):,}건 / 컬럼: {', '.join(df.columns)}")

    # 기본 통계
    if "출원국" in df.columns:
        top_countries = df["출원국"].value_counts().head(5)
        print(f"  상위 출원국: {dict(top_countries)}")
    if "출원일" in df.columns:
        dates = pd.to_datetime(df["출원일"], errors="coerce")
        valid = dates.dropna()
        if not valid.empty:
            print(f"  출원일 범위: {valid.min().strftime('%Y-%m-%d')} ~ {valid.max().strftime('%Y-%m-%d')}")


if __name__ == "__main__":
    main()
