# IP Landscape Workbench

**특허 데이터 수집을 위한 검색식 설계 & IP Landscape 분석 보고서(PDF, 한글 HWPX)까지 자동화하는 Claude Code 하네스**

특허 검색식 설계, 유효데이터 정제, 정량·정성·경쟁사·핵심특허 분석, 통합 보고서 생성을 하나의 워크벤치에서 수행합니다. Next.js 기반 검색 대시보드와, Claude Code 전문 에이전트·스킬로 구성된 분석 파이프라인이 결합되어 있습니다.

> ⚠️ **데이터 수집은 Claude가 하지 않습니다.** 특허 데이터 **수집**은 사용자가 **KIPRIS 등에서 직접 검색해 엑셀을 내려받거나(수동)**, **Power Automate로 자동 수집**하는 별도 단계입니다. Claude는 그 앞뒤 단계 — **검색식 설계**와 **수집된 데이터의 정제·분석·보고서 생성** — 를 담당합니다.

> 📖 **사용 매뉴얼:** https://iplandscape.vercel.app/
> 처음 사용하신다면 매뉴얼의 STEP 1~5를 따라 진행하시는 것을 권장합니다.

---

## 목차

- [무엇을 하나요](#무엇을-하나요)
- [전체 워크플로우](#전체-워크플로우)
- [빠른 시작](#빠른-시작)
- [분석 파이프라인 상세](#분석-파이프라인-상세)
- [입력 데이터 · 출력물](#입력-데이터--출력물)
- [프로젝트 구조](#프로젝트-구조)
- [요구 사항](#요구-사항)

---

## 무엇을 하나요

IP Landscape Workbench는 **특허 분석 실무 전 과정**을 지원합니다. 아래 표에서 **데이터 수집만 사용자가 직접(수동/Power Automate) 수행**하고, 나머지 단계를 Claude가 담당합니다.

| 단계 | 수행 주체 | 하는 일 | 산출물 |
|------|:---:|---------|--------|
| **검색식 설계** | 🤖 Claude | 연구주제를 입력하면 AI가 분류체계·키워드·IPC·검색식을 자동 설계 (WIPS / Lens / KIPRIS) | 검색식 JSON, 편집 대시보드 |
| **데이터 수집** | 🧑 사용자 | 설계된 검색식으로 KIPRIS 등에서 **직접 검색해 엑셀 다운로드(수동)** 또는 **Power Automate로 자동 수집** | 원본 특허 엑셀 |
| **IP Landscape 분석 & 보고서** | 🤖 Claude | 데이터 폴더 경로 + 요청 한 번으로 아래 전 과정을 자동 수행:<br>• **유효데이터 정제** — 법적상태·출원일 기계 필터 + 선정기준 의미판정<br>• **정량 분석** — 출원 동향·국가·IPC·출원인 차트 10종 + 해석<br>• **경쟁사 분석** — 상위 출원인 식별, 기업별 포지셔닝·기술포커스·대표특허<br>• **정성 분석** — 기술흐름도, O/S(목적×수단) Matrix, 특허맵 등고선(White Space 발굴)<br>• **핵심특허 선별** — 인용·패밀리·청구항 정량 스코어링 + 명세서 의미검토<br>• **시장 환경 분석** — 웹 리서치로 기술 이해 + 국내/국외 최근 동향<br>• **통합 보고서** — 위 결과를 표지·요약·5개 장으로 조립 | `유효데이터.xlsx` · 차트 PNG · `IP_Landscape_Report.pdf` · `.hwpx` |

---

## 전체 워크플로우

매뉴얼의 5단계 흐름과 대응합니다. **②번(데이터 수집)만 사용자가 직접 수행**하고, 나머지는 Claude Code에서 진행합니다.

```
① 검색식 설계        🤖 Claude   Claude Code에서 /patent-search "연구주제"
   (STEP 1~2)                   → 대시보드(localhost:3000/stage1)에서 검색식 확인·편집

② 데이터 수집        🧑 사용자   ★ 이 단계는 Claude가 하지 않습니다 ★
   (STEP 3)                     (자동) Power Automate로 KIPRIS 국가별 특허 자동 수집·폴더 생성
                                (수동) KIPRIS 등에서 직접 검색 → 엑셀 다운로드 → 폴더에 저장

③ 분석 & 보고서      🤖 Claude   Claude Code에 데이터 폴더 경로 뒤에
   (STEP 4~5)                    "IP Landscape 분석 보고서 만들어줘" 를 붙여 Enter
                                예) C:\경로\특허데이터폴더 IP Landscape 분석 보고서 만들어줘

                                → 유효데이터 정제 → 정량·경쟁사·정성·핵심특허·시장 분석
                                  → IP_Landscape_Report.pdf + IP_Landscape_Report.hwpx 자동 생성
```

> 💡 **`localhost:3000/stage1` 화면이 안 열릴 때:** 검색·수집 화면은 Claude Code 작업 창과 함께 동작합니다. 작업 창을 닫으면 화면도 닫힙니다. 다시 열려면 Claude 대화창에 `npm run dev` 실행 후 `localhost:3000/stage1` 로 접속하세요.

---

## 빠른 시작

이 프로젝트는 **Claude Code 하네스**입니다. Claude Code에서 슬래시 커맨드(스킬)로 실행합니다.

### 1) 검색식 설계 + 데이터 수집
```
/patent-search 로보틱스
```
- AI가 검색식을 설계하고 웹 대시보드를 띄웁니다.
- 주제 앞에 `<특허DB>` 를 붙이면 **수집하려는 특허 DB의 검색 신택스에 맞춰** 검색식을 작성해 줍니다.
  - `<kipris>` — KIPRIS (국문 위주)
  - `<lens>` — Lens.org (영문 위주)
  - 생략 시 기본값은 WIPS ON 신택스
  - 예: `/patent-search <kipris> 이차전지 양극재`
- 완성된 검색식을 복사해 해당 DB(KIPRIS/WIPS/Lens 등)에서 검색한 뒤, 결과 엑셀을 한 폴더에 모읍니다.

### 2) 전체 분석 → 보고서
수집한 특허 엑셀을 한 폴더에 모은 뒤, Claude Code에 **폴더 경로 + 요청 문장**을 입력하고 Enter만 누르면 됩니다.
```
C:\경로\특허데이터폴더 IP Landscape 분석 보고서 만들어줘
```
- 유효데이터 정제 → 정량·경쟁사·정성·핵심특허·시장 분석 → 통합 보고서까지 자동으로 진행됩니다.
- 원본 엑셀이 있으면 정제부터, `유효데이터.xlsx`가 이미 있으면 분석부터 진행합니다.
- 완료 시 폴더 루트에 `IP_Landscape_Report.pdf` 와 `.hwpx` 가 생성됩니다.

### 부분 재실행
이미 한 번 분석한 폴더면, 이어서 자연어로 필요한 부분만 다시 요청할 수 있습니다.
```
정량분석만 다시 해줘  /  경쟁사만 업데이트해줘  /  보고서만 다시 빌드해줘
```

---

## 분석 파이프라인 상세

`ipl-pipeline` 오케스트레이터가 전문 에이전트 팀에 작업을 위임합니다.

```
<폴더>/원본*.xlsx
  └─ data-curator ──────────→ 유효데이터.xlsx, _ipl/data_summary.json
        ├─ quant-analyst ────→ _ipl/quant/       (차트10 + 해석)
        ├─ competitor-analyst → _ipl/competitor/  (점유율·추이·IPC·기술흐름·O/S)
        ├─ qualitative-analyst → _ipl/qualitative/ (기술흐름도·O/S Matrix·등고선 2종)
        └─ core-patent-finder → _ipl/core/        (핵심특허 스코어링·의미검토)
  market-analyst (주제만) ────→ _ipl/market/       (기술 이해·국내/국외 동향)
        └─ report-integrator → _ipl/manifest.json → IP_Landscape_Report.{pdf,hwpx}
```

- **Phase 1 정제** → **Phase 2 분석(5종 병렬)** → **Phase 3 통합**의 3단계로 실행됩니다.
- 모든 중간 산출물은 `<폴더>/_ipl/` 에 보존되어 감사 추적이 가능합니다.
- 일부 분석이 실패해도 성공한 결과만으로 보고서를 완성하고, 누락은 명시합니다.

---

## 입력 데이터 · 출력물

**입력:** WIPS · KIPRIS · Lens.org · USPTO · Espacenet 등 어떤 특허 DB의 엑셀이든 지원합니다. (강건한 엑셀 리더가 헤더행 자동 탐지, 국내/해외 스키마 정합, 손상 스타일시트 폴백을 처리합니다.)

**출력:**
- `IP_Landscape_Report.pdf` — 표지 → Executive Summary → 5개 장으로 구성된 통합 보고서
- `IP_Landscape_Report.hwpx` — 동일 내용의 한글(HWPX) 보고서
- `_ipl/` — 차트 PNG, 통계 JSON, 해석 등 모든 중간 산출물

---

## 프로젝트 구조

```
.
├── CLAUDE.md                  프로젝트 지침 · 변경 이력
├── .claude/
│   ├── agents/                분석 전문 에이전트 7종 (data-curator, quant-analyst 등)
│   ├── settings.json          공유 권한 설정
│   └── skills/                Claude Code 스킬
│       ├── ipl-pipeline/      전체 파이프라인 오케스트레이터
│       ├── ipl-competitor/    경쟁사 분석
│       ├── ipl-contour-map/   특허맵 등고선 · O/S Matrix
│       ├── ipl-core-patent/   핵심특허 선별
│       ├── ipl-report/        통합 보고서 빌더 (PDF · HWPX)
│       ├── patent-filter/     유효데이터 정제
│       ├── patent-trend/      정량 분석 차트
│       ├── patent-quality/    정성 분석 (기술흐름 · O/S)
│       ├── patent-data/       Lens.org API 수집
│       └── patent-search/     검색식 설계 + 웹 대시보드 (Next.js)
```

---

## 요구 사항

- **Claude Code** (에이전트·스킬 실행 환경)
- **Python 3** — 분석 스크립트 (`pandas`, `matplotlib`, `reportlab`, `openpyxl` 등, 최초 실행 시 자동 설치)
- **Node.js** — 검색 대시보드(`patent-search/dashboard`, 최초 실행 시 `npm install` 자동)
- (선택) **Power Automate** — KIPRIS 특허 데이터 자동 수집

---

> 사용 중 화면이 열리지 않거나 진행이 막히면 매뉴얼(https://iplandscape.vercel.app/)의 문제 해결 안내를 참고하세요.
