---
name: ipl-competitor
description: 유효특허 엑셀에서 상위 출원인(경쟁사)을 식별하고 기업별 상세 분석을 만든다. 점유율·연도별 추이·IPC 기술포커스 차트 3종을 렌더링하고, 기업별 프로파일(기술 집중영역·출원 모멘텀·포지셔닝·대표특허) 골격을 만든 뒤 Claude가 해석을 채운다. 사용자가 "경쟁사 분석", "상위 출원인/기업별 상세", "주요 플레이어 분석", "경쟁 구도", "출원인 포지셔닝"을 요청하거나 IP Landscape 보고서의 경쟁사 장을 만들 때 사용한다. argument로 [유효데이터폴더경로]를 받는다.
argument-hint: [유효데이터폴더경로]
user-invocable: true
---

# ipl-competitor — 경쟁사 상위 기업별 상세 분석

유효특허 데이터에서 상위 출원인을 식별하고, **단순 점유율을 넘어 기업별로 "무엇에 집중하고 어떻게 움직이는가"**를 분석한다. 통합 PDF 보고서의 경쟁사 장(3장)에 들어간다.

## 경로
- 스크립트: `${CLAUDE_SKILL_DIR}/scripts/_competitor.py`, `${CLAUDE_SKILL_DIR}/scripts/_ipl_io.py`
- 출력: `<폴더>/_ipl/competitor/`

## 사전 조건
- `<폴더>`에 `유효데이터.xlsx`(또는 분석용 xlsx) 존재. 출원인 컬럼 필수, 출원일·IPC 컬럼 권장.
- Python: `pandas numpy matplotlib openpyxl pillow` (스크립트가 자동 설치)

## 작업 흐름 (2단계)

### Stage A — 집계 + 차트 (Python)
```bash
cd "${CLAUDE_SKILL_DIR}/scripts" && python _competitor.py "<폴더>" --top 8
```
산출물(`<폴더>/_ipl/competitor/`):
- `comp_share.png` 점유율, `comp_trend.png` 상위사 연도별 추이, `comp_ipc.png` 상위사×IPC 섹션 히트맵
- `competitor.json` — 기업별 골격 `{rank, name, count, share, focus_ipc, momentum, positioning:"", profile:[], rep_patents}`
- `_stats.json` — 추이·포커스 원자료

> 출원인 표기는 스크립트가 1차 정규화(법인 접미 제거, 첫 출원인 추출)한다. 동일 기업의 한/영 표기나 합병 변형이 여전히 분리돼 보이면 Claude가 `competitor.json`에서 수동 병합한다.

### Stage A-2 — 상위 출원인 기술흐름도 + O/S Matrix (Python)
```bash
cd "${CLAUDE_SKILL_DIR}/scripts" && python _competitor_quality.py "<폴더>" --top 8
```
- `comp_techflow.png` — 상위 출원인 patents의 IPC 서브클래스 구성을 연도 3구간으로 적층(기술 진화).
- `comp_osmatrix.png` — 해결과제(Object)×해결수단(Solution) 히트맵. 카테고리는 `<폴더>/_ipl/competitor/os_categories.json`(없으면 내장 EV 기본값). **도메인이 EV/배터리가 아니면** Claude가 샘플 초록을 보고 `os_categories.json`(`{object:[[라벨,[키워드…]]…], solution:[…]}`)을 새로 정의해 둔다.
- `comp_quality.json` — techflow 행렬 + osmatrix 집중/공백 셀.
보고서에는 이 둘을 점유율·추이·IPC 포커스에 이어 추가 차트로 싣는다(`competitor.json.charts.techflow/osmatrix` + `chart_interp`).

### Stage B — 기업별 해석 작성 (Claude가 직접)
`competitor.json`을 읽고, 각 기업의 `_stats.json` 수치를 근거로 다음을 채운다:
- `positioning`: 선도 / 추격 / 틈새 / 신규진입 중 하나 — 점유율·모멘텀·기술폭으로 판단
- `profile`: 2~4개 불릿. 각 불릿은 **기업마다 달라야 한다.** 기술 포커스(어떤 IPC에 몰림), 출원 모멘텀(언제 늘고 줄었는지 연도), 경쟁 위치를 수치로 서술. 막연한 칭찬 금지.

**해석 깊이 기준:** "A사는 1위"가 아니라 "A사는 H01M(이차전지)에 출원의 60%를 집중하며 2020년 이후 출원이 2배로 늘어 이 영역의 선도 포지션을 굳히는 중"처럼 (집중영역 + 변화 + 의미)를 담는다.

**기업별 심층 분석(권장):** 각 기업의 `profile`(라벨형 `{l,t}`)에 규모·순위/기술 포커스/모멘텀에 더해 대표특허 기반 3종을 넣는다 — `핵심특허`(번호·제목·피인용·패밀리), `요지 분석`(`rep_patents[0].abstract`를 읽고 무엇을 청구하는지), `권리범위 분석`(기술/지역 범위 — 패밀리 폭=지역, IPC=기술축, 청구항 텍스트가 없으면 초록·패밀리로 추정하고 그 한계를 밝힘), `대응 전략`(회피설계 방향·라이선스·무효 가능성·주의도). 이 부분이 경쟁사 장의 핵심 부가가치다.

채운 결과를 `competitor.json`에 다시 쓴다.

## 데이터 없음 처리
출원인 컬럼이 없으면 `competitor.json`에 `error`가 기록된다. 이때 경쟁사 장을 "데이터 없음"으로 보고하고 임의 생성하지 않는다.
