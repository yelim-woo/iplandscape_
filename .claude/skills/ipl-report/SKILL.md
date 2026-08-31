---
name: ipl-report
description: IP Landscape 분석 산출물을 모아 단일 통합 보고서를 PDF(IP_Landscape_Report.pdf)와 한글 HWPX(IP_Landscape_Report.hwpx)로 동시 생성한다. manifest.json(데이터개요·정량·경쟁사·정성·핵심특허 + 차트 PNG 경로)을 입력받아 표지→Executive Summary→5개 장 구조로, PDF는 reportlab(한글 폰트 자동 등록), HWPX는 양식.hwpx 템플릿(차트 BinData 임베드)으로 빌드한다. 두 빌더는 같은 manifest를 공유한다. 사용자가 "통합 보고서", "최종 PDF 보고서", "한글/hwpx 보고서", "IP landscape 보고서 PDF", "분석 결과를 PDF로/한글로", "리포트 만들어"를 요청하거나 파이프라인 마지막에 모든 분석을 하나의 보고서로 합칠 때 사용한다. argument로 [manifest.json경로]를 받는다.
argument-hint: [manifest.json경로]
user-invocable: true
---

# ipl-report — 통합 PDF 보고서 빌더

흩어진 IP Landscape 분석 자산(`_ipl/`의 JSON + PNG)을 **하나의 일관된 PDF**로 엮는다. 파이프라인의 최종 산출물이다.

## 경로
- 스크립트: `${CLAUDE_SKILL_DIR}/scripts/_build_pdf.py`, `${CLAUDE_SKILL_DIR}/scripts/_build_hwpx.py`, `${CLAUDE_SKILL_DIR}/scripts/_ipl_io.py`
- HWPX 템플릿: `${CLAUDE_SKILL_DIR}/assets/양식.hwpx` (벤더링됨)
- 입력: `<폴더>/_ipl/manifest.json` (PDF·HWPX 빌더가 **동일 manifest를 공유**)
- 출력: `<폴더>/IP_Landscape_Report.pdf` + `<폴더>/IP_Landscape_Report.hwpx`

## 사전 조건
- 분석 에이전트들이 `_ipl/` 하위에 산출물을 만들어 둔 상태.
- Python: `reportlab pillow` (자동 설치). 한글 폰트는 OS에서 자동 탐지(Windows=Malgun Gothic).

## 작업 흐름 (2단계)

### Stage A — manifest.json 조립 (Claude/report-integrator가 직접)
`_ipl/` 하위 산출물을 모아 `_ipl/manifest.json`을 만든다. **Executive Summary는 직접 작성**한다(각 분석의 핵심 발견 종합).

manifest 스키마:
```json
{
  "meta": {"title":"...IP Landscape 분석 보고서", "subject":"연구주제", "date":"2026-06-05", "source":"WIPS ON", "author":"(선택)"},
  "data_summary": { "raw_count":1200, "valid_count":340, "excluded_count":860,
                    "year_range":[2016,2025], "criteria_summary":"등록·최근10년 + 천연물 활성성분 관련성",
                    "exclude_reasons": {"법적상태 미등록": 500, "관련성 낮음": 360} },
  "executive_summary": ["종합 불릿1", "종합 불릿2", "..."],
  "market": { "tech_overview":["간략 기술 설명", {"t":"...","refs":[5]}],
              "env_domestic":[{"t":"국내 환경·최근 소식","refs":[1,2]}, "..."],
              "env_global":[{"t":"국외 환경·최근 소식","refs":[3]}, "..."],
              "references":["매체/기관 (YYYY-MM)","..."] },
  "quant": { "charts_dir": "<abs>/_ipl/quant",
             "interpretation": [ {"id":1, "title":"연도별 출원 추이", "bullets":["...","..."]}, ... ] },
  "competitor": { "companies":[ {"rank":1,"name":"...","count":61,"share":0.18,
                    "focus_ipc":["H01M"],"momentum":"상승","positioning":"선도",
                    "profile":["...","..."],"rep_patents":["..."]} ],
                  "charts": {"share":"<abs>.png","trend":"<abs>.png","ipc":"<abs>.png"} },
  "qualitative": { "tech_flow":{"title":"기술흐름도","bullets":[...]},
                   "os_matrix":{"title":"O/S Matrix","bullets":[...]},
                   "contour":{"title":"특허맵","bullets":[...],"hotspots":[...],"whitespace":[...]},
                   "charts": {"tech_flow":"<abs>.png","os_matrix":"<abs>.png","contour":"<abs>.png"} },
  "core": [ {"rank":1,"number":"...","title":"...","applicant":"...","year":2021,"score":0.87,"reason":"..."} ]
}
```
**해석 불릿 형식(가독성):** 정량·경쟁사·정성의 해석 불릿은 `{"l":"라벨","t":"내용"}` 객체로 쓰면 PDF가 '라벨 | 내용' 정의리스트로 렌더한다(문자열이면 ▪ 불릿). 라벨 예: 현황/동인/함의/비교/전략/전망/유의.
**경쟁사 추가 키:** `competitor.chart_interp={share,trend,ipc}`(차트별 해석), `companies[].rep_patents=[{number,title,year,citations,family}]`(대표특허 표로 렌더), `companies[].profile`(라벨형).
**정성 등고선 2종:** `qualitative.contour_ipc`/`qualitative.contour_tech` 각각 `{title,bullets,hotspots,whitespace}`, `qualitative.charts={contour_ipc:png, contour_tech:png}`. (기술흐름도/OS는 데이터 있으면 tech_flow/os_matrix 키로 추가.)
**핵심특허 표:** `score`는 표에 표시하지 않는다(선정은 정량+AI지만 점수는 비노출). 각 항목 `reason`은 '라벨 | 근거' 정의리스트로 렌더된다.
**기술·시장 분석(`market`):** 입력 특허 데이터와 **별개로** 연구주제 기반 시장/환경을 요약하는 장. Executive Summary 다음, '분석 개요' 앞에 **번호 없는 카드형 장**으로 렌더된다(기술 이해 → 환경분석 국내 → 환경분석 국외; 각 섹션은 회색 헤더밴드+좌측 액센트 룰 카드). 각 항목은 문자열 또는 `{"t":...,"refs":[n,...]}`. `refs`는 `market.references`(번호순)를 가리키며 본문 끝 `[n]` 윗첨자로 렌더되고, **출처는 보고서 맨 뒷페이지 '참고문헌(References)' 장**에 번호순 정리된다. market-analyst가 웹 리서치로 채운다. 비어 있으면 장 자동 생략(선택 장).
**본문 강조(`**...**`):** 모든 해석/시장 불릿 텍스트에서 `**강조**` 마크다운은 **볼드**로 렌더된다(중요 포인트 강조). 또한 핵심 수치(%·금액·건수·배수·CAGR)는 빌더가 자동 볼드한다(`rich()`). HWPX는 인라인 볼드를 생략하고 `**` 마커만 제거(한글에서 편집).
**부록 제거:** '부록(Appendix)' 장은 더 이상 렌더하지 않는다. 맨 뒤 장은 '참고문헌'이다.
**구간형 O/S Matrix(`qualitative.os_matrix`):** `{title, landscape, bullets}` + `qualitative.charts.os_matrix`(=`os_matrix_periods.png`). 정성분석 장에서 렌더되며 성숙(레드오션)/성장/신규/공백(순위①②③) 색분류 매트릭스. **`landscape`는 기본 false=세로 도표**(6×6 등은 페이지 폭에 맞게 충분히 큼). 매우 넓은 매트릭스(8×8+)만 `landscape:true`로 주면 이미지 90° 회전 가로 전용 페이지로 배치한다.
**공백기술 & 전략(`whitespace_strategy`, 매니페스트 최상위):** `{title, intro, opportunities:[{rank,combo,evidence,strategy}], contour_notes:[...]}`. 정성분석 장 끝에 **표(순위·공백조합·근거·진입전략) + 등고선 공백 종합**으로 렌더된다. **보고서 핵심 목적(공백기술 발굴·연구부서 전략 지원)** 의 결론부. 비어 있으면 생략.

**빌더가 자동 처리하는 것(매니페스트에서 신경 안 써도 됨):**
- **XML 이스케이프**: `R&D`·`M&A`·`<`·`>` 등은 PDF 빌더가 자동 이스케이프한다(`&`를 그대로 두면 reportlab이 `R&D;`로 깨뜨림 — 이미 빌더에서 방지). HWPX도 동일.
- **정제 기준 표시**: `data_summary.criteria_summary`(짧은 라벨)를 우선 쓰고, 없으면 `criteria_path`의 **파일명만** 보여준다(로컬 전체경로·깨진 글자 노출 방지). 가급적 `criteria_summary`를 넣어라.
- **특허번호 포맷**: KR 13자리 무하이픈 번호(예 `1024633740000`)는 빌더가 `10-2463374`(등록)·`10-YYYY-NNNNNNN`(출원)로 자동 정리(`fmt_patent_no`, 멱등). JP/US 등은 원본 유지.
- **대표특허 표 컬럼**: `rep_patents`에 `citations`/`family`가 **하나도 없으면** 해당 컬럼을 자동 생략하고 캡션도 '(출원인별 대표 특허)'로 바꾼다(빈 컬럼 방지). 있으면 컬럼·'(피인용·패밀리 기준)' 캡션을 노출.
- **긴 텍스트**: 표의 기업명·명칭·출원인 등은 길면 말줄임표(`…`)로 정리된다(글자 단위 뚝 잘림 방지).
- **데이터 개요 표 한글**: 값 셀도 한글 폰트로 렌더(단위 '건' 등이 □로 깨지지 않음).
- **표지 작성자**: `meta.author`가 없으면 '작성' 줄을 통째로 생략(빈 '작성 -' 표기 안 함).

**조립 규칙:**
- 각 분석 JSON(`competitor.json`, `contour_ipc.json`+`contour_tech.json`, `core_patents.json`, `data_summary.json`)을 읽어 해당 키에 넣는다.
- 차트 경로는 **절대경로**로 적는다(빌더가 다른 CWD에서 실행돼도 찾도록).
- 정량 차트는 `quant.charts_dir` + `chart_{id}.png` 규칙으로 자동 매칭되므로 interpretation의 `id`만 맞추면 된다(개별 `chart` 키로 덮어쓰기도 가능).
- 수행되지 않은 분석은 **키를 비우거나 생략**한다. 빌더가 해당 장을 "미수행"으로 표기한다(그럴듯하게 채우지 말 것).

### Stage B — 보고서 빌드 (Python) — PDF + HWPX 둘 다
```bash
cd "${CLAUDE_SKILL_DIR}/scripts"
python _build_pdf.py  "<폴더>/_ipl/manifest.json"   # → IP_Landscape_Report.pdf
python _build_hwpx.py "<폴더>/_ipl/manifest.json"   # → IP_Landscape_Report.hwpx
```
표지 → 분석요약 → 기술·시장 분석 → 1.분석개요 → 2.정량분석(차트+해석) → 3.경쟁사 상세 → 4.정성분석(기술흐름/OS/등고선) → 5.핵심특허(표+근거) → 참고문헌 순으로 보고서를 만든다. **두 빌더는 같은 manifest.json을 소비**하므로 내용·차트·표·해석이 동일하다(분석 재실행 불필요).

**HWPX(_build_hwpx.py) 참고:**
- patent-dashboard의 `양식.hwpx`(assets에 벤더링)를 템플릿으로, 차트 PNG를 BinData에 임베드하고 content.hpf 매니페스트를 갱신한다. 핵심특허·경쟁사 표는 header.xml에 borderFill 8(헤더 음영)·9(격자)를 주입해 그린다.
- HWPX는 한글 양식(장 헤더 표·개조식 불릿) 기반이라 **PDF의 프리미엄 비주얼(canvas 표지·2-pass 목차·러닝헤더)을 1:1로 복제하지 않는다** — 내용은 동일하되 외형은 한글 보고서 양식이며, 한글에서 바로 후속 편집할 수 있다.
- `pip` 의존성은 `pillow`뿐(있으면 자동). 폰트는 한글 자체 폰트를 쓰므로 등록 불필요. 빌드 후 `${HOME}/.claude/skills/hwpx/scripts/validate.py`로 구조 검증 가능.
- HWPX만/PDF만 단독으로 다시 만들려면 해당 줄만 실행한다.

**출력 양식 규칙(특허분석 보고서 표준 양식):**
- **장 헤더**: 파란 번호박스 + 굵은 제목 + 이중 가로줄(굵은선/얇은선).
- **그림 우선 배치**: 섹션제목 → 그림 → 가운데 `<그림 N-M> 제목` 캡션 → `○` 불릿 해석 순. (해석을 그림 위에 두지 않는다.)
- **블록 무결성**: 각 (섹션제목+그림+캡션+해석)은 `KeepTogether`로 묶여 페이지 경계에서 쪼개지지 않는다 — 제목만 페이지 끝에 남거나 그림이 다음 장으로 떨어지는 현상을 방지. 차트 이미지는 max_h로 제한해 한 블록이 한 페이지에 들어오게 한다.
- **불릿**: `○` 마커, 양쪽정렬, 행잉 인덴트. 막연한 표현 대신 수치 근거를 담는다.
- 한글 볼드는 `malgunbd.ttf`를 별도 등록(Malgun-B). 이 규칙들을 바꾸려면 `_build_pdf.py`의 `chapter_header`/`figure_block`/`ST` 스타일을 수정한다.

## 에러 핸들링
- 한글이 깨지면 폰트 등록 실패다. `_build_pdf.py`가 `Malgun`→`Helvetica`로 폴백하므로, Windows에서 `C:\Windows\Fonts\malgun.ttf` 존재를 확인한다.
- 이미지 경로가 틀리면 해당 자리에 "[이미지 없음]"이 출력된다 → manifest의 절대경로를 점검한다.
- 빌드 실패 시 누락 자산을 특정해 보고하고, 가능한 섹션만으로 재빌드한다(전체 실패 금지).
