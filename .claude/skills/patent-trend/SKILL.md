---
name: patent-trend
description: 엑셀 특허 데이터(WIPS, KIPRIS, USPTO, Espacenet 등 어떤 DB든)가 있는 폴더 경로를 받아, 양식.hwpx 템플릿에 맞춰 10개 분석 차트를 2개 장(출원동향 분석 + 출원인 분석)으로 배치한 HWPX 보고서(Trend_report.hwpx)를 생성한다.
argument-hint: [폴더경로]
---

## 특허 동향분석 HWPX 보고서 생성기 (Stage 2)

사용자가 입력한 폴더 경로(`$ARGUMENTS`)에서 특허 엑셀 파일들을 읽어, 지정된 HWPX 양식에 맞춰 **10개 차트를 2개 장으로** 배치한 보고서(`Trend_report.hwpx`)를 생성한다.

> **데이터 소스 제한 없음**: WIPS, KIPRIS, USPTO, Espacenet, Orbit 등 어떤 특허 DB의 엑셀이든 사용 가능. 컬럼 자동 매핑(별칭 + 데이터 패턴 감지)이 내장되어 있으며, 그래도 매핑이 안 되면 Claude가 직접 매핑을 판단한다.

---

### 경로

- **HWPX 양식 템플릿**: `${CLAUDE_SKILL_DIR}/양식.hwpx`
- **스크립트 위치**: `${CLAUDE_SKILL_DIR}/_gen_report_stage_a.py`, `${CLAUDE_SKILL_DIR}/_gen_report_stage_c.py`
- **대시보드 상태 파일**: `${CLAUDE_PROJECT_DIR}/.claude/skills/patent-search/dashboard/public/stage2-state.json`
- **출력**: 입력 폴더에 `Trend_report.hwpx`

---

### 사전 조건

- 입력 폴더에 `.xlsx` 파일이 1개 이상 존재
- 어떤 특허 DB의 엑셀이든 사용 가능 (WIPS, KIPRIS, USPTO, Espacenet, Orbit 등)
- Python 패키지: `pandas`, `matplotlib`, `openpyxl`, `pillow`, `numpy` 설치

---

### 전체 작업 흐름 (3+1단계)

0. **Stage 0 -- 컬럼 매핑 확인 (비표준 데이터일 때만)**: Claude가 엑셀 헤더를 확인하고, 자동 매핑이 안 되는 컬럼이 있으면 `column_map.json`을 작성
1. **Stage A -- 데이터 집계 + 차트 PNG 렌더링**: Python 스크립트가 10개 PNG + 10개 JSON 통계 파일 생성
2. **Stage B -- 불릿 본문 생성**: Claude(본 대화)가 각 차트의 JSON 통계를 읽고 양식의 `○` 스타일로 3~5개 불릿 문장 작성
3. **Stage C -- HWPX 조립**: Python 스크립트가 양식.hwpx를 템플릿으로 2개 장 헤더가 포함된 Trend_report.hwpx 빌드

---

### Stage 0. 컬럼 매핑 확인 (비표준 데이터일 때만)

스크립트에는 3단계 자동 매핑이 내장되어 있다:

1. **정확 매칭** — WIPS 표준 컬럼명(`출원일`, `국가코드`, `출원인`, `Current IPC Main` 등)이 그대로 있으면 즉시 사용
2. **별칭 매핑** — 흔한 대체 컬럼명 자동 인식 (예: `Filing Date`→`출원일`, `Applicant`→`출원인`, `IPC`→`Current IPC Main`, `Country`→`국가코드` 등 50+ 별칭)
3. **패턴 감지** — 별칭에도 없는 컬럼은 샘플 데이터 패턴으로 추론:
   - 날짜 패턴(YYYYMMDD) → 출원일 (출원 관련 키워드가 있는 컬럼 우선)
   - 2글자 국가코드(KR/US/JP...) → 국가코드
   - IPC 패턴(A01B, H04L...) → IPC
   - 등록번호 패턴(7자리+ 숫자) → 등록번호

**Claude의 역할**: Stage A 실행 전, 엑셀 파일 하나를 Read하여 컬럼명을 확인한다.

- **WIPS 표준 컬럼** → 바로 Stage A 실행 (매핑 불필요)
- **별칭/패턴으로 매핑 가능** → 바로 Stage A 실행 (스크립트가 자동 처리)
- **자동 매핑 불가능한 컬럼 존재** → `column_map.json` 작성 후 `--column-map` 옵션으로 전달

`column_map.json` 형식:
```json
{
  "원본컬럼명1": "출원일",
  "원본컬럼명2": "출원인",
  "원본컬럼명3": "국가코드"
}
```

---

### Stage A. 데이터 집계 + PNG 렌더링

```bash
python "${CLAUDE_SKILL_DIR}/_gen_report_stage_a.py" <폴더>
```
명시적 매핑 필요 시:
```bash
python "${CLAUDE_SKILL_DIR}/_gen_report_stage_a.py" <폴더> --column-map column_map.json
```

출력: `<폴더>/_report_assets/chart_{1..10}.png` + `stats_{1..10}.json`

**10개 차트 구성:**

**Chapter 3. 출원동향 분석 (차트 1~4, 6~7)**

| N | 제목 | 차트 타입 |
|---|------|-----------|
| 1 | 주요 국가별 연도별 출원동향 | 국가별 누적 바 + 합계 라인 오버레이 |
| 2 | 국가별 특허 점유 현황 | 도넛 차트 (전체 기간 국가 비율) |
| 3 | IPC 기술 분야 분포 Top 10 | 수평 바차트 (상위 10 서브클래스, 그라디언트) |
| 4 | 주요 IPC 연도별 동향 | 라인차트 (상위 5 IPC의 연도 추이, area fill) |
| 6 | 국가별 등록률 분석 | 그룹 바차트 (국가별 출원/등록 + 등록률 %) |
| 7 | 기술 성장단계 (S-curve) | 누적 라인 + 4단계 색상 밴드 (도입/성장/성숙/쇠퇴) |

**Chapter 4. 출원인 분석 (차트 5, 8~10)**

| N | 제목 | 차트 타입 |
|---|------|-----------|
| 5 | 주요 출원인 Top 15 | 수평 바차트 (국가 색상 코딩) |
| 8 | 출원인 연도별 활동 추이 | 라인차트 (Top 5 출원인의 연도 추이) |
| 9 | 출원인-국가 히트맵 | 히트맵 (Top 10 출원인 x 4개국) |
| 10 | 출원인 유형 분포 | 도넛 차트 (기업/대학/연구기관/개인) |

---

### Stage B. 불릿 본문 생성 (Claude가 직접 수행)

Stage A 스크립트 실행 후, Claude는 다음을 수행:

1. `_report_assets/stats_{1..10}.json` 을 모두 Read
2. 각 차트마다 **3~5개 불릿 문장** 작성
3. 양식의 문체를 따름:
   - 각 불릿은 `○ ` 로 시작
   - 수치를 구체적으로 인용 (`한국(KIPO) 223건(20%)` 형식)
   - 마지막 불릿은 시사점/해석
   - 존댓말 아닌 개조식 `~함`, `~나타남`, `~추세를 보임` 종결
4. 결과를 `_report_assets/bullets_{N}.json` 으로 저장:

```json
{
  "chart_id": 1,
  "subtitle": "1. 주요 국가별 연도별 출원동향",
  "caption": "<그림 3-1> 주요 출원국 연도별 특허동향",
  "bullets": [
    "○ ... 통계분석을 진행함",
    "○ ... 증가하는 추세를 보임",
    "○ ..."
  ]
}
```

장 번호 및 그림 번호 체계:
- Chapter 3 출원동향 분석: 차트 1,2,3,4,6,7 → 그림 3-1 ~ 3-6
- Chapter 4 출원인 분석: 차트 5,8,9,10 → 그림 4-1 ~ 4-4

---

### Stage C. HWPX 보고서 조립

```bash
export HWPX_TEMPLATE="${CLAUDE_SKILL_DIR}/양식.hwpx"
python "${CLAUDE_SKILL_DIR}/_gen_report_stage_c.py" <폴더>
```

출력: `<폴더>/Trend_report.hwpx`

---

### 실행 순서 요약

Claude는 다음 순서로 진행한다:

```
0. 대시보드 서버 시작 (이미 떠 있으면 건너뜀)
1. (비표준 데이터인 경우) 엑셀 파일 하나 Read → column_map.json 작성
2. 대시보드 상태 파일 저장 (stage2-state.json)
3. python _gen_report_stage_a.py <폴더>
4. stats_{1..10}.json 10개를 Read
5. bullets_{1..10}.json 10개 Write
6. HWPX_TEMPLATE 환경변수 설정 후 python _gen_report_stage_c.py <폴더>
7. 최종 Trend_report.hwpx 경로 안내
8. 웹 대시보드 안내: http://localhost:$PORT/stage2
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

### 대시보드 연동 (stage2-state.json)

서버 시작 후, Stage A 실행 **전에** 반드시 아래 파일을 Write로 저장한다:

경로: `${CLAUDE_PROJECT_DIR}/.claude/skills/patent-search/dashboard/public/stage2-state.json`

```json
{
  "folder": "<폴더 절대 경로>",
  "timestamp": "<ISO 8601>"
}
```

이 파일이 있으면 Stage 2 페이지(`/stage2`)가 자동으로 해당 폴더의 결과를 읽어 표시한다.
분석 진행 중에는 5초마다 자동 갱신되므로, 사용자는 페이지를 열어두면 실시간 진행 상황을 볼 수 있다.

---

### 주의사항

- **2개 장 구조**: Chapter 3 "출원동향 분석" (6페이지) + Chapter 4 "출원인 분석" (4페이지)
- **mimetype 파일**: HWPX ZIP은 `mimetype` 이 첫 엔트리이며 **무압축(ZIP_STORED)** 이어야 함
- **문자 이스케이프**: 본문에 `<`, `>`, `&` 들어가면 XML-escape 필수
- **이미지 크기**: PNG 렌더 시 `figsize=(16,9)`, `dpi=110` (1760x990) 으로 고정
- **페이지 분리**: `pageBreak="1"` 속성으로 각 차트 페이지 분리
- **에러 내성**: 각 차트 렌더링은 try/except로 감싸여 있어 한 차트 실패가 전체를 중단시키지 않음
