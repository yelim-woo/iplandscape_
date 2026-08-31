"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { STAGES } from "@/lib/stages";

export default function Sidebar() {
  const pathname = usePathname();
  const match = pathname?.match(/\/stage(\d)/);
  const currentNum = match ? parseInt(match[1], 10) : 0;

  return (
    <aside className="sidebar">
      <Link href="/stage1" className="brand">
        <span className="brand-mark">🔍</span>
        <span>
          IP Landscape
          <br />
          <small style={{ fontWeight: 400, color: "#94a3b8", fontSize: 11 }}>특허 분석 워크벤치</small>
        </span>
      </Link>

      <ul className="stepper">
        {STAGES.map((s) => {
          const isActive = s.num === currentNum;

          return (
            <li key={s.num}>
              <Link href={s.href} className={isActive ? "is-active" : ""}>
                <span className="step-num">{s.num}</span>
                <span className="step-title">{s.num}. {s.title}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
