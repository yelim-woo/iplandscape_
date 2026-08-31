"""
Lens.org Patent API 수집 스크립트
- scroll 방식으로 대량 데이터 수집
- 평가판 rate limit 준수 (분당 10건, 요청당 100건)
"""

import argparse
import json
import sys
import time

import requests

API_URL = "https://pmr-beta.api.lens.org/patent/search"
REQUEST_DELAY = 7  # 분당 10건 제한 → 7초 간격 (여유 포함)
MAX_PER_REQUEST = 100
MAX_RETRIES = 3
RETRY_WAIT = 60  # 429 응답 시 대기 시간


def make_request(payload, token, attempt=1):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    try:
        resp = requests.post(API_URL, json=payload, headers=headers, timeout=30)
    except requests.exceptions.RequestException as e:
        print(f"  [ERROR] 네트워크 오류: {e}", file=sys.stderr)
        if attempt < MAX_RETRIES:
            print(f"  {RETRY_WAIT}초 후 재시도 ({attempt}/{MAX_RETRIES})...", file=sys.stderr)
            time.sleep(RETRY_WAIT)
            return make_request(payload, token, attempt + 1)
        raise

    if resp.status_code == 429:
        if attempt < MAX_RETRIES:
            print(f"  [WARN] Rate limit 초과. {RETRY_WAIT}초 대기 후 재시도...", file=sys.stderr)
            time.sleep(RETRY_WAIT)
            return make_request(payload, token, attempt + 1)
        print("[ERROR] Rate limit 재시도 횟수 초과", file=sys.stderr)
        sys.exit(1)

    if resp.status_code == 401:
        print("[ERROR] API 토큰이 유효하지 않습니다.", file=sys.stderr)
        sys.exit(1)

    if resp.status_code != 200:
        print(f"[ERROR] API 응답 오류 (HTTP {resp.status_code}): {resp.text[:500]}", file=sys.stderr)
        sys.exit(1)

    return resp.json()


def collect(query_dict, token, max_records):
    # 첫 요청: total 확인
    payload = {**query_dict, "size": MAX_PER_REQUEST, "scroll": "1m"}
    data = make_request(payload, token)

    total = data.get("total", 0)
    target = min(total, max_records)
    print(f"총 검색 결과: {total:,}건 / 수집 목표: {target:,}건")

    all_records = data.get("data", [])
    scroll_id = data.get("scroll_id")
    collected = len(all_records)
    request_count = 1

    print(f"  수집 중... {collected:,}/{target:,}건 ({collected*100//max(target,1)}%)")

    while scroll_id and collected < target:
        time.sleep(REQUEST_DELAY)

        payload = {"scroll_id": scroll_id, "scroll": "1m"}
        data = make_request(payload, token)

        batch = data.get("data", [])
        if not batch:
            break

        all_records.extend(batch)
        scroll_id = data.get("scroll_id")
        collected = len(all_records)
        request_count += 1

        print(f"  수집 중... {collected:,}/{target:,}건 ({collected*100//max(target,1)}%) [요청 {request_count}회]")

    # max_records 초과분 제거
    all_records = all_records[:max_records]
    print(f"수집 완료: {len(all_records):,}건 (API 요청 {request_count}회)")
    return all_records, total


def main():
    parser = argparse.ArgumentParser(description="Lens.org Patent API 수집")
    parser.add_argument("--token", required=True, help="Lens.org API 토큰")
    parser.add_argument("--query", required=True, help="검색 쿼리 JSON 문자열")
    parser.add_argument("--output", required=True, help="출력 JSON 파일 경로")
    parser.add_argument("--max-records", type=int, default=5000, help="최대 수집 건수")
    args = parser.parse_args()

    query_dict = json.loads(args.query)
    records, total = collect(query_dict, args.token, args.max_records)

    result = {
        "total_found": total,
        "total_collected": len(records),
        "data": records,
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"저장 완료: {args.output}")


if __name__ == "__main__":
    main()
