// ─────────────────────────────────────────────────────────────────
// DB(특허 검색 플랫폼) 설정 — WIPS ON / Lens.org / KIPRIS 분기
//
// patent-search 스킬은 WIPS ON(기본)·Lens.org·KIPRIS 세 DB의 검색식을 설계한다.
// 생성한 stage1 JSON 의 최상위 `db` 필드("wips" | "lens" | "kipris")로 검색식
// 신택스 · 외부 링크 · 라벨을 분기한다. `db` 누락 시 "wips" 로 동작(하위호환).
// ─────────────────────────────────────────────────────────────────

export type Db = "wips" | "lens" | "kipris";

/** db 값 정규화 — 누락/오타 시 wips 로 fallback (기존 patent-search 호환) */
export function normalizeDb(db: unknown): Db {
  return db === "lens" ? "lens" : db === "kipris" ? "kipris" : "wips";
}

export const DB_LABELS: Record<Db, { name: string; openLabel: string; hint: string }> = {
  wips: {
    name: "WIPS ON",
    openLabel: "↗ WIPS ON 열기",
    hint: "[WIPS ON 열기]를 누르면 검색식이 클립보드에 복사되고 새 탭이 열립니다. WIPS ON 검색창에 붙여넣기 하세요.",
  },
  lens: {
    name: "Lens",
    openLabel: "↗ Lens 열기",
    hint: "[Lens 열기]를 누르면 검색식이 클립보드에 복사되고 새 탭이 열립니다. Lens 검색창(Query)에 붙여넣기 하세요.",
  },
  kipris: {
    name: "KIPRIS",
    openLabel: "↗ KIPRIS 열기",
    hint: "[KIPRIS 열기]를 누르면 검색식이 클립보드에 복사되고 새 탭이 열립니다. KIPRIS 스마트검색 입력창에 붙여넣기 하세요.",
  },
};

const WIPS_ON_URL = "https://www.wipson.com/service/mai/main.wips";
const LENS_SEARCH_URL = "https://www.lens.org/lens/search/patent/list?q=";
const KIPRIS_SEARCH_URL = "https://www.kipris.or.kr/khome/search/searchResult.do?queryText=";

/**
 * 검색식을 클립보드에 복사하고 해당 DB 검색 페이지를 새 탭으로 연다.
 * - WIPS ON: 메인 검색 페이지(원내 SSO) — 클립보드 붙여넣기 방식
 * - Lens: q= 파라미터로 검색식을 전달 + 클립보드 백업
 * - KIPRIS: queryText= 파라미터로 스마트검색식 전달 + 클립보드 백업
 */
export function openInDb(db: Db, searchExpr: string) {
  if (typeof navigator !== "undefined" && navigator.clipboard) {
    navigator.clipboard.writeText(searchExpr).catch(() => {});
  }
  if (typeof window === "undefined") return;
  const url =
    db === "lens"
      ? `${LENS_SEARCH_URL}${encodeURIComponent(searchExpr)}`
      : db === "kipris"
      ? `${KIPRIS_SEARCH_URL}${encodeURIComponent(searchExpr)}`
      : WIPS_ON_URL;
  window.open(url, "_blank", "noopener,noreferrer");
}
