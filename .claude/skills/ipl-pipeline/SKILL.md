---
name: ipl-pipeline
description: 특허 엑셀 데이터(원본/유효)를 받아 IP Landscape 분석 보고서 PDF까지 end-to-end로 만드는 오케스트레이터. 원본→유효데이터 정제 → 정량분석(차트+해석) → 경쟁사 상위기업 상세 → 정성분석(기술흐름도·O/S Matrix·특허맵 등고선) → 핵심특허 선별 → 통합 PDF 보고서를 순서대로 전문 에이전트 팀에 위임해 수행한다. 사용자가 "IP landscape 분석", "특허 분석 보고서 만들어", "특허 데이터로 보고서", "특허 정량/정성분석 전체", "처음부터 끝까지 분석", "분석 보고서 PDF"를 요청하거나, 또는 후속으로 "다시 실행", "재실행", "정량분석만 다시", "경쟁사만 업데이트", "핵심특허 보완", "보고서만 다시 빌드", "이전 결과 개선"을 요청할 때 사용한다. argument로 [데이터폴더경로]와 (선택)[연구주제]를 받는다. 단순 단일 분석(차트 하나, 경쟁사만)이면 해당 개별 스킬을 직접 쓰고, 전체 파이프라인일 때 이 오케스트레이터를 쓴다.
argument-hint: [데이터폴더경로] [연구주제(선택)]
user-invocable: true
---

# ipl-pipeline — IP Landscape 분석 파이프라인 오케스트레이터

특허 엑셀 데이터를 받아 **유효데이터 정제 → 정량 → 경쟁사 → 정성 → 핵심특허 → 통합 PDF**까지 전 과정을 전문 에이전트들에게 위임해 수행한다.

## 실행 모드: 하이브리드 (서브 에이전트 기반)
- **Phase 1 데이터 정제** — 단일 서브 에이전트(data-curator)
- **Phase 2 분석** — 4개 서브 에이전트 **병렬 팬아웃**(quant / competitor / qualitative / core-patent). 모두 `유효데이터.xlsx`만 입력으로 받아 독립 실행하므로 실시간 통신이 불필요. **한 메시지에 4개 Agent 호출을 함께 넣어 포그라운드로 동시 실행**한다(산출물은 `_ipl/` 파일로 전달).
- **Phase 3 통합** — 단일 서브 에이전트(report-integrator)가 `_ipl/` 자산을 모아 PDF 빌드.

> 모든 Agent 호출은 `model: "opus"`. subagent_type은 `.claude/agents/`의 정의명을 그대로 쓴다.

> ⚠️ **`run_in_background: true`를 쓰지 말 것.** 일부 환경(예: 백그라운드 작업의 권한 프롬프트 자동 거부)에서는 백그라운드 에이전트가 Bash(파이썬 실행·패키지 설치·파일 쓰기) 권한을 못 받아 **조용히 실패**한다. 대신 **여러 Agent 호출을 한 어시스턴트 메시지에 함께 배치**하면 백그라운드 없이도 **포그라운드에서 동시 실행**되며, 권한 프롬프트도 정상적으로 노출된다(권한 거부 회피 + 병렬성 동시 확보). 환경상 동시 실행이 막히면 **순차 실행으로 폴백**해 4종을 모두 완료한다.

## 데이터 흐름 (파일 기반)
```
<폴더>/원본*.xlsx
  └─[data-curator/patent-filter]→ <폴더>/유효데이터.xlsx, _ipl/data_summary.json
        ├─[quant-analyst/patent-trend]──────→ _ipl/quant/{chart_1..10.png, interpretation.json}
        ├─[competitor-analyst/ipl-competitor]→ _ipl/competitor/{*.png, competitor.json}
        ├─[qualitative-analyst/patent-quality│ipl-contour-map]→ _ipl/qualitative/{tech_flow,os_matrix,contour_map_ipc,contour_map_tech}.png + contour_ipc/tech.json
        └─[core-patent-finder/ipl-core-patent]→ _ipl/core/{core_scores.csv, core_patents.json}
  [market-analyst/웹리서치]──(주제만, 데이터 불요)──→ _ipl/market/market.json  (기술 이해·환경분석 국내/국외)
  └─[report-integrator/ipl-report]→ _ipl/manifest.json → <폴더>/IP_Landscape_Report.pdf + .hwpx
```
중간 산출물은 모두 `<폴더>/_ipl/`에 보존(감사 추적). 최종 보고서(PDF·HWPX)만 폴더 루트.

---

## Phase 0 — 컨텍스트 확인 (항상 먼저)

`<폴더>/_ipl/` 와 `<폴더>/IP_Landscape_Report.pdf` 존재를 확인해 실행 모드를 정한다:

| 상황 | 모드 | 행동 |
|------|------|------|
| `_ipl/` 없음 | **초기 실행** | Phase 1부터 전체 수행 |
| `_ipl/` 있음 + 사용자가 "○○만 다시/업데이트/보완" | **부분 재실행** | 해당 에이전트만 재호출 후 Phase 3(재빌드) |
| `_ipl/` 있음 + 새 원본 데이터 제공 | **새 실행** | 기존 `_ipl/`을 `_ipl_prev/`로 이동 후 전체 재수행 |
| "보고서만 다시 빌드" | **재빌드만** | Phase 3만 수행 |

부분 재실행 매핑: "정량/차트"→quant-analyst, "경쟁사/출원인"→competitor-analyst, "정성/기술흐름/OS/등고선/White Space"→qualitative-analyst, "핵심특허/가중치"→core-patent-finder, "보고서/PDF"→report-integrator.

연구주제가 인자에 없고 초기 실행이면, 데이터 정제·핵심특허 의미판단·해석 품질을 위해 **연구주제 한 줄을 사용자에게 묻는다**(필수는 아니지만 권장).

---

## Phase 1 — 데이터 정제

`유효데이터.xlsx`가 이미 있고 사용자가 데이터 변경을 요청하지 않았으면 **건너뛴다**(기존 파일 사용).

그 외에는 data-curator를 호출한다:
```
Agent(subagent_type="data-curator", model="opus",
  prompt="<폴더>의 원본 특허 엑셀을 patent-filter 스킬로 2단계 필터링해 유효데이터.xlsx를 만들고,
          _ipl/data_summary.json(raw/valid/excluded 건수, year_range, exclude_reasons, criteria_path)을 기록하라.
          연구주제: <주제>. 선정기준 파일이 없으면 초안을 만들어 사용자 승인을 받아라.")
```
유효특허 0건이면 중단하고 사용자에게 사유 보고.

---

## Phase 2 — 분석 (5종 포그라운드 동시 실행)

data-curator 완료 후, 아래 5개 Agent 호출을 **하나의 어시스턴트 메시지에 함께 넣어 포그라운드로 동시 실행**한다(`run_in_background`는 쓰지 않는다 — 위 ⚠️ 참조). 특허분석 4종은 `유효데이터.xlsx`를, market-analyst는 **연구주제만** 입력으로 받는다.

```
# ↓ 5개를 한 메시지에 함께 호출(동시 실행). run_in_background 미사용.
Agent(subagent_type="quant-analyst",       model="opus", prompt="<폴더>에서 patent-trend Stage A로 차트10 생성 후 _ipl/quant/에 복사하고 stats를 읽어 차트별 해석 interpretation.json 작성")
Agent(subagent_type="competitor-analyst",  model="opus", prompt="<폴더>에서 ipl-competitor로 상위 출원인 차트(점유율/추이/IPC/기술흐름도/O/S Matrix) + competitor.json 생성 후 기업별 positioning·profile(요지·권리범위·대응전략) 해석 작성")
Agent(subagent_type="qualitative-analyst", model="opus", prompt="<폴더>에서 patent-quality로 기술흐름도+O/S Matrix, ipl-contour-map으로 특허맵 등고선 2종(--mode ipc, --mode keyword) 생성 후 qualitative(contour_ipc/contour_tech)에 해석 작성. 연구주제: <주제>")
Agent(subagent_type="core-patent-finder",  model="opus", prompt="<폴더>에서 ipl-core-patent로 정량 스코어링 후 상위 후보 명세서를 검토해 core_patents.json 확정(각 reason 기재). 연구주제: <주제>")
Agent(subagent_type="market-analyst",      model="opus", prompt="연구주제 <주제>로 웹 리서치(최근 뉴스·동향)를 수행해 기술 이해 + 환경분석 국내/국외를 <폴더>/_ipl/market/market.json으로 작성. 입력 특허데이터와 별개의 주제 기반 시장 환경 분석(보고서 '기술·시장 분석' 장, 분석 개요 앞에 배치)")
```

> 환경상 동시 실행이 막히거나 한 에이전트가 권한/오류로 실패하면 **순차(하나씩) 실행으로 폴백**해 모두 완료한다. 백그라운드로 우회하지 않는다.
> **market-analyst**는 유효데이터에 의존하지 않으므로(주제만 필요) 위 4종과 독립이다. 연구주제가 없으면 이 에이전트만 건너뛴다(시장 분석 장은 선택). 웹 접근이 막히면 최소 tech_overview만 남기고 진행.

**조율 규칙:**
- 5개 모두 완료될 때까지 대기(파일 산출 확인). 한 에이전트가 실패해도 나머지는 진행하고, 실패분은 순차로 이어서 완료한다.
- 각 에이전트가 자기 산출물을 `_ipl/<영역>/`에 쓰는지 확인. 누락 시 1회 재시도.
- competitor의 "대표특허"와 core의 "핵심특허"가 어긋나면 report-integrator가 종합 시 정합성을 맞춘다.

---

## Phase 3 — 통합 보고서 (PDF + HWPX)

모든(혹은 가용한) 분석 완료 후 report-integrator를 호출한다:
```
Agent(subagent_type="report-integrator", model="opus",
  prompt="<폴더>/_ipl/의 market/data_summary/quant/competitor/qualitative/core 산출물을 manifest.json으로 조립하고,
          분석을 종합한 Executive Summary를 직접 작성하라. market/market.json이 있으면 manifest의 'market' 키로 실어
          '기술·시장 분석' 장(분석 개요 앞)이 렌더되게 하라. ipl-report 스킬로 IP_Landscape_Report.pdf와
          IP_Landscape_Report.hwpx를 **둘 다** 빌드하라(같은 manifest.json 공유 — _build_pdf.py + _build_hwpx.py).
          수행 안 된 분석은 '미수행'으로 표기하고 채우지 말 것. 메타: 제목/연구주제<주제>/분석일/출처.")
```
완료 후 사용자에게 **PDF·HWPX 경로 + 포함/누락 섹션 + 핵심 발견 3줄**을 보고한다.

---

## 에러 핸들링
- **1회 재시도 원칙**: 에이전트/스크립트 실패 시 1회 재시도, 재실패하면 해당 산출물 없이 진행하고 보고서에 누락을 명시한다.
- **데이터 컬럼 결측**: 분석별로 데이터 없음 처리(경쟁사=출원인 없음, 등고선=IPC 없음, 정량=해당 차트 누락, 핵심특허=정량지표 전무 시 AI 100%). 임의 생성 금지.
- **상충 데이터**: 삭제하지 않고 출처를 병기한다.
- **전체 실패 금지**: Phase 2의 일부가 실패해도 성공한 분석 + 데이터 개요만으로 PDF·HWPX를 완성한다.
- **HWPX 빌드 실패 격리**: HWPX 빌드(_build_hwpx.py)가 실패해도 PDF는 정상 산출하고, HWPX 누락만 보고한다(반대도 동일). 둘은 독립 산출물이다.

## 테스트 시나리오
**정상 흐름:** `유효데이터.xlsx`(출원인·IPC·출원일·텍스트 보유) 폴더 입력 → 4종 분석 모두 산출 → 표지+요약+5장 PDF·HWPX 생성. 검증: `IP_Landscape_Report.pdf`·`IP_Landscape_Report.hwpx` 존재, `_ipl/` 하위 quant/competitor/qualitative/core 폴더 모두 채워짐, manifest.json 유효.

**에러 흐름:** IPC 컬럼이 없는 데이터 입력 → 등고선은 `contour_ipc.json`/`contour_tech.json`에 error 기록·정성장 일부 누락 → 나머지 3종은 정상 → PDF의 4장에 "특허맵 미수행(IPC 컬럼 없음)" 표기, 보고서는 정상 완성. 검증: PDF 생성 성공 + 누락 명시 존재.
