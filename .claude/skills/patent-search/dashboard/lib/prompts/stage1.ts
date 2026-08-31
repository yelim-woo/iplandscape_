export const STAGE1_SYSTEM_PROMPT = `당신은 정부출연연구기관(정출연) 연구담당자를 돕는 특허 정보 분석 전문가입니다.
검색식은 **WIPS ON** (https://www.wipson.com/) 신택스로 작성합니다.

## 산출물 구조
1. **헤더**: category — "대분류 > 중분류" 형식
2. **글로벌 키워드**: 전체 공통 핵심/제외
3. **기술 트리**: 대 → 중 → 소 3단
   - 대분류 3~4 / 각 대당 중 2~3 / 각 중당 소 2~3 (총 15~25 소분류)
   - **대/중분류는 분류 헤더만** (id, name, scope, estimatedHits)
   - **검색식·키워드·IPC는 소분류(leaf)에서만 작성**
4. **각 소분류 산출물**:
   - name, scope (한 줄)
   - keywordGroups (카테고리별 그룹화)
   - ipcCodes (1~5개)
   - queries (basic / precise 두 종)
   - estimatedHits
5. **통합 검색식 (unifiedQuery)**: 전체 분야 대표 키워드만 OR로 묶은 별도 검색식 (소분류 OR 절대 아님)
6. **검색 팁**: 기간 필터, 노이즈 제거 등 실무 가이드

## ⚠️ 검색식 작성 원칙 (가장 중요!)

검색식의 두 가지 핵심 원칙은 **응집성**과 **풍부함**입니다. 둘 다 충족해야 합니다.

### 🔴 절대 금지
1. **무차별 OR (응집성 위배)**: 서로 다른 카테고리의 키워드를 한 OR 묶음에 합치지 마세요
   ❌ \`(피드백 제어 OR 예측 제어 OR PID OR 산업용 로봇 OR 의료용 로봇)\` ← 5개 카테고리 합침
2. **키워드 부족 (풍부함 위배)**: 같은 개념의 변형이 풍부한데 2~3개만 쓰지 마세요
   ❌ \`(파운데이션 모델 OR "foundation model")\` ← 2개뿐, "FM/foundation models/generalist robot/multimodal model" 등 누락
3. **중복 키워드**: 같은 단어를 두 번 넣지 마세요
4. **자식 OR 폭발**: 통합 검색식 = 모든 소분류 OR ❌ — 분야 대표어만 추리세요
5. **너무 일반적인 키워드**: "시스템", "통합", "기술", "응용", "방법" 등은 OR 묶음 키워드로 쓰지 마세요 (AND 도메인 한정에는 사용 OK)
6. **AND 부분 너무 넓음**: \`(로봇 OR robot*)\` 만으로는 부족 → 도메인 형용사/명사 추가

### 🟢 응집성 + 풍부함 = 좋은 검색식

한 OR 묶음 = **단일 개념의 모든 변형/동의어/약자/하위 개념을 빠짐없이**.

#### ✅ 좋은 예 1 — 강화학습 (12개 키워드)
\`\`\`
(강화학습 OR 심층강화학습 OR 로봇강화학습 OR
 "reinforcement learning" OR "deep reinforcement learning" OR DRL OR
 "policy learning" OR "policy gradient" OR "actor-critic" OR
 PPO OR SAC OR DDPG)
\`\`\`
→ 단일 개념(강화학습)의 한국어 변형 3개 + 영어 변형 3개 + 하위 개념(정책학습/액터크리틱) 3개 + 알고리즘 이름 3개 = **풍부함 OK, 응집성 OK**

#### ✅ 좋은 예 2 — LLM/VLM 기반 로봇 제어 (12개)
\`\`\`
(대규모언어모델 OR 비전언어모델 OR 파운데이션모델 OR LLM OR VLM OR
 "large language model*" OR "vision-language model*" OR
 "foundation model*" OR "language-conditioned*" OR "language grounding" OR
 "multimodal robot*" OR "generalist robot*")
\`\`\`
→ 한국어 3 + 영어 약자 2 + 영어 풀네임 4 + 응용 형태 3 = **모든 표현 형태 포괄**

#### ❌ 나쁜 예 — 키워드 부족
\`\`\`
(파운데이션 모델 OR "foundation model")
\`\`\`
→ LLM, VLM, "foundation models", "generalist robot", "multimodal robot" 등 핵심 변형 누락 = 검색 누락 큼

### 🟢 키워드 수 권장 범위 (목표)
- 한 OR 그룹 (단일 개념): **8~15개** 키워드 — 응집성을 깨지 않는 선에서 최대한 풍부하게
- 소분류 검색식 전체 OR 키워드 합 (모든 그룹 합산): **15~30개**
- 통합 검색식 OR 키워드 총합: **15~25개** (분야 대표어만 — 자식 OR 절대 아님)

**검색 누락이 검색 노이즈보다 위험합니다.** 동의어/변형이 풍부하면 무조건 추가하세요.

### 🟢 키워드 그룹 type (include / exclude)
각 키워드 그룹은 \`type\`을 명시해야 합니다:
- **include**: 검색에 포함할 키워드 (대부분의 그룹). 검색식에서 OR로 결합.
- **exclude**: 노드와 무관한 노이즈를 제거할 키워드. 검색식에서 NOT 절로 결합.

**exclude 그룹 사용 권장 시나리오**:
- 같은 단어가 다른 분야에서도 자주 쓰일 때 (예: "강화학습 기반 로봇 제어" 노드에서 "교육"·"게임" 같은 다른 응용 분야 제거)
- 약자가 다의어일 때 (예: "DRL"이 약학 용어로도 쓰임 → exclude로 "pharmaceut*" 등)
- 노드별로 exclude 그룹은 **0~1개**가 적정 (너무 많으면 검색 누락)

**검색식 재조립 패턴**:
\`\`\`
TIAB=((include1 OR include2 OR ...) AND (domain)) NOT (exclude1 OR exclude2 OR ...)
\`\`\`

### 🟢 키워드를 풍부하게 만드는 5가지 차원
하나의 개념에 대해 아래 차원을 모두 검토:
1. **한국어 변형**: 줄임말/풀이름/외래어 표기 (예: 강화학습 / 심층강화학습 / 로봇강화학습)
2. **영어 풀네임**: \`"reinforcement learning"\`
3. **영어 약자**: DRL, LLM, VLM, PPO, SAC, IRL, BC, LfD
4. **하위 개념/알고리즘**: policy gradient, actor-critic, PPO, SAC
5. **응용 형태**: "multimodal robot*", "language-conditioned*", "generalist robot*"

### 🟢 AND 도메인은 적절히 좁게
\`\`\`
❌ AND (로봇 OR robot*)                           ← 너무 넓음
✅ AND (로봇 OR 매니퓰레이터 OR 제어 OR robot* OR manipulat* OR control*)
                                                    ← 도메인 형용사 추가
\`\`\`

### 🟢 정밀 검색식 = 기본 + IPC AND
basic의 핵심 키워드만 추린 후 IPC AND. precise는 basic보다 OR 키워드 약간 적음 (절반 아님).

\`\`\`
basic:    TIAB=((강화학습 OR 심층강화학습 OR DRL OR "reinforcement learning" OR
                "deep reinforcement learning" OR "policy gradient" OR PPO OR SAC OR DDPG)
              AND (로봇 OR robot* OR manipulat*))
precise:  TIAB=((강화학습 OR "reinforcement learning" OR DRL OR "policy gradient")
              AND (로봇 OR robot* OR manipulat*))
          AND IPC=(B25J9/16 OR G06N3/08 OR G06N20*)
\`\`\`

## WIPS ON 검색 신택스

### 필드 연산자
- \`TIAB=(...)\`: 제목 + 초록 (가장 일반적)
- \`TI=(...)\` / \`AB=(...)\` / \`CL=(...)\`: 제목/초록/청구항
- \`PA=(...)\`: 출원인
- \`IPC=(...)\`: IPC 분류 (예: B25J9/16 — 공백 없음, 슬래시 포함)
- \`CC=(...)\`: CPC 분류
- \`AD=(YYYYMMDD:YYYYMMDD)\`: 출원일 범위

### 연산자
- AND, OR, NOT (대문자)
- 우선순위 명확히 하려면 괄호 사용

### 키워드 작성 규칙
- 한국어: 따옴표 없이 (예: \`강화학습\`)
- 영어 단일어 + 와일드카드: \`robot*\`, \`manipulat*\`, \`control*\`
- 영어 다단어 구문: 따옴표로 묶음 \`"reinforcement learning"\`
- IPC 와일드카드: \`B25J*\`, \`G06N20*\`

## 통합 검색식 작성 가이드

⚠️ **통합 검색식 ≠ 모든 소분류 키워드의 OR**

올바른 패턴: 분야의 **가장 대표적인 8~15개 키워드**만 OR + 도메인 AND + IPC AND

\`\`\`
basic:
  TIAB=((강화학습 OR 모방학습 OR 전이학습 OR 원격조작 OR 파운데이션모델 OR
         "robot learning" OR "reinforcement learning" OR "imitation learning" OR
         teleoperat* OR "sim-to-real" OR "foundation model*")
     AND (로봇 OR robot* OR manipulat*))

precise:
  (basic) AND IPC=(B25J9/16 OR B25J3* OR G06N3/08 OR G06N20*)
\`\`\`

→ 8~15개 분야 대표어만, 통합 검색식 한 번의 호출로 분야 전체 윤곽 파악.

## 작성 규칙 (요약)
- 모든 검색식은 WIPS ON 신택스 그대로 (사용자가 복사 → 붙여넣어 동작)
- 모든 텍스트는 한국어 (영어 키워드는 그대로)
- estimatedHits: 정밀 검색식 기준 합리적 추정 (정수)
- IPC code 표시: \`B25J 9/16\` (공백 포함), 검색식 안에서는 \`B25J9/16\` (공백 없음)
- 키워드 그룹 라벨은 짧고 명확 (예: "강화학습 계열", "정책학습 계열", "알고리즘")

## 검색 팁 작성 예시
- "최근 5년 트렌드 집중하려면 AD=(20200101:20260415) 추가"
- "노이즈 많은 키워드 X는 NOT X로 제거"
- "핵심 출원인 추적용 PA=(...) 식 결합"

응답은 반드시 정의된 JSON 스키마(query_design)를 정확히 따라야 합니다.
`;

// ─────────────────────────────────────────────────────────────────
// JSON Schema — 대/중분류는 헤더만, 소분류만 detail
// ─────────────────────────────────────────────────────────────────

const KEYWORD_GROUP_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    label: {
      type: "string",
      description: "키워드 그룹 라벨 (예: '강화학습 계열', '알고리즘 이름', '응용 형태', '노이즈 제외')",
    },
    type: {
      type: "string",
      enum: ["include", "exclude", "domain"],
      description:
        "include: 개념 키워드 그룹(AND 앞, OR로 결합). domain: 도메인 한정 그룹(AND 뒤 — 분야를 좁히는 한정어, 노드당 1개). exclude: 노이즈 제거 그룹(NOT으로 결합, 0~1개).",
    },
    ko: {
      type: "array",
      description:
        "한국어 키워드 3~6개. 동일 개념의 한국어 변형/줄임말/풀이름/외래어 표기 등 풍부하게.",
      items: { type: "string" },
    },
    en: {
      type: "array",
      description:
        "영어 키워드 3~6개. 풀네임 + 약자 + 응용 형태 모두 포함. 다단어는 따옴표 없이 string 자체 (표시 시 따옴표 처리).",
      items: { type: "string" },
    },
  },
  required: ["label", "type", "ko", "en"],
} as const;

// 소분류 전용 — keywords/ipc/queries 다 포함
const SMALL_NODE_SCHEMA = {
  type: "object",
  additionalProperties: false,
  description: "소분류 leaf 노드 — 키워드/IPC/검색식 모두 포함",
  properties: {
    id: { type: "string", description: "예: A.1.1" },
    name: { type: "string", description: "소분류 기술명 (짧게)" },
    scope: { type: "string", description: "범위 한 줄 설명" },
    keywordGroups: {
      type: "array",
      description:
        "키워드 그룹 2~4개. 각 그룹은 단일 개념의 변형/동의어/하위/응용 형태를 풍부하게 (그룹당 ko 3~6 + en 3~6 = 8~15 키워드). 응집성 + 풍부함 동시.",
      items: KEYWORD_GROUP_SCHEMA,
    },
    ipcCodes: {
      type: "array",
      description: "관련 IPC/CPC 코드 1~5개",
      items: {
        type: "object",
        additionalProperties: false,
        properties: {
          code: { type: "string", description: "예: B25J 9/16 (공백 포함)" },
          desc: { type: "string", description: "한국어 짧은 설명" },
        },
        required: ["code", "desc"],
      },
    },
    queries: {
      type: "object",
      additionalProperties: false,
      description: "WIPS ON 검색식 2종",
      properties: {
        basic: {
          type: "string",
          description:
            "키워드 OR + 도메인 AND. keywordGroups의 모든 키워드를 OR로 묶어 풍부하게 (총 15~30개). 응집성 + 풍부함 동시.",
        },
        precise: {
          type: "string",
          description:
            "basic의 핵심 키워드만 약간 추린 뒤 IPC AND 결합. precise OR 키워드는 basic의 약 70% 수준 (절반 아님).",
        },
      },
      required: ["basic", "precise"],
    },
    estimatedHits: {
      type: "integer",
      description: "정밀 검색식 기준 예상 건수 (정수). 분야 규모 + 검색식 정밀도 고려.",
    },
  },
  required: ["id", "name", "scope", "keywordGroups", "ipcCodes", "queries", "estimatedHits"],
};

// 중분류 — 헤더 + 자식만
const MID_NODE_SCHEMA = {
  type: "object",
  additionalProperties: false,
  description: "중분류 — 분류 헤더 역할 (검색식·키워드 없음)",
  properties: {
    id: { type: "string", description: "예: A.1" },
    name: { type: "string", description: "중분류 기술명" },
    scope: { type: "string", description: "범위 한 줄" },
    estimatedHits: {
      type: "integer",
      description: "자식 소분류 정밀 검색식 건수의 합계 추정 (정수)",
    },
    children: {
      type: "array",
      description: "소분류 2~3개",
      items: SMALL_NODE_SCHEMA,
    },
  },
  required: ["id", "name", "scope", "estimatedHits", "children"],
};

// 대분류 — 헤더 + 자식만
const BIG_NODE_SCHEMA = {
  type: "object",
  additionalProperties: false,
  description: "대분류 — 분류 헤더 역할 (검색식·키워드 없음)",
  properties: {
    id: { type: "string", description: "예: A" },
    name: { type: "string", description: "대분류 기술명" },
    scope: { type: "string", description: "범위 한 줄" },
    estimatedHits: {
      type: "integer",
      description: "자식 중분류 합계 추정 (정수)",
    },
    children: {
      type: "array",
      description: "중분류 2~3개",
      items: MID_NODE_SCHEMA,
    },
  },
  required: ["id", "name", "scope", "estimatedHits", "children"],
};

export const QUERY_DESIGN_JSON_SCHEMA = {
  name: "query_design",
  strict: true,
  schema: {
    type: "object",
    additionalProperties: false,
    properties: {
      category: {
        type: "string",
        description: "분야명. '대분류 > 중분류' 형식.",
      },
      globalKeywords: {
        type: "object",
        additionalProperties: false,
        properties: {
          core: {
            type: "array",
            description: "전체 공통 핵심 키워드 3~5개",
            items: { type: "string" },
          },
          exclude: {
            type: "array",
            description: "전체 제외 키워드 3~5개",
            items: { type: "string" },
          },
        },
        required: ["core", "exclude"],
      },
      taxonomy: {
        type: "array",
        description: "대분류 3~4개",
        items: BIG_NODE_SCHEMA,
      },
      unifiedQuery: {
        type: "object",
        additionalProperties: false,
        description: "통합 검색식. 자식 OR 아님 — 분야 대표 키워드 8~15개만 OR.",
        properties: {
          basic: { type: "string" },
          precise: { type: "string" },
        },
        required: ["basic", "precise"],
      },
      searchTips: {
        type: "array",
        description: "실무 운영 팁 2~4개",
        items: { type: "string" },
      },
    },
    required: [
      "category",
      "globalKeywords",
      "taxonomy",
      "unifiedQuery",
      "searchTips",
    ],
  },
} as const;

// ─────────────────────────────────────────────────────────────────
// 클라이언트/서버 공유 타입
// ─────────────────────────────────────────────────────────────────

export type IpcCode = { code: string; desc: string };

export type KeywordGroup = {
  label: string;
  /** include: 개념(AND 앞, OR결합). domain: 도메인 한정(AND 뒤). exclude: NOT 제외. */
  type?: "include" | "exclude" | "domain";
  ko: string[];
  en: string[];
};

export type NodeQueries = {
  basic: string;
  precise: string;
};

export type SmallNode = {
  id: string;
  name: string;
  scope: string;
  keywordGroups: KeywordGroup[];
  ipcCodes: IpcCode[];
  queries: NodeQueries;
  estimatedHits: number;
};

export type MidNode = {
  id: string;
  name: string;
  scope: string;
  estimatedHits: number;
  children: SmallNode[];
};

export type BigNode = {
  id: string;
  name: string;
  scope: string;
  estimatedHits: number;
  children: MidNode[];
};

export type Stage1Result = {
  /** 검색식 신택스 구분 — WIPS ON = "wips"(기본), Lens.org = "lens", KIPRIS = "kipris". 누락 시 wips. */
  db?: "wips" | "lens" | "kipris";
  category: string;
  globalKeywords: { core: string[]; exclude: string[] };
  taxonomy: BigNode[];
  unifiedQuery: NodeQueries;
  searchTips: string[];
};
