import type { IpcCode, KeywordGroup, SmallNode } from "@/lib/prompts/stage1";
import type { Db } from "@/lib/db-config";

/**
 * 사용자가 키워드/IPC 편집 후 검색식을 자동 재조립.
 * AI 원본의 도메인 블록을 유지하고, 키워드 블록만 편집된 keywordGroups 로 새로 조립.
 *
 * db 별 신택스 (셋 다 basic 구조는 `(개념블록) AND (도메인블록) [NOT (제외블록)]`):
 * - wips (WIPS ON): 후위 필드 `.ti./.ab.`, 다단어는 ADJ 체인, IPC `(...).ipc.`, 날짜 @ad:/관할 @cc:
 * - lens (Lens.org): 전위 필드 `title:/abstract:`, 다단어는 "구문", IPC `class_ipcr.symbol:(...)`
 * - kipris (KIPRIS 스마트검색): 키워드 불리언 — OR=`+`/AND=`*`/NOT=`*!`, 그룹 `()`, 다단어는 "구문".
 *     기간은 precise 끝에 `*AD=[YYYYMMDD~YYYYMMDD]`(최근 10년) 포함(허용). 인라인 IPC·항목 한정은
 *     검색창이 거부하므로 KIPRIS 상세검색 폼 입력칸으로. 절단기호 없음(자동절단검색).
 */

// ──────────────────────────────────────────────────────────────
// db별 연산자 (OR 조인 / AND / NOT)
//   wips·lens: 텍스트 연산자(OR/AND/NOT) + 스페이스
//   kipris   : 기호 연산자(+ / * / *!) — 스페이스 없이
// ──────────────────────────────────────────────────────────────

function orSep(db: Db): string {
  return db === "kipris" ? "+" : " OR ";
}
function andOp(db: Db): string {
  return db === "kipris" ? "*" : " AND ";
}
function notOp(db: Db): string {
  return db === "kipris" ? "*!" : " NOT ";
}

// ──────────────────────────────────────────────────────────────
// 키워드 포맷 (db별)
// ──────────────────────────────────────────────────────────────

/** 단일 키워드를 db 규약에 맞게 포맷. WIPS=다단어 ADJ 체인(따옴표 미지원), Lens/KIPRIS=다단어 큰따옴표. */
function formatKeyword(raw: string, db: Db): string {
  const v = raw.trim();
  if (!v) return v;
  if (db === "wips") {
    // WIPS ON: 큰따옴표 구문검색 미지원 → 다단어는 ADJ 체인 (스페이스=OR 이므로)
    return v.includes(" ") ? v.split(/\s+/).join(" ADJ ") : v;
  }
  if (db === "kipris") {
    // KIPRIS: 자동절단검색이 기본 → 절단기호(*,?)를 제거(텍스트 키워드에 `?`는 "특수문자" 오류,
    // `?`는 번호검색 전용). `composite` 만으로 `composites` 등이 자동 매칭됨.
    // 다단어/하이픈/슬래시 포함 구문은 "..." (구문검색).
    const t = v.replace(/[*?]/g, "").trim();
    if (!t) return t;
    return /[\s\-/]/.test(t) ? `"${t}"` : t;
  }
  // Lens: 다단어/하이픈/슬래시 포함 구문은 큰따옴표
  if (v.includes(" ") || v.includes("-") || v.includes("/")) return `"${v}"`;
  return v;
}

function pushKeyword(target: string[], seen: Set<string>, raw: string, db: Db) {
  const v = raw.trim();
  if (!v) return;
  const norm = v.toLowerCase();
  if (seen.has(norm)) return;
  seen.add(norm);
  target.push(formatKeyword(v, db));
}

/** 모든 그룹 키워드를 단일 배열로 (호환용). Lens 는 영어만. */
export function collectKeywords(groups: KeywordGroup[], db: Db = "wips"): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  for (const g of groups) {
    if (g.type === "exclude") continue;
    if (db !== "lens") for (const k of g.ko) pushKeyword(out, seen, k, db);
    for (const k of g.en) pushKeyword(out, seen, k, db);
  }
  return out;
}

/**
 * 타입별 키워드 수집.
 * - include: 개념 블록(AND 앞) / domain: 도메인 한정 블록(AND 뒤) / exclude: NOT 제외
 * db === "lens" 인 경우 한국어 검색에 약하므로 영어(en) 키워드만 사용.
 */
export function collectKeywordsByType(
  groups: KeywordGroup[],
  db: Db = "wips"
): { include: string[]; domain: string[]; exclude: string[] } {
  const include: string[] = [];
  const domain: string[] = [];
  const exclude: string[] = [];
  const seenInc = new Set<string>();
  const seenDom = new Set<string>();
  const seenExc = new Set<string>();
  const useKorean = db !== "lens";
  for (const g of groups) {
    const bucket =
      g.type === "exclude"
        ? { arr: exclude, seen: seenExc }
        : g.type === "domain"
        ? { arr: domain, seen: seenDom }
        : { arr: include, seen: seenInc };
    if (useKorean) for (const k of g.ko) pushKeyword(bucket.arr, bucket.seen, k, db);
    for (const k of g.en) pushKeyword(bucket.arr, bucket.seen, k, db);
  }
  return { include, domain, exclude };
}

// ──────────────────────────────────────────────────────────────
// 필드 블록 (db별)
//   wips  : ((terms).ti. OR (terms).ab.)
//   lens  : (title:(terms) OR abstract:(terms))
//   kipris: (term1+term2+...)   — OR=`+`, 필드지정 없음(자유검색창은 <in>/콤마 거부)
// ──────────────────────────────────────────────────────────────

function fieldBlock(terms: string[], db: Db): string {
  const j = terms.join(orSep(db));
  if (db === "wips") return `((${j}).ti. OR (${j}).ab.)`;
  if (db === "kipris") return `(${j})`;
  return `(title:(${j}) OR abstract:(${j}))`;
}

// ──────────────────────────────────────────────────────────────
// AI 원본 basic 에서 도메인 블록 추출
//   구조: (개념블록) AND (도메인블록) [NOT ...] → 도메인블록 반환
//   레거시 WIPS `TIAB=(...)` 래퍼도 처리
// ──────────────────────────────────────────────────────────────

export function extractDomainAnd(basicQuery: string | undefined, db: Db = "wips"): string {
  const fallback =
    db === "lens" ? "(robot*)" : db === "kipris" ? "(robot)" : fieldBlock(["robot*"], "wips");
  if (!basicQuery) return fallback;
  let inner = basicQuery.trim();
  // 레거시 WIPS: TIAB=(...) 래퍼 벗기기
  const tiab = inner.match(/^TIAB\s*=\s*\(([\s\S]+)\)\s*$/);
  if (tiab) inner = tiab[1].trim();
  // 한 겹 더 균형 괄호로 감싼 경우 벗기기 (KIPRIS는 (terms)<in>(TL,AB) 구조라 벗기지 않음)
  if (db !== "kipris" && inner.startsWith("(") && inner.endsWith(")") && isBalanced(inner.slice(1, -1))) {
    inner = inner.slice(1, -1).trim();
  }
  const domainStart = findDomainStartAfterParenGroup(inner, db);
  if (domainStart < 0) return fallback;
  const domainPart = inner.slice(domainStart).trim();
  return domainPart.startsWith("(") ? domainPart : `(${domainPart})`;
}

function isBalanced(s: string): boolean {
  let depth = 0;
  for (const c of s) {
    if (c === "(") depth++;
    else if (c === ")") depth--;
    if (depth < 0) return false;
  }
  return depth === 0;
}

/**
 * 첫 괄호 그룹 (...) 뒤에 나오는 최상위 AND 연산자 '다음' 위치(도메인 블록 시작) 반환. 없으면 -1.
 * - wips/lens: AND 토큰은 ` AND ` / kipris: `*` (단 NOT `*!` 는 제외).
 * KIPRIS는 필드블록이 `(terms)<in>(TL,AB)` 라 첫 괄호 `(terms)` 뒤가 아니라
 * `(TL,AB)` 괄호 그룹이 닫힌 직후의 최상위 `*` 를 도메인 시작으로 잡는다.
 */
function findDomainStartAfterParenGroup(s: string, db: Db): number {
  let depth = 0;
  let firstParenEnded = false;
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (c === "(") depth++;
    else if (c === ")") {
      depth--;
      if (depth === 0) firstParenEnded = true;
    }
    if (firstParenEnded && depth === 0) {
      const tail = s.slice(i + 1);
      if (db === "kipris") {
        // `*` (AND) 이되 `*!` (NOT) 은 제외
        const m = tail.match(/^\*(?!!)/);
        if (m) return i + 1 + m[0].length;
      } else {
        const m = tail.match(/^\s+AND\s+/i);
        if (m) return i + 1 + m[0].length;
      }
    }
  }
  return -1;
}

// ──────────────────────────────────────────────────────────────
// IPC
// ──────────────────────────────────────────────────────────────

export function normalizeIpcForQuery(code: string): string {
  return code.replace(/\s+/g, "");
}

/** 서브클래스/그룹 코드에 와일드카드 부여. "A61P25" → "A61P25*" */
function ipcWildcard(code: string): string {
  const c = code.replace(/\s+/g, "");
  return c.endsWith("*") ? c : c + "*";
}

/**
 * db별 IPC 절.
 *   wips  : `(A61P25* OR ...).ipc.`
 *   lens  : `class_ipcr.symbol:(...)`
 *   kipris: `(A61P25+...)<in>IPC`  — OR=`+`, KIPRIS IPC는 서브클래스가 계층 매칭되어 절단(`*`) 불필요
 */
function ipcClause(codes: IpcCode[], db: Db): string {
  if (db === "kipris") {
    const part = codes.map((i) => normalizeIpcForQuery(i.code)).join("+");
    return `(${part})<in>IPC`;
  }
  const part = codes.map((i) => ipcWildcard(i.code)).join(" OR ");
  return db === "wips" ? `(${part}).ipc.` : `class_ipcr.symbol:(${part})`;
}

// ──────────────────────────────────────────────────────────────
// precise 끝의 기간·관할 등 부가 필터 보존 (키워드 편집 후에도 유지)
//   Lens  : date_published / jurisdiction / has_full_text ...
//   WIPS  : @ad: / @pd: / @cc: ...
//   KIPRIS: [YYYYMMDD~YYYYMMDD]<in>AD / <in>PD / <in>GD / <in>OPD ...
// ──────────────────────────────────────────────────────────────

/** 최상위 AND 연산자로 분할. wips/lens=` AND `, kipris=`*`(NOT `*!` 도 `*`에서 분리됨). */
function splitTopLevelAnd(s: string, db: Db): string[] {
  const parts: string[] = [];
  let depth = 0;
  let cur = "";
  for (let i = 0; i < s.length; i++) {
    if (db === "kipris") {
      if (depth === 0 && s[i] === "*") {
        parts.push(cur);
        cur = "";
        continue;
      }
    } else if (depth === 0 && s.slice(i, i + 5) === " AND ") {
      parts.push(cur);
      cur = "";
      i += 4;
      continue;
    }
    const c = s[i];
    if (c === "(" || c === "[") depth++;
    else if (c === ")" || c === "]") depth--;
    cur += c;
  }
  parts.push(cur);
  return parts;
}

/**
 * db별 보존 대상 부가 필터 판별 (precise 편집 후에도 유지할 절).
 * ⚠️ wips/lens는 기간(@ad:/date_published: 등)을 보존 대상에서 제외 → 기간 미부착(관할/전문플래그만 유지).
 * KIPRIS만 날짜 필드(`AD=[..]` / `<in>AD`)를 보존(부착 대상).
 */
const FILTER_MATCHERS: Record<Db, (s: string) => boolean> = {
  lens: (s) => ["jurisdiction:", "has_full_text:"].some((p) => s.startsWith(p)),
  wips: (s) => ["@cc:", "@an:"].some((p) => s.startsWith(p)),
  kipris: (s) => /^(AD|PD|GD|OPD)\s*=\s*\[/i.test(s) || /<in>\s*\(?\s*(AD|PD|GD|OPD)\b/i.test(s),
};

/**
 * KIPRIS 출원일 기간 필터: `AD=[ (올해-10)0101 ~ 오늘YYYYMMDD ]`.
 * 현재일자 기준 최근 10년. 브라우저에서 호출되므로 new Date() 사용 가능.
 */
function kiprisAdDateFilter(): string {
  const now = new Date();
  const y = now.getFullYear();
  const mm = String(now.getMonth() + 1).padStart(2, "0");
  const dd = String(now.getDate()).padStart(2, "0");
  return `AD=[${y - 10}0101~${y}${mm}${dd}]`;
}

/**
 * KIPRIS precise에 출원일 기간(`AD=[..]`)이 없으면 최근 10년 필터를 부착(있으면 그대로).
 * AI 생성 JSON 로드 시 정규화에 사용 → Claude가 규칙을 누락해도 화면·[열기]·복사 모두 기간 보장.
 * db !== "kipris" 이거나 빈 문자열이면 원본 그대로.
 */
export function ensureKiprisDate(precise: string | undefined, db: Db): string {
  const p = (precise ?? "").trim();
  if (db !== "kipris" || !p) return p;
  const hasDate = splitTopLevelAnd(p, db)
    .map((s) => s.trim())
    .some((s) => FILTER_MATCHERS.kipris(s));
  return hasDate ? p : `${p}${andOp(db)}${kiprisAdDateFilter()}`;
}

/**
 * WIPS/Lens precise에서 기간 절을 제거. (관할 `@cc:`/`jurisdiction:` 등은 유지.)
 *  - wips: `@ad:[..]` `@pd:[..]` `AD=..` `PD=..`
 *  - lens: `date_published:[..]` `application_reference.date:..` `year_published:..`
 * AI가 기간을 붙여도 로드 시 떼어내 기간 미적용 보장. kipris/빈값이면 원본 그대로.
 */
export function stripPeriodFilter(precise: string | undefined, db: Db): string {
  const p = (precise ?? "").trim();
  if (db === "kipris" || !p) return p;
  const isDate =
    db === "wips"
      ? (s: string) => /^(@(ad|pd):|AD=|PD=)/i.test(s)
      : (s: string) => /^(date_published:|application_reference\.date:|year_published:)/i.test(s);
  const kept = splitTopLevelAnd(p, db)
    .map((s) => s.trim())
    .filter((s) => s && !isDate(s));
  return kept.join(andOp(db));
}

/** AI 원본 precise 에서 기간·관할 등 부가 필터만 추출 ( "AND ..." 형태로 반환, 없으면 "" ). */
export function extractExtraFilters(precise: string | undefined, db: Db = "wips"): string {
  if (!precise) return "";
  const match = FILTER_MATCHERS[db];
  const sep = andOp(db);
  const extras = splitTopLevelAnd(precise, db)
    .map((s) => s.trim())
    .filter((s) => match(s));
  return extras.length ? sep + extras.join(sep) : "";
}

// ──────────────────────────────────────────────────────────────
// basic / precise 자동 재조립
// ──────────────────────────────────────────────────────────────

export type RebuildContext = {
  /** AI 원본 노드 (도메인 블록·부가 필터 추출용) */
  aiOriginal?: SmallNode;
};

export function rebuildBasic(
  node: Pick<SmallNode, "keywordGroups">,
  ctx: RebuildContext,
  db: Db = "wips"
): string {
  const { include, domain, exclude } = collectKeywordsByType(node.keywordGroups, db);
  // include 키워드가 없으면 AI 원본 유지
  if (include.length === 0) return ctx.aiOriginal?.queries.basic ?? "";

  // 도메인 그룹이 있으면 그걸로 블록 구성, 없으면 AI 원본 검색식에서 추출(레거시 호환)
  const domainBlock =
    domain.length > 0 ? fieldBlock(domain, db) : extractDomainAnd(ctx.aiOriginal?.queries.basic, db);
  let inner = domainBlock
    ? `${fieldBlock(include, db)}${andOp(db)}${domainBlock}`
    : fieldBlock(include, db);
  if (exclude.length > 0) inner += `${notOp(db)}${fieldBlock(exclude, db)}`;
  return inner;
}

export function rebuildPrecise(
  node: Pick<SmallNode, "keywordGroups" | "ipcCodes">,
  ctx: RebuildContext,
  db: Db = "wips"
): string {
  const basic = rebuildBasic(node, ctx, db);
  // KIPRIS: 기간은 `*AD=[..]` 로 precise에 포함(허용 확인됨), IPC는 여전히 상세검색 폼.
  // AI 원본 precise에 기간 필터가 있으면 그 값을 보존, 없으면 최근 10년(올해-10~오늘)을 자동 산정해 부착.
  if (db === "kipris") {
    const extras = extractExtraFilters(ctx.aiOriginal?.queries.precise, db);
    return extras ? basic + extras : `${basic}${andOp(db)}${kiprisAdDateFilter()}`;
  }
  // AI 원본 precise 의 기간·관할 등 부가 필터 보존
  const extras = extractExtraFilters(ctx.aiOriginal?.queries.precise, db);
  if (node.ipcCodes.length === 0) return basic + extras;
  return `${basic}${andOp(db)}${ipcClause(node.ipcCodes, db)}${extras}`;
}

/** 노드 전체 재조립 — 검색식만 갱신, 다른 필드는 그대로. */
export function rebuildNode(
  node: SmallNode,
  aiOriginal: SmallNode | undefined,
  db: Db = "wips"
): SmallNode {
  const ctx: RebuildContext = { aiOriginal };
  return {
    ...node,
    queries: {
      basic: rebuildBasic(node, ctx, db),
      precise: rebuildPrecise(node, ctx, db),
    },
  };
}
