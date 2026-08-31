---
name: ipl-contour-map
description: 유효특허의 IPC 분류를 기반으로 기술공간을 2D로 투영하고 특허 밀도를 등고선(contour)으로 그린 특허맵을 만든다. 밀집 영역(핫스팟)과 저밀도 영역(White Space, 미개척 기술공간)을 식별한다. 사용자가 "특허맵", "등고선 맵", "기술 지형도", "landscape map", "White Space 분석", "기술 공백 영역", "특허 밀도 지도"를 요청하거나 IP Landscape 정성분석에 등고선 특허맵이 필요할 때 사용한다. argument로 [유효데이터폴더경로]를 받는다.
argument-hint: [유효데이터폴더경로]
user-invocable: true
---

# ipl-contour-map — 특허맵 등고선 (기술 지형도)

IPC 분류로 정의된 기술공간에 특허를 배치하고, **밀도를 등고선으로 그려 핫스팟과 White Space를 가시화**한다. IP Landscape 정성분석(4장)에 들어간다.

## 원리 (왜 이렇게 하나)
특허맵은 본질적으로 "기술 좌표 위 특허 분포"다. 좌표를 임베딩으로 만들면 정확하지만 인프라가 무겁다. 대신 **IPC 서브클래스(예: H01M)의 공동출현 패턴**을 특징으로 쓰면, 별도 모델 없이도 기술적으로 가까운 특허가 가깝게 모인다. 이를 PCA로 2D 투영하고 가우시안 KDE로 밀도를 추정해 등고선을 그린다. 절대 좌표값은 의미가 없고, **군집·능선·골짜기(공백) 패턴**이 해석 대상이다.

## 경로
- 스크립트: `${CLAUDE_SKILL_DIR}/scripts/_contour.py`, `${CLAUDE_SKILL_DIR}/scripts/_ipl_io.py`
- 출력(모드별): `<폴더>/_ipl/qualitative/{contour_map_ipc.png + contour_ipc.json}` (ipc), `{contour_map_tech.png + contour_tech.json}` (keyword)

## 사전 조건
- `<폴더>`에 `유효데이터.xlsx`. **IPC 컬럼 필수**(Current IPC All 우선, 없으면 Main).
- IPC 보유 특허 10건 이상.
- Python: `pandas numpy matplotlib openpyxl pillow` (자동 설치). scikit-learn 불필요(numpy SVD 사용).

## 작업 흐름 (2단계)

### Stage A — 등고선 생성 (Python, 2종)
두 관점의 특허맵을 만든다(권장: 둘 다 생성해 보고서에 나란히 제시):
```bash
cd "${CLAUDE_SKILL_DIR}/scripts"
python _contour.py "<폴더>" --mode ipc       # ①IPC 기술분류 등고선
python _contour.py "<폴더>" --mode keyword   # ②기술주제(제목·초록 용어) 등고선
```
- `--mode ipc` → `contour_map_ipc.png` + `contour_ipc.json` (핫스팟 라벨 = IPC 서브클래스, 키 `ipc`). 분류 공동출현 기반 '기술 분류 지형'.
- `--mode keyword` → `contour_map_tech.png` + `contour_tech.json` (핫스팟 라벨 = 핵심 용어, 키 `term`). 제목+초록 용어 공동출현 기반 '무엇에 관한 특허인가(주제) 지형'. IPC와 다른 시각의 군집·공백을 드러낸다.
- 공통 JSON: `{mode, n_patents, n_features, top_terms, hotspots:[{ipc|term, density, n_near}], whitespace:[{near_ipc, density}]}`
- 핫스팟 라벨은 '지역 내 최다 테마', White Space 인접 라벨은 주변 주요 테마로 산출된다. keyword 모드는 영문 용어(charging/pack 등)가 라벨이며 해석에서 한국어로 풀어 쓴다.

### Stage B — 해석 작성 (Claude가 직접)
`contour_ipc.json`·`contour_tech.json`을 읽고 정성분석의 `qualitative.contour_ipc`·`qualitative.contour_tech` 항목을 채운다:
- **핫스팟 해석**: 밀집 IPC가 어떤 기술인지(예: H01M=이차전지) 풀어 설명하고, 왜 경쟁이 집중되는지.
- **White Space 해석**: 저밀도 영역의 인접 IPC를 보고, 그것이 진짜 기술 공백(기회)인지 아니면 비현실적 조합인지 판단. 막연히 "공백=기회"로 단정하지 말 것 — 인접 기술 맥락에서 진입 타당성을 함께 적는다.

**해석 깊이 기준:** "H01M 영역이 밀집"이 아니라 "이차전지 전극(H01M) 영역에 출원이 능선처럼 집중돼 레드오션이며, 인접한 열관리(H01M/F28)와 전지관리시스템(G01R) 사이 골짜기는 통합 솔루션의 미개척 공백으로 보인다"처럼 (밀도 패턴 + 기술 의미 + 시사점)을 담는다.

## 데이터 없음 처리
IPC/텍스트가 없거나 보유 특허가 부족하면 해당 모드의 `contour_ipc.json`/`contour_tech.json`에 `error`가 기록된다. 등고선 장을 "데이터 부족으로 미수행"으로 보고하고 임의 생성하지 않는다.
