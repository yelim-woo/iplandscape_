import { DB_LABELS, normalizeDb, type Db } from "@/lib/db-config";

/**
 * 검색 플랫폼(DB) 배지 — WIPS ON(블루) / Lens(그린).
 * 같은 stage1 대시보드를 wips/lens 스킬이 공용으로 쓰므로
 * 결과 헤더·프로젝트 목록에서 어느 DB용 설계인지 한눈에 구분한다.
 */
export default function DbBadge({
  db,
  size = "md",
}: {
  db: Db | string | undefined;
  size?: "sm" | "md" | "lg";
}) {
  const d = normalizeDb(db);
  const sizeClass = size === "sm" ? "db-badge-sm" : size === "lg" ? "db-badge-lg" : "";
  return (
    <span
      className={`db-badge db-badge-${d} ${sizeClass}`}
      title={`${DB_LABELS[d].name} 검색식`}
    >
      {DB_LABELS[d].name}
    </span>
  );
}
