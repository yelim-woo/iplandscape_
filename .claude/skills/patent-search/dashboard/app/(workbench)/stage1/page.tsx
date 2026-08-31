"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import ProjectSelector from "@/components/ProjectSelector";
import DbBadge from "@/components/DbBadge";
import { getStageBySlug } from "@/lib/stages";
import type {
  Stage1Result,
  BigNode,
  MidNode,
  SmallNode,
  NodeQueries,
  IpcCode,
  KeywordGroup,
} from "@/lib/prompts/stage1";
import {
  cloneProject,
  cloneResult,
  createEmptyProject,
  emptyStore,
  exportProjectToFile,
  generateProjectId,
  importProjectFromFile,
  loadStore,
  Project,
  ProjectsStore,
  saveStore,
} from "@/lib/stage1-storage";
import { rebuildNode, ensureKiprisDate, stripPeriodFilter } from "@/lib/stage1-rebuild";
import { openInDb, DB_LABELS, normalizeDb, type Db } from "@/lib/db-config";



export default function Stage1Page() {
  const stage = getStageBySlug("stage1")!;

  const [store, setStore] = useState<ProjectsStore>(emptyStore);
  const [hydrated, setHydrated] = useState(false);

  const [error, setError] = useState<string | null>(null);
  const [moreMenuOpen, setMoreMenuOpen] = useState(false);

  const [modalNodeIds, setModalNodeIds] = useState<{
    bigId: string;
    midId: string;
    smallId: string;
  } | null>(null);

  const [confirmAction, setConfirmAction] = useState<null | {
    title: string;
    message: string;
    onConfirm: () => void;
  }>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // ─── 초기 로드 (마이그레이션 포함) + 스킬 결과 자동 감지 ───
  useEffect(() => {
    const loaded = loadStore();
    if (loaded.projects.length === 0) {
      const p = createEmptyProject("새 프로젝트");
      const next: ProjectsStore = { version: 1, activeId: p.id, projects: [p] };
      setStore(next);
      saveStore(next);
    } else if (!loaded.activeId || !loaded.projects.find((p) => p.id === loaded.activeId)) {
      setStore({ ...loaded, activeId: loaded.projects[0].id });
    } else {
      setStore(loaded);
    }
    setHydrated(true);

    // 스킬이 생성한 stage1-results/ 폴더의 모든 JSON 자동 로드
    loadSkillResults();
  }, []);

  async function loadSkillResults() {
    try {
      const listRes = await fetch("/api/stage1-results", { cache: "no-store" });
      if (!listRes.ok) return;
      const { files } = (await listRes.json()) as { files: string[] };
      if (!files || files.length === 0) return;

      const results: { filename: string; data: Stage1Result }[] = [];
      for (const f of files) {
        try {
          const r = await fetch(`/stage1-results/${encodeURIComponent(f)}`, { cache: "no-store" });
          if (!r.ok) continue;
          const data = await r.json();
          // 기간 정규화(결정론적): KIPRIS = 모든 precise에 출원일 기간(AD=[최근10년]) 부착,
          //                        WIPS/Lens = precise에서 기간 절(@ad:/date_published: 등) 제거.
          if (data && data.taxonomy) {
            const ndb = normalizeDb(data.db);
            const fixQ = (q: { basic?: string; precise?: string } | undefined) => {
              if (q && typeof q.precise === "string") {
                q.precise =
                  ndb === "kipris" ? ensureKiprisDate(q.precise, ndb) : stripPeriodFilter(q.precise, ndb);
              }
            };
            const walk = (nodes: { queries?: { basic?: string; precise?: string }; children?: unknown[] }[] | undefined) => {
              if (!Array.isArray(nodes)) return;
              for (const n of nodes) { fixQ(n.queries); walk(n.children as typeof nodes); }
            };
            walk(data.taxonomy);
            fixQ(data.unifiedQuery);
          }
          if (data && data.taxonomy) results.push({ filename: f, data });
        } catch { /* skip */ }
      }
      if (results.length === 0) return;

      setStore((prev) => {
        let updated = { ...prev, projects: [...prev.projects] };
        let latestId = prev.activeId;

        for (const { filename, data } of results) {
          // 파일명에서 프로젝트명 추출: YYYYMMDD_HHmm_주제.json → "YYYY-MM-DD HH:mm 주제"
          const stem = filename.replace(/\.json$/, "");
          const match = stem.match(/^(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})_(.+)$/);
          const projectName = match
            ? `${match[1]}-${match[2]}-${match[3]} ${match[4]}:${match[5]} ${match[6].replace(/_/g, " ")}`
            : data.category || stem;

          // sourceFile(파일명) 기반으로 기존 프로젝트 찾기
          const existingIdx = updated.projects.findIndex(
            (pp) => pp.sourceFile === filename
          );

          if (existingIdx >= 0) {
            const existing = updated.projects[existingIdx];
            updated.projects[existingIdx] = {
              ...existing,
              aiOriginal: data,
              current: cloneResult(data),
              updatedAt: new Date().toISOString(),
            };
            latestId = existing.id;
          } else {
            const p = createEmptyProject(projectName);
            p.sourceFile = filename;
            p.inputs.topic = data.category || "";
            p.aiOriginal = data;
            p.current = cloneResult(data);
            updated.projects.push(p);
            latestId = p.id;
          }
        }

        updated.activeId = latestId;
        saveStore(updated);
        return updated;
      });
      // 결과 로드 완료
    } catch { /* ignore */ }
  }

  // ─── 자동 저장 ───
  useEffect(() => {
    if (!hydrated || store.projects.length === 0) return;
    const t = setTimeout(() => saveStore(store), 300);
    return () => clearTimeout(t);
  }, [store, hydrated]);

  // ─── 더보기 메뉴 외부 클릭 닫기 ───
  useEffect(() => {
    if (!moreMenuOpen) return;
    const handler = () => setMoreMenuOpen(false);
    window.addEventListener("click", handler);
    return () => window.removeEventListener("click", handler);
  }, [moreMenuOpen]);

  const activeProject = useMemo(
    () => store.projects.find((p) => p.id === store.activeId) || null,
    [store]
  );

  // ─── store 변경 헬퍼 ───
  function updateActive(updater: (p: Project) => Project) {
    setStore((s) => ({
      ...s,
      projects: s.projects.map((p) =>
        p.id === s.activeId ? { ...updater(p), updatedAt: new Date().toISOString() } : p
      ),
    }));
  }

  function switchProject(id: string) {
    setStore((s) => ({ ...s, activeId: id }));
    // 프로젝트 전환
    setError(null);
  }

  function createProject() {
    const p = createEmptyProject("새 프로젝트");
    setStore((s) => ({
      version: 1,
      activeId: p.id,
      projects: [...s.projects, p],
    }));
    // 프로젝트 전환
    setError(null);
  }

  function renameProject(id: string, name: string) {
    setStore((s) => ({
      ...s,
      projects: s.projects.map((p) =>
        p.id === id ? { ...p, name, updatedAt: new Date().toISOString() } : p
      ),
    }));
  }

  function deleteProject(id: string) {
    setStore((s) => {
      const remaining = s.projects.filter((p) => p.id !== id);
      if (remaining.length === 0) {
        // 마지막 프로젝트 삭제 시 빈 프로젝트 하나 자동 생성
        const p = createEmptyProject("새 프로젝트");
        return { version: 1, activeId: p.id, projects: [p] };
      }
      return {
        ...s,
        projects: remaining,
        activeId: s.activeId === id ? remaining[0].id : s.activeId,
      };
    });
  }

  function duplicateProject(id: string) {
    setStore((s) => {
      const src = s.projects.find((p) => p.id === id);
      if (!src) return s;
      const copy: Project = {
        ...cloneProject(src),
        id: generateProjectId(),
        name: `${src.name} (복사본)`,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };
      return {
        ...s,
        activeId: copy.id,
        projects: [...s.projects, copy],
      };
    });
  }

  function handleExport() {
    if (!activeProject) return;
    exportProjectToFile(activeProject);
  }

  async function handleImportFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    try {
      const imported = await importProjectFromFile(file);
      setStore((s) => ({
        version: 1,
        activeId: imported.id,
        projects: [...s.projects, imported],
      }));
      // 결과 로드 완료
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "가져오기 실패");
    }
  }

  function handleResetAll() {
    if (!activeProject?.aiOriginal || activeProject.modifiedNodeIds.length === 0) return;
    setConfirmAction({
      title: "전체 원본으로 되돌리기",
      message: `${activeProject.modifiedNodeIds.length}개 소분류 수정을 버리고 AI 원본으로 되돌립니다.`,
      onConfirm: () => {
        updateActive((p) => ({
          ...p,
          current: p.aiOriginal ? cloneResult(p.aiOriginal) : null,
          modifiedNodeIds: [],
        }));
        setConfirmAction(null);
      },
    });
  }

  function updateSmallNode(
    bigId: string,
    midId: string,
    smallId: string,
    updater: (n: SmallNode) => SmallNode
  ) {
    if (!activeProject?.current || !activeProject.aiOriginal) return;
    updateActive((p) => {
      if (!p.current || !p.aiOriginal) return p;
      const next = cloneResult(p.current);
      const big = next.taxonomy.find((b) => b.id === bigId);
      const mid = big?.children.find((m) => m.id === midId);
      const small = mid?.children.find((s) => s.id === smallId);
      if (!small) return p;
      const aiBig = p.aiOriginal.taxonomy.find((b) => b.id === bigId);
      const aiMid = aiBig?.children.find((m) => m.id === midId);
      const aiSmall = aiMid?.children.find((s) => s.id === smallId);
      Object.assign(small, rebuildNode(updater(small), aiSmall, normalizeDb(p.current?.db)));
      const ids = new Set(p.modifiedNodeIds);
      ids.add(smallId);
      return { ...p, current: next, modifiedNodeIds: Array.from(ids) };
    });
  }

  function resetSmallNode(bigId: string, midId: string, smallId: string) {
    if (!activeProject?.current || !activeProject.aiOriginal) return;
    updateActive((p) => {
      if (!p.current || !p.aiOriginal) return p;
      const aiBig = p.aiOriginal.taxonomy.find((b) => b.id === bigId);
      const aiMid = aiBig?.children.find((m) => m.id === midId);
      const aiSmall = aiMid?.children.find((s) => s.id === smallId);
      if (!aiSmall) return p;
      const next = cloneResult(p.current);
      const big = next.taxonomy.find((b) => b.id === bigId);
      const mid = big?.children.find((m) => m.id === midId);
      const small = mid?.children.find((s) => s.id === smallId);
      if (!small) return p;
      Object.assign(small, JSON.parse(JSON.stringify(aiSmall)));
      const ids = new Set(p.modifiedNodeIds);
      ids.delete(smallId);
      return { ...p, current: next, modifiedNodeIds: Array.from(ids) };
    });
  }

  // ─── 입력 동기화 ───
  // 모달 노드 lookup
  const modalNodes = (() => {
    if (!activeProject?.current || !modalNodeIds) return null;
    const big = activeProject.current.taxonomy.find((b) => b.id === modalNodeIds.bigId);
    const mid = big?.children.find((m) => m.id === modalNodeIds.midId);
    const small = mid?.children.find((s) => s.id === modalNodeIds.smallId);
    if (!big || !mid || !small) return null;
    return { big, mid, small };
  })();

  const current = activeProject?.current ?? null;
  const aiOriginal = activeProject?.aiOriginal ?? null;
  const modifiedNodeIds = new Set(activeProject?.modifiedNodeIds ?? []);

  // ─── 렌더 ───
  return (
    <>
      {/* 프로젝트 선택기 — 항상 보임 */}
      {hydrated && (
        <div className="proj-bar">
          <ProjectSelector
            projects={store.projects}
            activeId={store.activeId}
            onSwitch={switchProject}
            onCreate={createProject}
            onRename={renameProject}
            onDelete={deleteProject}
            onDuplicate={duplicateProject}
          />
          <div className="proj-bar-spacer" />
          {current && (
            <div className="topbar-mini-right" style={{ borderBottom: "none", padding: 0, margin: 0 }}>
              <div className="more-menu-wrap" onClick={(e) => e.stopPropagation()}>
                <button
                  type="button"
                  className="link-btn"
                  onClick={() => setMoreMenuOpen((v) => !v)}
                >
                  ⋯ 더보기
                </button>
                {moreMenuOpen && (
                  <div className="more-menu">
                    <button type="button" onClick={() => { setMoreMenuOpen(false); handleExport(); }}>
                      💾 현재 프로젝트 JSON으로 내보내기
                    </button>
                    <button type="button" onClick={() => { setMoreMenuOpen(false); fileInputRef.current?.click(); }}>
                      📂 JSON 가져오기 (새 프로젝트로)
                    </button>
                    {modifiedNodeIds.size > 0 && (
                      <button type="button" onClick={() => { setMoreMenuOpen(false); handleResetAll(); }}>
                        ↩️ 전체 원본으로 ({modifiedNodeIds.size}개 수정 취소)
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* 결과 없을 때 — 안내 카드 */}
      {hydrated && activeProject && !current && (
        <section className="simple-card">
          <h1 className="simple-title">🔍 검색식 설계</h1>
          <p className="simple-sub">
            Claude Code에서 <code>/patent-search</code> 스킬을 실행하면 검색식이 자동으로 생성됩니다.
          </p>
          <div style={{ background: "#f1f5f9", borderRadius: 8, padding: "16px 20px", fontSize: 14, lineHeight: 1.7 }}>
            <strong>사용법</strong>
            <br />
            Claude Code에서 아래와 같이 입력하세요:
            <br />
            <code style={{ background: "#e2e8f0", padding: "2px 6px", borderRadius: 4 }}>
              /patent-search 리튬이온 배터리 실리콘 음극재
            </code>
            <br />
            <br />
            생성이 완료되면 이 페이지에 자동으로 반영됩니다.
          </div>
        </section>
      )}

      {/* 결과 있을 때 — 미니 입력 영역 + 결과 */}
      {hydrated && activeProject && current && (
        <>
          {error && <div className="simple-error">⚠️ {error}</div>}

          <ResultView
            data={current}
            modifiedNodeIds={modifiedNodeIds}
            onOpenNode={(bigId, midId, smallId) => setModalNodeIds({ bigId, midId, smallId })}
          />
        </>
      )}

      <input
        type="file"
        accept="application/json"
        ref={fileInputRef}
        onChange={handleImportFile}
        style={{ display: "none" }}
      />

      {modalNodes && current && aiOriginal && modalNodeIds && (
        <DetailModal
          big={modalNodes.big}
          mid={modalNodes.mid}
          small={modalNodes.small}
          aiOriginalSmall={(() => {
            const aiBig = aiOriginal.taxonomy.find((b) => b.id === modalNodeIds.bigId);
            const aiMid = aiBig?.children.find((m) => m.id === modalNodeIds.midId);
            return aiMid?.children.find((s) => s.id === modalNodeIds.smallId);
          })()}
          isModified={modifiedNodeIds.has(modalNodeIds.smallId)}
          db={normalizeDb(current.db)}
          onUpdate={(updater) => updateSmallNode(modalNodeIds.bigId, modalNodeIds.midId, modalNodeIds.smallId, updater)}
          onResetNode={() => resetSmallNode(modalNodeIds.bigId, modalNodeIds.midId, modalNodeIds.smallId)}
          onClose={() => setModalNodeIds(null)}
        />
      )}

      {confirmAction && (
        <ConfirmModal
          title={confirmAction.title}
          message={confirmAction.message}
          onConfirm={confirmAction.onConfirm}
          onCancel={() => setConfirmAction(null)}
        />
      )}

      {/* unused stage var은 type-only로 사용 */}
      <span style={{ display: "none" }} aria-hidden="true">{stage.title}</span>
    </>
  );
}

// ──────────────────────────────────────────────────────────────
// 결과 화면 — 표 (rowspan)로 트리 표시
// ──────────────────────────────────────────────────────────────

type RowInfo = {
  big: BigNode;
  mid: MidNode;
  small: SmallNode;
  showBig: boolean;
  bigRowSpan: number;
  showMid: boolean;
  midRowSpan: number;
};

function flattenTaxonomy(taxonomy: BigNode[]): RowInfo[] {
  const rows: RowInfo[] = [];
  taxonomy.forEach((big) => {
    if (!big.children || big.children.length === 0) return;
    const bigRowSpan = big.children.reduce((s, m) => s + (m.children?.length || 0), 0);
    if (bigRowSpan === 0) return;
    let bigFirst = true;
    big.children.forEach((mid) => {
      if (!mid.children || mid.children.length === 0) return;
      const midRowSpan = mid.children.length;
      let midFirst = true;
      mid.children.forEach((small) => {
        rows.push({
          big, mid, small,
          showBig: bigFirst, bigRowSpan,
          showMid: midFirst, midRowSpan,
        });
        bigFirst = false;
        midFirst = false;
      });
    });
  });
  return rows;
}

function ResultView({
  data,
  modifiedNodeIds,
  onOpenNode,
}: {
  data: Stage1Result;
  modifiedNodeIds: Set<string>;
  onOpenNode: (bigId: string, midId: string, smallId: string) => void;
}) {
  const today = new Date().toISOString().slice(0, 10);
  const rows = flattenTaxonomy(data.taxonomy);
  return (
    <>
      <div className="result-mini-header">
        <h1 className="result-mini-title" style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          {data.category}
          <DbBadge db={data.db} size="lg" />
        </h1>
        <div className="result-mini-meta">
          생성일 {today} · 소분류 <strong>{rows.length}</strong>개
          {modifiedNodeIds.size > 0 && (
            <span className="modified-pill" style={{ marginLeft: 10 }}>
              ✏ 수정 {modifiedNodeIds.size}개
            </span>
          )}
        </div>
      </div>

      <section className="card mb-md">
        <div className="card-header">
          <h3>🔗 통합 검색식</h3>
        </div>
        <div className="card-body">
          <UnifiedQueries queries={data.unifiedQuery} db={normalizeDb(data.db)} />
        </div>
      </section>

      <section className="card mb-md">
        <div className="card-header">
          <h3>🌳 기술 트리</h3>
          <span className="text-sm text-muted">
            행을 클릭하면 해당 소분류의 키워드·검색식을 보고 편집할 수 있습니다
          </span>
        </div>
        <div className="card-body" style={{ padding: 0 }}>
          <div className="tree-table-wrap">
            <table className="tree-table">
              <thead>
                <tr>
                  <th style={{ width: "16%" }}>대분류</th>
                  <th style={{ width: "18%" }}>중분류</th>
                  <th>소분류</th>
                  <th style={{ width: "44px" }} aria-label="열기"></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => {
                  const isMod = modifiedNodeIds.has(r.small.id);
                  return (
                    <tr
                      key={i}
                      className={`tree-table-row ${isMod ? "is-modified" : ""}`}
                      onClick={() => onOpenNode(r.big.id, r.mid.id, r.small.id)}
                    >
                      {r.showBig && (
                        <td rowSpan={r.bigRowSpan} className="cell-big" onClick={(e) => e.stopPropagation()}>
                          <div className="tax-id tax-id-big">{r.big.id}</div>
                          <div className="cell-name">{r.big.name}</div>
                        </td>
                      )}
                      {r.showMid && (
                        <td rowSpan={r.midRowSpan} className="cell-mid" onClick={(e) => e.stopPropagation()}>
                          <div className="tax-id tax-id-mid">{r.mid.id}</div>
                          <div className="cell-name">{r.mid.name}</div>
                        </td>
                      )}
                      <td className="cell-small">
                        <div className="cell-small-head">
                          <span className="tax-id tax-id-small">{r.small.id}</span>
                          <span className="cell-name">{r.small.name}</span>
                          {isMod && <span className="modified-dot" title="사용자 수정됨" />}
                        </div>
                        <div className="cell-scope">{r.small.scope}</div>
                      </td>
                      <td className="cell-arrow" aria-hidden="true">›</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {data.searchTips && data.searchTips.length > 0 && (
        <details className="card details-card">
          <summary>💡 검색 팁 ({data.searchTips.length}개)</summary>
          <div className="card-body">
            <ul className="search-tips">
              {data.searchTips.map((tip, i) => (
                <li key={i}>{tip}</li>
              ))}
            </ul>
          </div>
        </details>
      )}
    </>
  );
}

function UnifiedQueries({ queries, db }: { queries: NodeQueries; db: Db }) {
  const [tab, setTab] = useState<"basic" | "precise">("basic");
  return (
    <div>
      <div className="flex justify-between items-center mb-sm" style={{ flexWrap: "wrap", gap: 8 }}>
        <div className="tabs" style={{ borderBottom: "none", margin: 0 }}>
          <button
            type="button"
            className={`tab ${tab === "basic" ? "is-active" : ""}`}
            onClick={() => setTab("basic")}
          >
            기본 (넓은 범위)
          </button>
          <button
            type="button"
            className={`tab ${tab === "precise" ? "is-active" : ""}`}
            onClick={() => setTab("precise")}
          >
            정밀 (IPC 결합)
          </button>
        </div>
        <div className="flex gap-sm">
          <button
            type="button"
            className="btn btn-sm"
            onClick={() => navigator.clipboard?.writeText(queries[tab])}
          >
            복사
          </button>
          <button
            type="button"
            className="btn btn-sm btn-primary"
            onClick={() => openInDb(db, queries[tab])}
            title={`검색식을 복사하고 새 탭에서 ${DB_LABELS[db].name}을(를) 엽니다`}
          >
            {DB_LABELS[db].openLabel}
          </button>
        </div>
      </div>
      <pre className="code-block">{queries[tab]}</pre>
      <div className="text-muted text-sm" style={{ marginTop: 6 }}>
        💡 {DB_LABELS[db].hint}
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────
// 상세 모달 — 항상 편집 가능
// ──────────────────────────────────────────────────────────────

function DetailModal({
  big,
  mid,
  small,
  aiOriginalSmall,
  isModified,
  db,
  onUpdate,
  onResetNode,
  onClose,
}: {
  big: BigNode;
  mid: MidNode;
  small: SmallNode;
  aiOriginalSmall: SmallNode | undefined;
  isModified: boolean;
  db: Db;
  onUpdate: (updater: (n: SmallNode) => SmallNode) => void;
  onResetNode: () => void;
  onClose: () => void;
}) {
  const [queryTab, setQueryTab] = useState<"basic" | "precise">("basic");

  // 제외 그룹이 없으면 빈 제외 그룹 자동 추가 (1회만)
  const excludeAdded = useRef(false);
  useEffect(() => {
    if (excludeAdded.current) return;
    const hasExclude = small.keywordGroups.some((g) => g.type === "exclude");
    if (!hasExclude) {
      excludeAdded.current = true;
      onUpdate((n) => ({
        ...n,
        keywordGroups: [
          ...n.keywordGroups,
          { label: "제외 키워드", type: "exclude" as const, ko: [], en: [] },
        ],
      }));
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", handler);
      document.body.style.overflow = "";
    };
  }, [onClose]);

  function copy(text: string) {
    navigator.clipboard?.writeText(text);
  }

  function updateGroup(idx: number, patch: Partial<KeywordGroup>) {
    onUpdate((n) => ({
      ...n,
      keywordGroups: n.keywordGroups.map((g, i) => (i === idx ? { ...g, ...patch } : g)),
    }));
  }
  function addGroup(type: "include" | "exclude" | "domain" = "include") {
    onUpdate((n) => ({
      ...n,
      keywordGroups: [
        ...n.keywordGroups,
        {
          label: type === "exclude" ? "제외 키워드" : type === "domain" ? "도메인 한정" : "새 그룹",
          type,
          ko: [],
          en: [],
        },
      ],
    }));
  }
  function removeGroup(idx: number) {
    onUpdate((n) => ({ ...n, keywordGroups: n.keywordGroups.filter((_, i) => i !== idx) }));
  }
  function toggleGroupType(idx: number) {
    const order = ["include", "domain", "exclude"] as const;
    onUpdate((n) => ({
      ...n,
      keywordGroups: n.keywordGroups.map((g, i) => {
        if (i !== idx) return g;
        const cur = (g.type ?? "include") as (typeof order)[number];
        const next = order[(order.indexOf(cur) + 1) % order.length];
        return { ...g, type: next };
      }),
    }));
  }
  function addKeyword(groupIdx: number, lang: "ko" | "en", value: string) {
    const v = value.trim();
    if (!v) return;
    onUpdate((n) => ({
      ...n,
      keywordGroups: n.keywordGroups.map((g, i) => {
        if (i !== groupIdx) return g;
        if (g[lang].includes(v)) return g;
        return { ...g, [lang]: [...g[lang], v] };
      }),
    }));
  }
  function removeKeyword(groupIdx: number, lang: "ko" | "en", kwIdx: number) {
    onUpdate((n) => ({
      ...n,
      keywordGroups: n.keywordGroups.map((g, i) =>
        i !== groupIdx ? g : { ...g, [lang]: g[lang].filter((_, j) => j !== kwIdx) }
      ),
    }));
  }
  function editKeyword(groupIdx: number, lang: "ko" | "en", kwIdx: number, value: string) {
    const v = value.trim();
    onUpdate((n) => ({
      ...n,
      keywordGroups: n.keywordGroups.map((g, i) => {
        if (i !== groupIdx) return g;
        const updated = [...g[lang]];
        if (!v) updated.splice(kwIdx, 1);
        else updated[kwIdx] = v;
        return { ...g, [lang]: updated };
      }),
    }));
  }

  function normalizeIpc(raw: string): string {
    const s = raw.trim().toUpperCase().replace(/\s+/g, "").replace(/\*$/,"");
    // 서브클래스(4자리: A01B, H04L 등)까지만 사용
    const m = s.match(/^([A-H]\d{2}[A-Z])/);
    if (m) return m[1];
    return s;
  }

  function addIpc(code: string, desc: string) {
    const c = normalizeIpc(code);
    if (!c) return;
    onUpdate((n) => {
      if (n.ipcCodes.find((i) => i.code === c)) return n;
      return { ...n, ipcCodes: [...n.ipcCodes, { code: c, desc: desc.trim() || c }] };
    });
  }
  function removeIpc(idx: number) {
    onUpdate((n) => ({ ...n, ipcCodes: n.ipcCodes.filter((_, i) => i !== idx) }));
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <header className="modal-header">
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="modal-context">
              {big.name} <span className="modal-context-sep">›</span> {mid.name}
            </div>
            <h2 className="modal-title">
              <span className="tax-id tax-id-small">{small.id}</span>
              <span className="modal-title-name">{small.name}</span>
              {isModified && <span className="modified-dot-sm" title="사용자가 수정한 노드" />}
            </h2>
            <div className="modal-scope">{small.scope}</div>
          </div>
          <div className="modal-header-actions">
            {isModified && (
              <button type="button" className="link-btn" onClick={onResetNode} title="이 노드만 AI 원본으로 되돌립니다">
                원본으로
              </button>
            )}
            <button type="button" className="modal-close" onClick={onClose} aria-label="닫기">✕</button>
          </div>
        </header>

        <div className="modal-body">
          <p className="modal-hint">
            키워드를 클릭하면 수정할 수 있고, 변경 시 아래 검색식이 자동으로 갱신됩니다.
          </p>

          <section className="modal-section">
            <div className="modal-section-head">
              <h3 className="modal-section-title">키워드</h3>
              <div className="flex gap-sm">
                <button type="button" className="link-btn" onClick={() => addGroup("include")}>
                  + 그룹 추가
                </button>
                <button
                  type="button"
                  className="link-btn"
                  onClick={() => addGroup("domain")}
                  title="AND 한정 — 분야를 좁히는 도메인어 (노드당 1개 권장)"
                >
                  + 도메인 그룹
                </button>
                <button
                  type="button"
                  className="link-btn link-btn-danger"
                  onClick={() => addGroup("exclude")}
                  title="NOT 조건 — 노이즈가 될 키워드를 검색에서 제외"
                >
                  + 제외 그룹
                </button>
              </div>
            </div>
            <div className="kw-cards">
              {small.keywordGroups.map((g, gi) => (
                <KeywordGroupCard
                  key={gi}
                  group={g}
                  onLabelChange={(v) => updateGroup(gi, { label: v })}
                  onAddKeyword={(lang, v) => addKeyword(gi, lang, v)}
                  onRemoveKeyword={(lang, idx) => removeKeyword(gi, lang, idx)}
                  onEditKeyword={(lang, idx, v) => editKeyword(gi, lang, idx, v)}
                  onRemoveGroup={() => removeGroup(gi)}
                  onToggleType={() => toggleGroupType(gi)}
                />
              ))}
              {small.keywordGroups.length === 0 && (
                <div className="text-soft text-sm" style={{ padding: 12 }}>
                  키워드 그룹이 없습니다. + 그룹 추가로 시작하세요.
                </div>
              )}
            </div>
          </section>

          <section className="modal-section">
            <div className="modal-section-head">
              <h3 className="modal-section-title">IPC / CPC 코드</h3>
            </div>
            <div className="ipc-chip-list">
              {small.ipcCodes.map((ipc: IpcCode, idx) => (
                <span key={ipc.code + idx} className="ipc-chip is-editing" title={ipc.desc}>
                  <code>{ipc.code}</code>
                  <span className="ipc-chip-desc">{ipc.desc}</span>
                  <button type="button" className="ipc-chip-remove" onClick={() => removeIpc(idx)} aria-label="IPC 삭제">✕</button>
                </span>
              ))}
              <IpcAddInline onAdd={addIpc} />
            </div>
          </section>

          <section className="modal-section">
            <div className="modal-section-head">
              <h3 className="modal-section-title">검색식</h3>
              <div className="tabs" style={{ borderBottom: "none", margin: 0 }}>
                <button type="button" className={`tab ${queryTab === "basic" ? "is-active" : ""}`} onClick={() => setQueryTab("basic")}>기본</button>
                <button type="button" className={`tab ${queryTab === "precise" ? "is-active" : ""}`} onClick={() => setQueryTab("precise")}>정밀</button>
              </div>
            </div>
            <pre className="code-block">{small.queries[queryTab]}</pre>
            <div className="flex gap-sm mt-sm">
              <button type="button" className="btn btn-sm" onClick={() => copy(small.queries[queryTab])}>
                복사
              </button>
              <button
                type="button"
                className="btn btn-sm btn-primary"
                onClick={() => openInDb(db, small.queries[queryTab])}
                title={`검색식을 복사하고 새 탭에서 ${DB_LABELS[db].name}을(를) 엽니다`}
              >
                {DB_LABELS[db].openLabel}
              </button>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

function KeywordGroupCard({
  group,
  onLabelChange,
  onAddKeyword,
  onRemoveKeyword,
  onEditKeyword,
  onRemoveGroup,
  onToggleType,
}: {
  group: KeywordGroup;
  onLabelChange: (v: string) => void;
  onAddKeyword: (lang: "ko" | "en", v: string) => void;
  onRemoveKeyword: (lang: "ko" | "en", idx: number) => void;
  onEditKeyword: (lang: "ko" | "en", idx: number, v: string) => void;
  onRemoveGroup: () => void;
  onToggleType: () => void;
}) {
  const isExclude = group.type === "exclude";
  const isDomain = group.type === "domain";
  return (
    <div className={`kw-card is-editing ${isExclude ? "is-exclude" : ""} ${isDomain ? "is-domain" : ""}`} data-type={group.type ?? "include"}>
      <div className="kw-card-head">
        <button
          type="button"
          className={`kw-type-pill ${isExclude ? "is-exclude" : ""} ${isDomain ? "is-domain" : ""}`}
          onClick={onToggleType}
          title="클릭하여 전환: 포함(개념) → 도메인(AND 한정) → NOT 제외"
        >
          {isExclude ? "NOT 제외" : isDomain ? "도메인(AND)" : "포함"}
        </button>
        <input
          className="kw-label-input"
          value={group.label}
          onChange={(e) => onLabelChange(e.target.value)}
          placeholder="카테고리명"
        />
        <button type="button" className="kw-card-delete" onClick={onRemoveGroup} title="그룹 삭제">
          🗑️
        </button>
      </div>

      <div className="kw-card-body">
        <div className="kw-row">
          <span className="kw-row-tag">한국어</span>
          <div className="kw-chip-list">
            {group.ko.map((k, i) => (
              <EditableKeywordChip key={i} value={k} lang="ko" onEdit={(v) => onEditKeyword("ko", i, v)} onRemove={() => onRemoveKeyword("ko", i)} />
            ))}
            <KeywordAddInline placeholder="+ 추가" onAdd={(v) => onAddKeyword("ko", v)} />
          </div>
        </div>
        <div className="kw-row">
          <span className="kw-row-tag">영어</span>
          <div className="kw-chip-list">
            {group.en.map((k, i) => (
              <EditableKeywordChip key={i} value={k} lang="en" onEdit={(v) => onEditKeyword("en", i, v)} onRemove={() => onRemoveKeyword("en", i)} />
            ))}
            <KeywordAddInline placeholder="+ 추가" onAdd={(v) => onAddKeyword("en", v)} />
          </div>
        </div>
      </div>
    </div>
  );
}

function EditableKeywordChip({
  value,
  lang,
  onEdit,
  onRemove,
}: {
  value: string;
  lang: "ko" | "en";
  onEdit: (v: string) => void;
  onRemove: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => setDraft(value), [value]);
  useEffect(() => { if (editing) inputRef.current?.focus(); }, [editing]);

  function commit() {
    if (draft.trim() === value) {
      setEditing(false);
      return;
    }
    onEdit(draft);
    setEditing(false);
  }

  if (editing) {
    return (
      <input
        ref={inputRef}
        className="kw-chip-edit-input"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") commit();
          if (e.key === "Escape") { setDraft(value); setEditing(false); }
        }}
      />
    );
  }

  const displayValue = lang === "en" && value.includes(" ") ? `"${value}"` : value;

  return (
    <span className={`kw-chip kw-chip-${lang} is-editable`}>
      <span className="kw-chip-text" onClick={() => setEditing(true)} title="클릭해서 수정">
        {displayValue}
      </span>
      <button type="button" className="kw-chip-remove" onClick={onRemove} aria-label="삭제">✕</button>
    </span>
  );
}

function KeywordAddInline({ placeholder, onAdd }: { placeholder: string; onAdd: (v: string) => void }) {
  const [draft, setDraft] = useState("");
  function commit() {
    if (!draft.trim()) return;
    onAdd(draft);
    setDraft("");
  }
  return (
    <input
      className="kw-chip-add-input"
      placeholder={placeholder}
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); commit(); } }}
    />
  );
}

function IpcAddInline({ onAdd }: { onAdd: (code: string, desc: string) => void }) {
  const [code, setCode] = useState("");
  function commit() {
    if (!code.trim()) return;
    onAdd(code, "");
    setCode("");
  }
  return (
    <span className="ipc-add-inline">
      <input
        className="kw-chip-add-input"
        placeholder="+ IPC (예: B25J)"
        value={code}
        onChange={(e) => setCode(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter") commit(); }}
        onBlur={commit}
        style={{ width: 160 }}
      />
    </span>
  );
}

function ConfirmModal({
  title,
  message,
  onConfirm,
  onCancel,
}: {
  title: string;
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onCancel]);

  return (
    <div className="modal-overlay" onClick={onCancel} style={{ zIndex: 110 }}>
      <div className="confirm-modal" onClick={(e) => e.stopPropagation()}>
        <h3 className="confirm-title">⚠️ {title}</h3>
        <p className="confirm-message">{message}</p>
        <div className="confirm-actions">
          <button type="button" className="btn" onClick={onCancel}>취소</button>
          <button type="button" className="btn btn-danger-outline" onClick={onConfirm}>계속</button>
        </div>
      </div>
    </div>
  );
}
