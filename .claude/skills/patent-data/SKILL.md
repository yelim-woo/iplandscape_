---
description: Lens.org API를 활용하여 연구 주제 기반 특허 데이터를 자동 검색·수집하고, 기존 patent-trend/patent-quality 스킬에서 바로 사용할 수 있는 엑셀 파일로 변환합니다.
user-invocable: true
arguments: 연구 주제 (예: 수소자동차, CRISPR 유전자 편집)
argument-hint: [연구 주제]
---

# patent-data

Lens.org Patent API(평가판)를 사용하여 연구 주제 기반 특허 데이터를 **검색 → 수집 → 엑셀 변환**까지 자동으로 수행합니다.
생성된 엑셀은 patent-trend / patent-quality 스킬의 입력 데이터로 바로 사용할 수 있습니다.

---

## API 제약 (평가판 기준)

| 항목 | 제한 |
|------|------|
| 월간 API 요청 | 5,000건 |
| 월간 레코드 | 최대 100,000건 |
| 분당 API 요청 | 10건 |
| 요청당 레코드 | 최대 100건 |

**반드시 rate limit을 준수해야 합니다.** 분당 10건 → 요청 사이 최소 6초 대기.

---

## 사전 조건

1. **API 토큰**: 사용자에게 Lens.org API 토큰을 요청합니다.
   - 토큰이 없는 경우: https://www.lens.org/lens/user/subscriptions 에서 평가판 신청 안내
2. **Python 패키지**: `requests`, `openpyxl`, `pandas` (없으면 자동 설치)

---

## 실행 흐름

사용자가 연구 주제를 입력하면:

1. **API 토큰 확인**: 사용자에게 Lens.org API 토큰을 요청
2. **검색 쿼리 설계**: 주제를 분석하여 Elasticsearch 쿼리 생성
3. **데이터 수집**: Lens API로 scroll 방식 전체 수집
4. **엑셀 변환**: 수집 데이터를 WIPS ON 호환 형식의 엑셀로 저장
5. **결과 안내**: 저장 경로 및 다음 단계(patent-trend/patent-quality) 안내

---

## Stage 1 — API 토큰 확인

사용자에게 API 토큰을 요청합니다:

> Lens.org API 토큰을 입력해 주세요.
> (토큰이 없으시면 https://www.lens.org/lens/user/subscriptions 에서 평가판을 신청할 수 있습니다.)

토큰을 받으면 간단한 테스트 요청으로 유효성을 확인합니다.

---

## Stage 2 — 검색 쿼리 설계

### Lens.org Elasticsearch 쿼리 구조

연구 주제를 분석하여 아래 구조의 쿼리를 자동 생성합니다:

```json
{
  "query": {
    "bool": {
      "must": [
        {
          "bool": {
            "should": [
              {"match_phrase": {"title": "키워드1"}},
              {"match_phrase": {"abstract": "키워드1"}},
              {"match_phrase": {"title": "keyword1"}},
              {"match_phrase": {"abstract": "keyword1"}}
            ]
          }
        }
      ],
      "must_not": [
        {"match_phrase": {"title": "제외키워드"}},
        {"match_phrase": {"abstract": "제외키워드"}}
      ]
    }
  },
  "include": [
    "lens_id", "country", "doc_number", "kind",
    "date_published", "biblio", "abstract",
    "legal_status", "document_type"
  ],
  "size": 100,
  "scroll": "1m"
}
```

### 쿼리 설계 규칙

- **한국어 + 영어 키워드를 모두 포함** (should로 OR 결합)
- `match_phrase` 사용으로 정확도 확보, 필요시 `match`로 전환
- 제외 키워드는 `must_not`에 배치
- 날짜 범위: 기본 최근 20년, 사용자 요청 시 조정
- **include 필드를 반드시 지정**하여 불필요한 데이터 전송 최소화
- 쿼리 생성 후 사용자에게 보여주고 **확인 후 실행**

### 선택적 필터

사용자 요청에 따라 추가:

```json
{"term": {"country": "KR"}},
{"range": {"year_published": {"gte": 2015, "lte": 2025}}},
{"match": {"legal_status.granted": true}}
```

---

## Stage 3 — 데이터 수집

`${CLAUDE_SKILL_DIR}/_collect_lens.py` 스크립트를 실행합니다.

```bash
python "${CLAUDE_SKILL_DIR}/_collect_lens.py" \
  --token "사용자토큰" \
  --query '쿼리JSON문자열' \
  --output "저장경로/lens_patents.json" \
  --max-records 5000
```

### 수집 로직 핵심

1. 첫 요청으로 `total` 건수 확인 → 사용자에게 예상 건수/소요시간 안내
2. scroll 방식으로 100건씩 반복 수집
3. **분당 10건 제한 준수**: 요청 사이 7초 대기 (여유 확보)
4. 중간 진행률 표시: `수집 중... 300/1,500건 (20%)`
5. 수집 완료 시 JSON 파일로 저장

### 대량 데이터 주의사항

- 5,000건 수집 = 50회 요청 = 약 6분 소요
- 10,000건 이상이면 사용자에게 **범위 축소** 또는 **분할 수집** 제안
- 월간 100,000건 한도 경고

---

## Stage 4 — 엑셀 변환

`${CLAUDE_SKILL_DIR}/_convert_to_excel.py` 스크립트를 실행합니다.

```bash
python "${CLAUDE_SKILL_DIR}/_convert_to_excel.py" \
  --input "저장경로/lens_patents.json" \
  --output "저장경로/"
```

### 출력 엑셀 컬럼 매핑 (patent-trend/patent-quality 호환)

Lens.org JSON 응답을 아래 컬럼으로 매핑하여 엑셀을 생성합니다:

| 엑셀 컬럼 | Lens JSON 필드 | 설명 |
|-----------|----------------|------|
| 출원번호 | `biblio.application_reference.doc_number` | 출원 번호 |
| 출원일 | `biblio.application_reference.date` | 출원 날짜 |
| 출원인 | `biblio.parties.applicants[].extracted_name` | 출원인 이름 (`;` 구분) |
| 발명자 | `biblio.parties.inventors[].extracted_name` | 발명인 이름 (`;` 구분) |
| 발명의 명칭 | `biblio.invention_title[0].text` | 발명 제목 |
| 요약 | `abstract[0].text` | 초록 텍스트 |
| IPC | `biblio.classifications_ipc.classifications[].symbol` | IPC 분류 (`;` 구분) |
| CPC | `biblio.classifications_cpc.classifications[].symbol` | CPC 분류 (`;` 구분) |
| 출원국 | `country` | 국가 코드 |
| 법적상태 | `legal_status.patent_status` | 특허 상태 |
| Lens ID | `lens_id` | Lens 고유 식별자 |

### 출력 파일

- `저장경로/lens_data.xlsx` — patent-trend/patent-quality 입력용
- `저장경로/lens_raw.json` — 원본 JSON 백업

---

## 파일 저장 규칙

- 기본 저장 경로: 사용자가 지정한 경로, 없으면 `~/Desktop/주제명/`
- 예시: `~/Desktop/수소자동차/lens_data.xlsx`

---

## 실행 순서 요약

```
사용자: /patent-data 수소자동차
  │
  ├─ [1] API 토큰 확인
  ├─ [2] 검색 쿼리 설계 → 사용자 확인
  ├─ [3] Lens API 수집 (scroll, rate limit 준수)
  ├─ [4] JSON → 엑셀 변환
  └─ [5] 완료 안내
       "수소자동차 특허 2,340건을 수집했습니다.
        엑셀 파일: ~/Desktop/수소자동차/lens_data.xlsx
        → /patent-trend ~/Desktop/수소자동차 로 동향분석을 바로 시작할 수 있습니다."
```

---

## 주의사항

- API 토큰은 **대화 중에만 사용**하고 파일에 저장하지 않습니다
- rate limit 초과 시 429 응답 → 60초 대기 후 재시도 (최대 3회)
- 네트워크 오류 시 마지막 scroll_id부터 재개 가능
- `taskkill //F //IM python.exe` 절대 사용 금지
