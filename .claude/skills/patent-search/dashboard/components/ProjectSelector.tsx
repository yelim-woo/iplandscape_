"use client";

import { useEffect, useRef, useState } from "react";
import type { Project } from "@/lib/stage1-storage";
import { normalizeDb, type Db } from "@/lib/db-config";
import DbBadge from "@/components/DbBadge";

/** 프로젝트의 DB 구분 — 데이터가 없는 빈 프로젝트는 null(배지 숨김) */
function projectDb(p: Project): Db | null {
  if (!p.current && !p.aiOriginal) return null;
  return normalizeDb(p.current?.db ?? p.aiOriginal?.db);
}

type Props = {
  projects: Project[];
  activeId: string | null;
  onSwitch: (id: string) => void;
  onCreate: () => void;
  onRename: (id: string, name: string) => void;
  onDelete: (id: string) => void;
  onDuplicate?: (id: string) => void;
};

export default function ProjectSelector({
  projects,
  activeId,
  onSwitch,
  onCreate,
  onRename,
  onDelete,
  onDuplicate,
}: Props) {
  const [open, setOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState("");

  const wrapRef = useRef<HTMLDivElement>(null);

  const activeProject = projects.find((p) => p.id === activeId) || null;

  // 외부 클릭 닫기
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) {
        setOpen(false);
        setEditingId(null);
      }
    };
    window.addEventListener("click", handler);
    return () => window.removeEventListener("click", handler);
  }, [open]);

  function startEdit(p: Project) {
    setEditingId(p.id);
    setEditingName(p.name);
  }
  function commitEdit() {
    if (editingId && editingName.trim()) {
      onRename(editingId, editingName.trim());
    }
    setEditingId(null);
    setEditingName("");
  }
  function cancelEdit() {
    setEditingId(null);
    setEditingName("");
  }

  function handleDelete(p: Project) {
    if (!confirm(`"${p.name}" 프로젝트를 삭제할까요? 되돌릴 수 없습니다.`)) return;
    onDelete(p.id);
  }

  return (
    <div className="proj-selector" ref={wrapRef}>
      <button
        type="button"
        className="proj-trigger"
        onClick={() => setOpen((v) => !v)}
        title="프로젝트 전환"
      >
        <span className="proj-trigger-icon">📁</span>
        <span className="proj-trigger-name">
          {activeProject?.name || "프로젝트 없음"}
        </span>
        {activeProject && projectDb(activeProject) && (
          <DbBadge db={projectDb(activeProject)!} size="sm" />
        )}
        <span className="proj-trigger-count">
          {projects.length > 1 ? `(${projects.length})` : ""}
        </span>
        <span className="proj-trigger-arrow">▾</span>
      </button>

      {open && (
        <div className="proj-dropdown" onClick={(e) => e.stopPropagation()}>
          <div className="proj-dropdown-head">프로젝트 ({projects.length})</div>

          <div className="proj-list">
            {projects.length === 0 && (
              <div className="proj-empty">아직 프로젝트가 없습니다.</div>
            )}
            {projects.map((p) => {
              const isActive = p.id === activeId;
              const isEditing = editingId === p.id;
              return (
                <div
                  key={p.id}
                  className={`proj-item ${isActive ? "is-active" : ""}`}
                >
                  {isEditing ? (
                    <input
                      autoFocus
                      className="proj-item-edit-input"
                      value={editingName}
                      onChange={(e) => setEditingName(e.target.value)}
                      onBlur={commitEdit}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") commitEdit();
                        if (e.key === "Escape") cancelEdit();
                      }}
                    />
                  ) : (
                    <button
                      type="button"
                      className="proj-item-main"
                      onClick={() => {
                        onSwitch(p.id);
                        setOpen(false);
                      }}
                    >
                      <span className="proj-item-name">
                        {isActive && <span className="proj-item-check">●</span>}
                        {p.name}
                        {projectDb(p) && <DbBadge db={projectDb(p)!} size="sm" />}
                      </span>
                      <span className="proj-item-meta">
                        {p.current ? (
                          <>업데이트 {formatDate(p.updatedAt)}</>
                        ) : (
                          <span style={{ opacity: 0.6 }}>비어있음</span>
                        )}
                      </span>
                    </button>
                  )}
                  {!isEditing && (
                    <div className="proj-item-actions">
                      <button
                        type="button"
                        className="proj-item-action"
                        onClick={() => startEdit(p)}
                        title="이름 변경"
                      >
                        ✏️
                      </button>
                      {onDuplicate && (
                        <button
                          type="button"
                          className="proj-item-action"
                          onClick={() => onDuplicate(p.id)}
                          title="복제"
                        >
                          📑
                        </button>
                      )}
                      <button
                        type="button"
                        className="proj-item-action proj-item-action-danger"
                        onClick={() => handleDelete(p)}
                        title="삭제"
                      >
                        🗑️
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          <div className="proj-dropdown-foot">
            <button
              type="button"
              className="proj-new-btn"
              onClick={() => {
                onCreate();
                setOpen(false);
              }}
            >
              + 새 프로젝트
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    return `${yyyy}-${mm}-${dd}`;
  } catch {
    return iso.slice(0, 10);
  }
}
