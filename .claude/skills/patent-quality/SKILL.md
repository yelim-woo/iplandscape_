---
name: patent-quality
description: 엑셀 특허 데이터의 요약/해결과제/해결수단 텍스트를 분석하여 연도별 기술흐름도와 O/S(Object/Solution) Matrix를 생성하고, HWPX 정성분석 보고서(Quality_report.hwpx)를 출력한다.
argument-hint: [폴더경로]
---

## 특허 정성분석 HWPX 보고서 생성기

사용자가 입력한 폴더 경로(`$ARGUMENTS`)에서 특허 엑셀 파일들을 읽어, 텍스트 기반 정성분석을 수행하고 **3개 차트를 1개 장으로** 배치한 보고서(`Quality_report.hwpx`)를 생성한다.

> **분석 내용**: 요약 텍스트 기반 기술흐름도 + 해결과제/해결수단 기반 O/S Matrix (전체 + 구간별 변화)

---

### 경로

- **HWPX 양식 템플릿**: `${CLAUDE_PROJECT_DIR}/.claude/skills/patent-trend/양식.hwpx`
- **스크립트 위치**: `${CLAUDE_SKILL_DIR}/_extract_texts.py`, `${CLAUDE_SKILL_DIR}/_gen_quality_charts.py`, `${CLAUDE_SKILL_DIR}/_gen_quality_report.py`
- **대시보드 상태 파일**: `${CLAUDE_PROJECT_DIR}/.claude/skills/patent-search/dashboard/public/stage3-state.json`
- **출력**: 입력 폴더에 `Quality_report.hwpx`

---

### 사전 조건

- 입력 폴더에 `.xlsx` 파일이 1개 이상 존재
- 엑셀에 `요약` 또는 `해결과제 요약`/`해결수단 요약` 텍스트 컬럼 필요
- Python 패키지: `pandas`, `matplotlib`, `openpyxl`, `pillow`, `numpy` 설치

---

### 전체 작업 흐름 (5단계)

1. **Stage A — 텍스트 추출**: Python 스크립트가 엑셀에서 텍스트 데이터 + 연도 구간 정보 추출
2. **Stage B-1 — 카테고리 정의**: Claude가 샘플 텍스트를 읽고 기술 주제 및 O/S 카테고리를 키워드와 함께 정의
3. **Stage A2 — 분류 + 차트 렌더링**: Python 스크립트가 키워드 매칭으로 전체 특허 분류 후 차트 3개 생성
4. **Stage B-2 — 불릿 생성**: Claude가 통계 JSON을 읽고 차트별 해석 문장 작성
5. **Stage C — HWPX 조립**: Python 스크립트가 보고서 빌드

---

### Stage A. 텍스트 추출

```bash
python "${CLAUDE_SKILL_DIR}/_extract_texts.py" <폴더>
```

출력: `<폴더>/_quality_assets/`
- `extracted_texts.json` — 전체 특허의 {id, year, period, title, summary, problem, solution}
- `sample_summary.json` — 구간별 요약 텍스트 샘플 (구간당 15~20건)
- `sample_os.json` — 해결과제/해결수단 샘플 (30~40건)
- `year_info.json` — 연도 범위, 4구간 경계, 구간별 건수

---

### Stage B-1. 카테고리 정의 (Claude가 직접 수행)

Stage A 완료 후, Claude는 다음을 수행:

1. `_quality_assets/sample_summary.json` 읽기
2. `_quality_assets/sample_os.json` 읽기
3. `_quality_assets/year_info.json` 읽기

샘플 텍스트를 분석하여 아래 5가지 카테고리를 정의:

#### (1) 기술 주제 (tech_themes) — 기술흐름도용
- 5~8개 주제 정의
- 각 주제별 대표 키워드 리스트 (한국어 + 영어, 주제당 10~20개)
- 키워드는 요약 텍스트에서 매칭 가능한 핵심 기술 용어

#### (2) Object 카테고리 (object_categories) — O/S Matrix 대분류용
- 5~8개 해결과제 유형 정의
- 각 카테고리별 키워드 리스트 (한국어 + 영어, 10~15개)

#### (3) Solution 카테고리 (solution_categories) — O/S Matrix 대분류용
- 5~8개 해결수단 유형 정의
- 각 카테고리별 키워드 리스트 (한국어 + 영어, 10~15개)

#### (4) 세부 Object 카테고리 (detail_object_categories) — O/S Matrix 세부용
- 10~14개 해결과제 세부 유형 정의
- (2)의 대분류를 세분화하여 더 구체적인 기술 과제로 분류
- 각 카테고리별 키워드 리스트 (한국어 + 영어, 10~15개)

#### (5) 세부 Solution 카테고리 (detail_solution_categories) — O/S Matrix 세부용
- 10~14개 해결수단 세부 유형 정의
- (3)의 대분류를 세분화하여 더 구체적인 기술 수단으로 분류
- 각 카테고리별 키워드 리스트 (한국어 + 영어, 10~15개)

결과를 `_quality_assets/categories.json`으로 저장:

```json
{
  "tech_themes": [
    {
      "id": "T1",
      "name": "주제명 (한국어)",
      "keywords": ["키워드1", "키워드2", "keyword3", "keyword4", ...]
    }
  ],
  "object_categories": [
    {
      "id": "O1",
      "name": "카테고리명",
      "keywords": ["키워드1", "keyword2", ...]
    }
  ],
  "solution_categories": [
    {
      "id": "S1",
      "name": "카테고리명",
      "keywords": ["키워드1", "keyword2", ...]
    }
  ],
  "detail_object_categories": [
    {
      "id": "DO1",
      "name": "세부 카테고리명",
      "keywords": ["키워드1", "keyword2", ...]
    }
  ],
  "detail_solution_categories": [
    {
      "id": "DS1",
      "name": "세부 카테고리명",
      "keywords": ["키워드1", "keyword2", ...]
    }
  ]
}
```

**카테고리 정의 원칙:**
- 키워드는 **구체적인 기술 용어** 위주 (일반적인 단어 피하기)
- 한 특허가 복수 카테고리에 매칭될 수 있음 (다중 분류 허용)
- 카테고리 간 중복 키워드 최소화
- 해당 기술 분야의 핵심 개념이 빠지지 않도록 포괄적으로 정의
- 키워드에 2~3글자 이상의 단어 사용 (1글자 단어는 오매칭 위험)

---

### Stage A2. 자동 분류 + 차트 렌더링

```bash
python "${CLAUDE_SKILL_DIR}/_gen_quality_charts.py" <폴더>
```

출력: `_quality_assets/chart_q{1..5}.png` + `stats_q{1..5}.json`

**5개 차트 구성:**

| # | 제목 | 차트 타입 | 데이터 |
|---|------|-----------|--------|
| q1 | 연도별 기술흐름도 | Stacked area chart | 요약 텍스트 → 기술 주제별 연도 추이 |
| q2 | O/S Matrix 전체 현황 | Heatmap | 해결과제 × 해결수단 빈도 (대분류) |
| q3 | O/S Matrix 구간별 변화 | 2×2 subplot heatmap | 4구간별 O/S 빈도 + 성장/공백 표시 (대분류) |
| q4 | O/S Matrix 세부 전체 현황 | Heatmap | 해결과제 × 해결수단 빈도 (세부) |
| q5 | O/S Matrix 세부 구간별 변화 | 2×2 subplot heatmap | 4구간별 O/S 빈도 + 성장/공백 표시 (세부) |

차트 q3/q5의 표시 기호:
- ★ 신규 출현 (이전 구간 0 → 현 구간 >0)
- ▲ 급상승 (이전 대비 2배 이상 증가)
- △ 성장 (이전 대비 증가)

---

### Stage B-2. 불릿 본문 생성 (Claude가 직접 수행)

Stage A2 완료 후, Claude는:

1. `_quality_assets/stats_q{1..5}.json` 5개를 Read
2. 각 차트마다 **3~5개 불릿 문장** 작성
3. 문체 규칙:
   - 각 불릿은 `○ `로 시작
   - 수치를 구체적으로 인용
   - 마지막 불릿은 시사점/해석
   - 개조식 종결: `~함`, `~나타남`, `~추세를 보임`
4. 결과를 `_quality_assets/bullets_q{1..5}.json`으로 저장:

```json
{
  "chart_id": "q1",
  "subtitle": "1. 연도별 기술흐름도",
  "caption": "<그림 5-1> 연도별 기술흐름도",
  "bullets": [
    "○ ... 분석을 진행함",
    "○ ... 증가하는 추세를 보임"
  ]
}
```

**장 번호 및 그림 번호 체계:**
- Chapter 5 정성분석: q1, q2, q3, q4, q5 → 그림 5-1, 5-2, 5-3, 5-4, 5-5

---

### Stage C. HWPX 보고서 조립

```bash
python "${CLAUDE_SKILL_DIR}/_gen_quality_report.py" <폴더>
```

출력: `<폴더>/Quality_report.hwpx`

---

### 실행 순서 요약

Claude는 다음 순서로 진행한다:

```
0. 대시보드 서버 시작 (이미 떠 있으면 건너뜀)
1. 대시보드 상태 파일 저장 (stage3-state.json)
2. python _extract_texts.py <폴더>
3. sample_summary.json, sample_os.json, year_info.json 읽기
4. categories.json 작성 (Write) — tech_themes, object/solution_categories, detail_object/solution_categories 모두 포함
5. python _gen_quality_charts.py <폴더>
6. stats_q{1..5}.json 5개 읽기
7. bullets_q{1..5}.json 5개 작성 (Write)
8. python _gen_quality_report.py <폴더>
9. 최종 Quality_report.hwpx 경로 안내
10. 웹 대시보드 안내: http://localhost:$PORT/stage3
```

### 대시보드 서버 시작

분석 시작 **전에** 대시보드 서버가 떠 있는지 확인하고, 없으면 시작한다:

```bash
cd "${CLAUDE_PROJECT_DIR}/.claude/skills/patent-search/dashboard"
if [ ! -d node_modules ]; then
  npm install --silent 2>/dev/null
fi
PORT=3000
while lsof -i :$PORT >/dev/null 2>&1 || netstat -an 2>/dev/null | grep -q ":$PORT "; do
  PORT=$((PORT + 1))
done
npx next dev --hostname 0.0.0.0 --port $PORT &
```

이미 서버가 실행 중이면 (포트가 사용 중이면) 해당 포트를 그대로 사용한다.

### 대시보드 연동 (stage3-state.json)

서버 시작 후, Stage A 실행 **전에** 반드시 아래 파일을 Write로 저장한다:

경로: `${CLAUDE_PROJECT_DIR}/.claude/skills/patent-search/dashboard/public/stage3-state.json`

```json
{
  "folder": "<폴더 절대 경로>",
  "timestamp": "<ISO 8601>"
}
```

이 파일이 있으면 Stage 3 페이지(`/stage3`)가 자동으로 해당 폴더의 결과를 읽어 표시한다.
분석 진행 중에는 5초마다 자동 갱신되므로, 사용자는 페이지를 열어두면 실시간 진행 상황을 볼 수 있다.

---

### 주의사항

- **1개 장 구조**: Chapter 5 "정성분석" (5페이지)
- **mimetype 파일**: HWPX ZIP은 `mimetype`이 첫 엔트리이며 **무압축(ZIP_STORED)**이어야 함
- **문자 이스케이프**: 본문에 `<`, `>`, `&` 들어가면 XML-escape 필수
- **이미지 크기**: PNG 렌더 시 `figsize=(16,9)`, `dpi=110` (1760x990)으로 고정
- **카테고리 품질**: 키워드 정의의 품질이 분석 결과를 결정. 샘플 텍스트를 꼼꼼히 읽고 도메인에 맞는 키워드를 정의할 것
- **다중 분류**: 한 특허가 여러 카테고리에 매칭될 수 있으므로 합계가 전체 건수보다 클 수 있음
- **태그 분류**: O/S Matrix 셀 태그는 **상대 비교 (percentile)** 방식으로 분류됨:
  - 🟢 성장: 성장률(연평균 비율) 상위 25%
  - 🔵 공백: 건수 하위 25%
  - 🟡 신규: 초기 존재감(1+2구간 합계) 하위 10% + 성장률 중간 이상
  - ⚪ 무의미: 모든 구간 0건
- **세부 O/S Matrix**: `detail_object_categories`, `detail_solution_categories`로 10~14개씩 세부 분류하여 차트 q4/q5 및 대시보드 세부 탭에 자동 반영
