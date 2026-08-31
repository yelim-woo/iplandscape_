import type { Stage1Result } from "@/lib/prompts/stage1";

/**
 * 한 개의 프로젝트 = 하나의 검색식 설계 작업
 */
export type Project = {
  id: string;
  name: string;
  createdAt: string;
  updatedAt: string;
  /** 스킬이 생성한 JSON 파일명 (중복 감지용) */
  sourceFile?: string;
  inputs: {
    topic: string;
    yearFrom: string;
    yearTo: string;
    countries: string[];
  };
  aiOriginal: Stage1Result | null;
  current: Stage1Result | null;
  modifiedNodeIds: string[];
};

/** localStorage에 저장되는 전체 구조 */
export type ProjectsStore = {
  version: 1;
  activeId: string | null;
  projects: Project[];
};

const STORAGE_KEY = "iplandscape:projects";
const LEGACY_KEY = "iplandscape:stage1:default"; // 이전 단일 슬롯 키

// ──────────────────────────────────────────────────────────────
// ID / 생성 헬퍼
// ──────────────────────────────────────────────────────────────

export function generateProjectId(): string {
  return `p_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

export function createEmptyProject(name: string = "새 프로젝트"): Project {
  const now = new Date().toISOString();
  return {
    id: generateProjectId(),
    name,
    createdAt: now,
    updatedAt: now,
    inputs: {
      topic: "",
      yearFrom: "2020",
      yearTo: "2026",
      countries: ["KR", "US", "JP", "EP"],
    },
    aiOriginal: null,
    current: null,
    modifiedNodeIds: [],
  };
}

export function emptyStore(): ProjectsStore {
  return { version: 1, activeId: null, projects: [] };
}

// ──────────────────────────────────────────────────────────────
// localStorage 로드/저장
// ──────────────────────────────────────────────────────────────

export function loadStore(): ProjectsStore {
  if (typeof window === "undefined") return emptyStore();

  // 1) 새 구조 우선
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as ProjectsStore;
      if (parsed.version === 1 && Array.isArray(parsed.projects)) return parsed;
    }
  } catch {
    // ignore
  }

  // 2) 이전 단일 슬롯 → 첫 프로젝트로 마이그레이션
  try {
    const legacyRaw = window.localStorage.getItem(LEGACY_KEY);
    if (legacyRaw) {
      const legacy = JSON.parse(legacyRaw);
      const project: Project = {
        id: generateProjectId(),
        name: legacy.current?.category || "마이그레이션 프로젝트",
        createdAt: legacy.savedAt || new Date().toISOString(),
        updatedAt: legacy.savedAt || new Date().toISOString(),
        inputs: legacy.inputs ?? {
          topic: "",
          yearFrom: "2020",
          yearTo: "2026",
          countries: ["KR", "US", "JP", "EP"],
        },
        aiOriginal: legacy.aiOriginal ?? null,
        current: legacy.current ?? null,
        modifiedNodeIds: legacy.modifiedNodeIds ?? [],
      };
      const store: ProjectsStore = {
        version: 1,
        activeId: project.id,
        projects: [project],
      };
      saveStore(store);
      window.localStorage.removeItem(LEGACY_KEY);
      return store;
    }
  } catch {
    // ignore
  }

  return emptyStore();
}

export function saveStore(store: ProjectsStore): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
  } catch (e) {
    console.warn("[stage1-storage] save failed", e);
  }
}

// ──────────────────────────────────────────────────────────────
// 깊은 복사
// ──────────────────────────────────────────────────────────────

export function cloneResult(data: Stage1Result): Stage1Result {
  return JSON.parse(JSON.stringify(data));
}

export function cloneProject(p: Project): Project {
  return JSON.parse(JSON.stringify(p));
}

// ──────────────────────────────────────────────────────────────
// JSON Export / Import — 단일 프로젝트 단위
// ──────────────────────────────────────────────────────────────

function slugify(text: string): string {
  return (
    text
      .toLowerCase()
      .replace(/[^a-z0-9가-힣]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 50) || "project"
  );
}

export function exportProjectToFile(project: Project): void {
  if (typeof window === "undefined") return;
  const json = JSON.stringify(project, null, 2);
  const blob = new Blob([json], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  const date = new Date().toISOString().slice(0, 10);
  const slug = slugify(project.name);
  a.href = url;
  a.download = `iplandscape-${slug}-${date}.json`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function importProjectFromFile(file: File): Promise<Project> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const text = reader.result as string;
        const parsed = JSON.parse(text);
        // 새 형식 (Project 단일) 또는 이전 형식 (StoredStage1)
        let project: Project;
        if (parsed.id && parsed.inputs && (parsed.aiOriginal || parsed.current)) {
          // 새 Project 형식
          project = {
            id: generateProjectId(), // 충돌 방지 — 새 ID 부여
            name: parsed.name || "가져온 프로젝트",
            createdAt: parsed.createdAt || new Date().toISOString(),
            updatedAt: new Date().toISOString(),
            inputs: parsed.inputs,
            aiOriginal: parsed.aiOriginal ?? null,
            current: parsed.current ?? null,
            modifiedNodeIds: parsed.modifiedNodeIds ?? [],
          };
        } else if (parsed.version === 1 && parsed.aiOriginal && parsed.current) {
          // 이전 StoredStage1 형식
          project = {
            id: generateProjectId(),
            name: parsed.current?.category || "가져온 프로젝트",
            createdAt: parsed.savedAt || new Date().toISOString(),
            updatedAt: new Date().toISOString(),
            inputs: parsed.inputs,
            aiOriginal: parsed.aiOriginal,
            current: parsed.current,
            modifiedNodeIds: parsed.modifiedNodeIds ?? [],
          };
        } else {
          reject(new Error("지원하지 않는 파일 형식"));
          return;
        }
        resolve(project);
      } catch {
        reject(new Error("JSON 파싱 실패"));
      }
    };
    reader.onerror = () => reject(new Error("파일 읽기 실패"));
    reader.readAsText(file);
  });
}
