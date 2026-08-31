export type Stage = {
  num: number;
  slug: string;
  title: string;
  href: string;
  eyebrow: string;
  lead: string;
  roles: { ai: string; user: string };
  implemented: boolean;
};

export const STAGES: Stage[] = [
  {
    num: 1,
    slug: "stage1",
    title: "검색식 설계",
    href: "/stage1",
    eyebrow: "STAGE 1 · Search Query Design",
    lead: "연구 주제를 자연어로 입력하면 AI가 키워드 맵·IPC/CPC 코드·DB별 Boolean 검색식을 자동 생성합니다.",
    roles: {
      ai: "🤖 AI: 검색식 생성, 키워드 확장, 코드 매칭",
      user: "👤 사용자: 기술 범위 확정, 검색식 최종 승인",
    },
    implemented: true,
  },
];

export function getStageBySlug(slug: string): Stage | undefined {
  return STAGES.find((s) => s.slug === slug);
}
