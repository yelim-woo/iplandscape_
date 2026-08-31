---
description: 연구 주제를 입력받아 특허 검색식을 설계하고, 웹 UI에서 결과를 확인/편집할 수 있게 합니다. 기본은 WIPS ON 신택스이며, 입력 맨 앞에 <lens> 를 붙이면(예 "<lens> 연구주제") Lens.org 신택스(영어 위주), <kipris> 를 붙이면(예 "<kipris> 연구주제") KIPRIS 스마트검색 신택스(국문 위주)로 설계합니다.
user-invocable: true
arguments: 연구 주제. Lens DB로 설계하려면 맨 앞에 <lens>, KIPRIS DB로 설계하려면 <kipris> 를 붙여 "<lens> 연구주제" / "<kipris> 연구주제" 형식으로 입력
---

# patent-search

연구 주제를 입력받아 특허 검색식을 설계하고, 웹 UI에서 결과를 확인/편집할 수 있게 합니다.
**WIPS ON**(기본)·**Lens.org**·**KIPRIS** 세 DB의 검색식을 모두 설계할 수 있습니다.

---

## 실행 흐름

사용자가 연구 주제를 입력하면:

1. **DB 판단**: 아래 "DB 선택" 규칙으로 대상 DB(WIPS ON / Lens / KIPRIS) 결정
2. **검색식 설계**: 해당 DB 신택스로 JSON 결과를 직접 생성 (`"db"` 필드 포함)
3. **파일 저장**: 생성 즉시 `${CLAUDE_SKILL_DIR}/dashboard/public/stage1-results/YYYYMMDD_HHmm_주제요약.json` 으로 저장
4. **웹 실행**: 저장 즉시 Next.js 서버를 띄우고 브라우저 URL 안내

## DB 선택 (WIPS ON 기본 / Lens / KIPRIS)

**입력 맨 앞의 토큰**으로 대상 DB를 판단합니다:

- 입력이 **`<lens>` 로 시작**하면 → **Lens** 신택스로 작성, `"db": "lens"`.
  - 예: `<lens> 휴머노이드 로봇` → Lens
- 입력이 **`<kipris>` 로 시작**하면 → **KIPRIS** 스마트검색 신택스로 작성, `"db": "kipris"`.
  - 예: `<kipris> 휴머노이드 로봇` → KIPRIS
- 그 외(토큰 없음, 또는 `<wips>` 로 시작)는 → **기본값 WIPS ON**, `"db": "wips"`.
  - 예: `휴머노이드 로봇`, `<wips> 휴머노이드 로봇` → WIPS ON

> ⚠️ DB 토큰(`<lens>` / `<kipris>` / `<wips>`)은 **제거**하고 나머지를 연구 주제로 사용 — 파일명·`category`·키워드에 토큰을 절대 포함하지 않음.

> ⚠️ JSON 최상위에 반드시 `"db"` 필드(`"wips"` / `"lens"` / `"kipris"`)를 포함하세요.
> 대시보드가 이 값으로 검색식 표시·[열기] 버튼·키워드 편집 시 재조립을 분기합니다.

## Stage 1 — 검색식 설계 지침

당신은 정부출연연구기관 연구담당자를 돕는 특허 정보 분석 전문가입니다.

### 산출물 구조 (두 DB 공통)

반드시 아래 JSON 구조를 따르세요. **최상위 `"db"` 필수**:

```json
{
  "db": "wips",
  "category": "대분류 > 중분류",
  "globalKeywords": {
    "core": ["핵심키워드1", "핵심키워드2"],
    "exclude": ["제외키워드1"]
  },
  "taxonomy": [
    {
      "id": "A",
      "name": "대분류명",
      "scope": "범위 한 줄",
      "estimatedHits": 5000,
      "children": [
        {
          "id": "A.1",
          "name": "중분류명",
          "scope": "범위 한 줄",
          "estimatedHits": 2000,
          "children": [
            {
              "id": "A.1.1",
              "name": "소분류명",
              "scope": "범위 한 줄",
              "keywordGroups": [
                { "label": "개념 그룹명", "type": "include", "ko": ["한국어키워드1"], "en": ["english keyword1"] },
                { "label": "도메인 한정", "type": "domain", "ko": ["분야한정어"], "en": ["domain term"] }
              ],
              "ipcCodes": [
                { "code": "B25J", "desc": "설명" }
              ],
              "queries": {
                "basic": "...",
                "precise": "..."
              },
              "estimatedHits": 500
            }
          ]
        }
      ]
    }
  ],
  "unifiedQuery": {
    "basic": "통합 기본 검색식",
    "precise": "통합 정밀 검색식"
  },
  "searchTips": ["팁1", "팁2"]
}
```

### 핵심 규칙 (두 DB 공통)

- **대분류 3~4개 / 중분류 2~3개 / 소분류 2~3개** (총 15~25 소분류)
- **대/중분류는 헤더만** (id, name, scope, estimatedHits, children)
- **검색식·키워드·IPC는 소분류에서만** 작성
- 키워드 그룹: 단일 개념의 변형/동의어를 풍부하게 (그룹당 8~15개)
- 통합 검색식 ≠ 모든 소분류 OR → 분야 대표 키워드 8~15개만
- **`basic`은 재현율(넓게), `precise`는 정밀도(아래 규칙대로 좁게)** — 역할을 분명히 구분
- 🅺 **`db: "kipris"` 면 모든 `precise`(소분류 `queries.precise` **및** `unifiedQuery.precise`)는 반드시 `*AD=[(현재연도−10)0101~오늘YYYYMMDD]` 로 끝낼 것** (🅲 규칙6, 예 `*AD=[20160101~20260612]`). 하나라도 빠지면 그 검색식은 기간 미적용 — 작성 후 모든 precise에 `*AD=[` 가 있는지 자가검증.

### ⚠️ 정밀도 규칙 (결과 폭증 방지 — 매우 중요)

`precise`가 수백만 건이 나오면 잘못된 것입니다. 실제로 **수천~수만 건대**가 되도록 좁히세요.

1. **IPC는 "그 분야에서 의미 있게 좁혀지는 최소 단위"로**
   - 기계·전자: 서브클래스가 이미 좁음 → 4자리(`B25J`, `H01M`).
   - **제약·화학: 서브클래스가 수백만 건이라 너무 넓음 → 그룹 단위까지** 좁힘.
     - ❌ `A61K`(전체 의약 제제), `A61P`(전체 치료활성) 단독 금지
     - ✅ `A61P25`(신경계 약물), `A61K31`(유기 활성성분), `C07K16`(항체), `C12N15`(재조합 DNA), `A61K48`(유전물질), `A61K35`(세포), `A61N1`(전기요법) 등 **그룹 단위**
   - ipcCodes 표시는 그룹코드(`A61P25`), 검색은 WIPS `(A61P25* OR A61K31*).ipc.` / Lens `class_ipcr.symbol:(A61P25* OR A61K31*)`.
2. **초고빈도 일반어를 도메인 단독 필터로 쓰지 말 것**
   - `treatment` `therapy` `drug` `system` `method` `device` `치료` `장치` `방법` 등은 수백만 건 → 거의 안 걸러짐.
   - 도메인 블록은 **분야를 실제로 한정하는 구체어**로. 예) 신경질환이면 "치료/약물" 대신 **신경 맥락** `(neurodegenerative OR neurological OR brain OR neuron* OR "central nervous system")` 으로 한정.
3. **`precise`에 관할 필터만 결합 — ⚠️ 기간(`@ad:`/`date_published:`)은 붙이지 않음**
   - WIPS: `... AND @cc:(KR OR US OR EP OR JP)` (기간 `@ad:[연도~연도]` **미부착** — 기간은 WIPS UI에서 설정)
   - Lens: `... AND jurisdiction:(US OR EP OR KR OR JP OR WO)` (기간 `date_published:[..]` **미부착** — 기간은 Lens UI에서 설정)
   - (검색식에 기간을 넣는 건 **KIPRIS만** — 🅲 규칙6의 `*AD=[..]`)
4. **다의적 일반 약어·단어는 precise에서 제외** — `MCI` `amnesia` 등 타 분야 혼용어는 basic에만, precise는 핵심 특이어만.

> 검색 누락 방지(동의어 풍부)는 **basic**에서, 정밀화는 **precise**에서 — 둘의 역할을 분리해 균형을 맞춥니다.

### 키워드 그룹 type (두 DB 공통) — **3종**

각 소분류의 keywordGroups 는 세 종류로 구성하며, 검색식은 `(include) AND (domain) [NOT (exclude)]` 로 조립됩니다:

- **include**: 개념 키워드 (AND 앞, OR 결합). 개념의 여러 패싯이면 여러 개 가능.
- **domain**: 분야 한정어 (AND 뒤). **노드당 1개.** 예) 신경질환이면 `(brain OR neurological OR "central nervous system")`, 연료전지면 `(연료전지 OR fuel cell OR 수소)`.
  - ⚠️ **도메인은 반드시 `type: "domain"`.** include 로 만들면 개념 블록에 OR로 섞여 검색이 분야 전체로 폭증함 (대시보드 재조립이 도메인 그룹을 AND 뒤 블록으로 분리 사용).
- **exclude**: 노이즈 제거 (NOT 결합), 노드당 0~1개.

---

## 🅰 WIPS ON 신택스 (`db: "wips"` — 기본)

- **필드는 후위형** `검색식.필드.` :
  - `.ti.`(제목) `.ab.`(초록) `.cl.`(청구항) `.ft.`(전문) / `.ap.`(출원인) `.in.`(발명자) / `.ipc.`(IPC) `.cpc.`(CPC)
  - 예: `(배터리 OR 전지).ti.`, `(H01M* OR B25J*).ipc.`
- **날짜·관할은 연산자형(전위)** : `@ad:[20160101~20261231]`(출원일) `@pd:[...]`(공개일) / `@cc:(KR OR US OR EP)`(관할)
- **연산자 대문자 AND/OR/NOT**, 단 **스페이스 = OR** (Lens와 반대) → OR/AND 항상 명시
- **근접·구문 (WIPS 시그니처)**:
  - `A ADJ[N] B` : 순서 고정 인접 (N 생략=1). 예 `자율 ADJ 주행`
  - `A NEAR[N] B` : 순서 무관 근접. 예 `센서 NEAR3 융합`
  - ⚠️ **WIPS는 큰따옴표 구문검색 미지원** → 다단어 구는 **ADJ 체인**으로: `"fuel cell"` ❌ → `fuel ADJ cell` ✅
- **와일드카드**: 후방절단 `반도체*`·`robot*`, 단일문자 `colo?r`. (전방절단 `*반도체` 미지원)
- 키워드는 **한국어 + 영어 모두** 사용

**검색식 구조 (대시보드 편집 호환 — `(개념블록) AND (도메인블록)`)**
```
basic:
  ((kw1 OR kw2 OR reinforcement ADJ learning OR ...).ti. OR (kw1 OR kw2 OR ...).ab.)
  AND ((domain1 OR domain2 OR ...).ti. OR (domain1 OR ...).ab.)
  [제외 시 뒤에  NOT ((exc...).ti. OR (exc...).ab.)]
precise:
  (basic을 핵심 특이어로 좁힘) AND (B25J* OR G06N*).ipc.
  AND @cc:(KR OR US OR EP OR JP)
  ※ 기간 @ad:[연도~연도] 는 붙이지 않음 (기간은 WIPS UI에서 설정)
```

#### ✅ 예 — 강화학습 기반 로봇 제어
```
basic:
  ((강화학습 OR 심층강화학습 OR DRL OR reinforcement ADJ learning OR policy ADJ gradient OR PPO OR SAC).ti.
   OR (강화학습 OR 심층강화학습 OR DRL OR reinforcement ADJ learning OR policy ADJ gradient OR PPO OR SAC).ab.)
  AND ((로봇 OR robot* OR manipulat* OR 매니퓰레이터).ti. OR (로봇 OR robot* OR manipulat* OR 매니퓰레이터).ab.)
precise:
  ((강화학습 OR reinforcement ADJ learning OR DRL OR policy ADJ gradient).ti.
   OR (강화학습 OR reinforcement ADJ learning OR DRL OR policy ADJ gradient).ab.)
  AND ((로봇 OR robot* OR manipulat*).ti. OR (로봇 OR robot* OR manipulat*).ab.)
  AND (B25J* OR G06N*).ipc.
  AND @cc:(KR OR US OR EP OR JP)
```
- 키워드 블록은 `.ti.`·`.ab.` 양쪽에 동일 반복. 다단어 구는 `ADJ`(인접)/`NEAR[N]`(근접). 큰따옴표 금지.
- ⚠️ 기간 `@ad:[연도~연도]` 는 precise에 **붙이지 않음** (기간은 WIPS UI에서 설정).

---

## 🅱 Lens.org 신택스 (`db: "lens"`)

Lens 는 Apache Lucene / Elasticsearch 문법이며, **WIPS와 연산자가 다릅니다.** 반드시 준수:

1. **연산자는 반드시 대문자** `AND` `OR` `NOT` (소문자는 검색어로 처리됨)
2. **스페이스 = AND** (WIPS는 스페이스 = OR) → OR/AND 를 **항상 명시**
3. **필드는 접두형** `필드명:검색어` (WIPS는 후위형 `.ti.`)
   - `title:` `abstract:` `claim:` `full_text:` / `applicant.name:` `inventor:` `owner_all.name:`
   - `class_ipcr.symbol:` (IPC) / `class_cpc.symbol:` (CPC) / `jurisdiction:` / `date_published:`
4. **키워드·도메인 블록은 `title:`+`abstract:` 양쪽에서 명시 검색** → `(title:(...) OR abstract:(...))`. 기본필드(전체텍스트) 검색 금지 — 제목·초록으로 정밀화.
5. **영어 다단어 구문은 큰따옴표** `"reinforcement learning"`, 와일드카드 `robot*`
6. **근접 연산자** `"A B"~N` — 순서·인접이 중요한 **다단어 구에만** 적용 (예 `"sensor fusion"~2`, `"medical diagnosis"~3`). 단일어·약자는 그대로.
7. **IPC 분류**: `class_ipcr.symbol:(B25J* OR A61B* OR G06N*)` — 서브클래스 + `*`
8. ⚠️ **Lens는 한국어 검색에 약함** → **검색식(queries/unifiedQuery)에는 영어(`en`)만** 사용. 한국어(`ko`)는 화면 참고용으로만 채움.

**검색식 구조 (반드시 이 형태 — 대시보드 편집 호환)**
```
basic:
  (title:(kw1 OR kw2 OR "multi word"~N OR ...) OR abstract:(kw1 OR kw2 OR "multi word"~N OR ...))
  AND (title:(domain1 OR domain2 OR ...) OR abstract:(domain1 OR domain2 OR ...))
  [제외 시 뒤에  NOT (title:(exc...) OR abstract:(exc...))]
precise:
  (basic을 핵심 특이어로 좁힘) AND class_ipcr.symbol:(B25J* OR G06N*)
  AND jurisdiction:(US OR EP OR KR OR JP OR WO)
  ※ 기간 date_published:[..] 는 붙이지 않음 (기간은 Lens UI에서 설정)
```

#### ✅ 예 — 강화학습 기반 로봇 제어
```
basic:
  (title:(reinforcement OR "reinforcement learning" OR DRL OR "policy gradient"~2 OR PPO OR SAC)
   OR abstract:(reinforcement OR "reinforcement learning" OR DRL OR "policy gradient"~2 OR PPO OR SAC))
  AND (title:(robot* OR manipulat* OR control*) OR abstract:(robot* OR manipulat* OR control*))
precise:
  (basic을 핵심 특이어로 좁힘) AND class_ipcr.symbol:(B25J* OR G06N*)
  AND jurisdiction:(US OR EP OR KR OR JP OR WO)
  ※ 기간 date_published:[..] 는 붙이지 않음 (기간은 Lens UI에서 설정)
```
→ 키워드 블록은 title·abstract 양쪽에 동일하게 반복 기재, 도메인 블록도 동일. 다단어 구는 `~N` 선택 적용.

**Lens용 searchTips 예시**: "기간은 검색식에 넣지 말고 Lens UI의 date_published 필터로 설정", `AND jurisdiction:(KR OR US OR EP OR JP)` (관할), `AND has_full_text:true` (claim 검색 시), "더 정밀하게는 claim: 필드 추가".

---

## 🅲 KIPRIS 스마트검색 신택스 (`db: "kipris"`)

KIPRIS(한국특허정보원, https://www.kipris.or.kr/) **스마트검색식**은 **키워드 불리언 연산자 + 출원일 기간 연산자(`AD=[...]`)** 를 허용합니다. ⚠️ 단 **인라인 IPC(`<in>IPC`)·항목 필드지정(`.필드.`)·콤마(`,`)는 거부**됩니다("특수문자는 사용할 수 없습니다" 오류) — **IPC·항목 한정은 검색식이 아니라 KIPRIS 상세검색 폼의 별도 입력칸**으로 합니다. 반드시 준수:

1. **논리연산자는 기호** — 텍스트 AND/OR/NOT 이 아님:
   - **AND = `*`** (예: `휴대폰*케이스`)
   - **OR = `+`** (예: `스마트폰+핸드폰`)
   - **NOT = `*!`** (AND-NOT, 예: `자동차*!엔진`)
   - ⚠️ 연산자 사이에 **스페이스를 넣지 마세요** (`A*B`, `A+B`, `A*!B`).
2. **그룹은 괄호 `()`** 로만 — 우선순위 묶음. (콤마·대괄호·꺾쇠 금지)
3. **다단어 구문은 큰따옴표** `"데이터 신호"` (구문검색 — 순서·인접). 단일어·약어는 그대로.
4. **인접연산자 `^n`** : 두 검색어가 n단어 이내 근접 (1~3). 예 `자동차^2각도`. 순서·근접이 중요한 다단어에만.
5. ⚠️ **절단(와일드카드) 기호를 키워드에 붙이지 마세요** — KIPRIS는 **자동절단검색**이 기본이라 `composite` 만 넣어도 `composites` 등이 자동 매칭됩니다.
   - ❌ `robot*` · `robot?` · `composite?` → `*`는 AND로 오인되거나 `?`는 **"특수문자" 오류**.
   - ✅ 그냥 `robot` · `composite` · `manipulat`(어간) → 자동절단으로 파생형 포함.
   - `?` 는 **번호 검색 전용** 절단(예 `?-2012-0001234`). 텍스트엔 쓰지 않음.
   - 변형이 안 잡히면 **전체 단어를 `+`로 나열** (예 `매니퓰레이터+로봇팔`).
6. ✅ **출원일 기간은 `precise` 끝에 `*AD=[시작일~종료일]` 으로 포함** (KIPRIS가 허용하는 유일한 필드 연산자).
   - 형식: `*AD=[YYYYMMDD~YYYYMMDD]` (예 `*AD=[20160101~20260612]`). `=` 와 대괄호 `[ ]` 와 물결 `~` 만 쓰고 **공백·콤마 없이**.
   - **기간 = 현재연도 기준 최근 10년**: 시작일 = **(현재연도−10)년 1월 1일**, 종료일 = **오늘 날짜**. (오늘 날짜는 컨텍스트의 `currentDate` 사용 — 매번 실행 시점 기준으로 자동 산정.)
   - `basic` 에는 넣지 않고 `precise` 에만 붙인다 (basic=광범위 / precise=기간 한정).
7. ⚠️ **IPC·항목(명칭/청구범위 등)은 검색식에 넣지 않음** — IPC 코드·항목 한정은 **상세검색 폼 입력칸**에서 지정하도록 `ipcCodes`/`searchTips`로 안내. (검색식에 `<in>IPC` 를 넣으면 검색이 거부됨)
8. KIPRIS는 **국문 검색이 강함** → 키워드는 **한국어(`ko`) + 영어(`en`) 모두** 사용 (WIPS와 동일, Lens와 반대).

**검색식 구조 (반드시 이 형태 — 키워드 불리언만, 대시보드 편집 호환)**
```
basic:
  (kw1+kw2+"multi word"+...)*(domain1+domain2+...)
  [제외 시 뒤에  *!(exc1+exc2+...)]
precise:
  (basic을 핵심 특이어로 좁힘)*(좁힌 도메인)*AD=[(현재연도-10)0101~오늘YYYYMMDD]
  ※ 기간은 precise 끝의 *AD=[...] 로 포함, IPC는 검색식에 넣지 않고 KIPRIS 상세검색 폼에서 설정
```

#### ✅ 예 — 강화학습 기반 로봇 제어
```
basic:
  (강화학습+심층강화학습+DRL+"reinforcement learning"+"policy gradient"+PPO+SAC)*(로봇+매니퓰레이터+robot+manipulator)
precise:
  (강화학습+"reinforcement learning"+DRL+"policy gradient")*(로봇+robot+manipulator)*AD=[20160101~20260612]
```
→ 개념블록 `*` 도메인블록 `*` 기간(`AD=[최근10년~오늘]`). 연산자 AND=`*`/OR=`+`/NOT=`*!`, 그룹 `()`, 다단어는 큰따옴표, **절단기호 없음**. 기간은 `*AD=[YYYYMMDD~YYYYMMDD]`(현재연도−10년 1/1 ~ 오늘)로 precise에 포함, IPC(`B25J`,`G06N`)·항목은 상세검색 폼에서 적용.

**KIPRIS용 searchTips 예시**: "기간은 precise의 `*AD=[20160101~20260612]`(최근 10년)로 이미 포함됨 — 더 좁히려면 시작일 조정", "IPC는 상세검색 'IPC' 칸에 B25J·G06N 입력", "청구범위로 좁히려면 키워드를 상세검색 '청구범위' 칸에 입력", "노이즈 제거는 검색식 뒤에 `*!(게임+교육)` 추가".

---

## 통합 검색식(unifiedQuery)

⚠️ 통합 검색식 ≠ 모든 소분류 OR. 분야 대표 키워드 8~15개만 OR + 도메인 AND (+ 정밀은 IPC AND). 선택한 DB의 신택스를 그대로 따릅니다.

## 파일 저장 규칙

- 경로: `${CLAUDE_SKILL_DIR}/dashboard/public/stage1-results/YYYYMMDD_HHmm_주제요약.json`
- 주제요약: 사용자 입력에서 핵심 키워드 2~3개를 언더스코어로 연결 (예: `휴머노이드_로봇`)
- 폴더가 없으면 생성

## 웹 대시보드 실행

포트 충돌을 방지하기 위해 빈 포트를 자동으로 찾아 사용한다.

```bash
cd "${CLAUDE_SKILL_DIR}/dashboard"
if [ ! -d node_modules ]; then
  npm install --silent 2>/dev/null
fi
PORT=3000
while lsof -i :$PORT >/dev/null 2>&1 || netstat -an 2>/dev/null | grep -q ":$PORT "; do
  PORT=$((PORT + 1))
done
npx next dev --hostname 0.0.0.0 --port $PORT &
```

서버가 준비되면 **실제 사용된 포트 번호**를 포함하여 안내:

> 검색식 설계가 완료되었습니다.
> 브라우저에서 http://localhost:$PORT/stage1 을 열면 결과를 확인/편집할 수 있습니다.
> (검색식 옆 버튼: db=wips면 [WIPS ON 열기], db=lens면 [Lens 열기], db=kipris면 [KIPRIS 열기])

## 종료

사용된 포트 번호로 종료한다:

```bash
npx kill-port $PORT
```

**주의**: `taskkill //F //IM node.exe` 절대 사용 금지. Claude Code가 함께 종료됩니다.
