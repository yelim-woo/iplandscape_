import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "IP Landscape Workbench",
  description: "정부출연연구기관 연구담당자를 위한 AI 기반 IP Landscape 워크플로우",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
