---
name: ipl-core-patent
description: 유효특허에서 핵심특허(core patent)를 선별한다. 인용수·패밀리수·청구항수·잔여존속기간·IPC폭 등 가용 정량지표를 자동 감지해 정규화 가중합으로 1차 스코어링하고, 상위 후보의 명세서를 Claude가 읽어 기술 핵심성을 의미 검토해 최종 확정한다. 사용자가 "핵심특허", "주요특허/중요특허 선별", "core patent", "키 특허 찾기", "필수특허", "특허 중요도 평가/랭킹"을 요청하거나 IP Landscape 보고서에 핵심특허 리스트가 필요할 때 사용한다. argument로 [유효데이터폴더경로]를 받는다.
argument-hint: [유효데이터폴더경로]
user-invocable: true
---

# ipl-core-patent — 핵심특허 선별 (정량 스코어링 + AI 검토)

유효특허에서 "반드시 주목해야 할 소수의 특허"를 근거와 함께 골라낸다. **정량 자동 스코어링으로 후보를 좁히고, AI가 명세서를 읽어 확정**하는 2단계다. 통합 PDF 보고서 5장에 들어간다.

## 왜 2단계인가
정량지표만으로 줄세우면 인용이 우연히 많은 주변기술이 끼고, 텍스트만 읽으면 주관적·비효율적이다. 정량으로 객관적 후보군을 만들고, 그 안에서 AI가 기술 핵심성·연구주제 부합도를 판단하면 두 방식의 약점을 서로 보완한다.

## 경로
- 스크립트: `${CLAUDE_SKILL_DIR}/scripts/_core_score.py`, `${CLAUDE_SKILL_DIR}/scripts/_ipl_io.py`
- 출력: `<폴더>/_ipl/core/`

## 사전 조건
- `<폴더>`에 `유효데이터.xlsx`. 정량지표 컬럼은 **가용한 것만** 사용(없어도 동작).
- Python: `pandas numpy openpyxl` (자동 설치)

## 작업 흐름 (2단계)

### Stage A — 정량 스코어링 (Python)
```bash
cd "${CLAUDE_SKILL_DIR}/scripts" && python _core_score.py "<폴더>" --top 30 --final 12
```
- 가용 지표를 자동 감지: `citations / family / claims / remaining_term(출원일+20년) / ipc_breadth`
- 각 지표 min-max 정규화 → 기본 가중치(인용0.35·패밀리0.25·청구항0.20·잔여0.10·IPC폭0.10)로 가중합. **가용 지표만으로 가중치 재정규화.**
- 산출물:
  - `core_scores.csv` — 전체 특허 점수(감사 추적용, UTF-8-SIG)
  - `candidates.json` — 상위 30 후보 + 명세서 텍스트(요약/과제/수단) — **AI 검토 대상**
  - `core_patents.json` — 잠정 상위 12건(reason 비어있음)

가중치를 바꾸려면 `--weights weights.json`(예: `{"citations":0.5,"claims":0.3}`)을 준다.

### Stage B — AI 의미 검토 (Claude가 직접)
`candidates.json`의 상위 후보 명세서를 읽고 `core_patents.json`을 최종 확정한다:
- 각 핵심특허에 **`reason`을 채운다**: "(정량 신호) + (기술적 핵심성)" 1~2문장. 예: "피인용 상위 5%이며, 청구항 1이 고체전해질-전극 계면 안정화를 포괄적으로 청구해 후속 출원의 길목을 막는다."
- **부적합 후보를 교체한다**: 점수는 높지만 연구주제와 무관하거나(노이즈), 같은 패밀리의 중복이거나, 주변기술이면 제외하고 다음 순위로 채운다.
- 연구주제가 주어지면 그 기준으로 핵심성을 판단한다.

### 정량지표가 전무할 때
`candidates.json`에 `no_metrics:true`가 기록되면, Claude가 `유효데이터.xlsx`의 텍스트(요약/청구항/해결수단)를 직접 읽어 연구주제 핵심성으로 선별하고, 보고서에 "정량지표 부재로 AI 의미판단 기반 선별"임을 명시한다.

## 협업
- competitor의 "대표 특허", qualitative의 "핵심 기술 흐름"과 교차 검증해 일관성을 맞춘다.
- 확정된 `core_patents.json`은 report-integrator가 보고서 5장에 사용한다.
