import Sidebar from "@/components/Sidebar";

export default function WorkbenchLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className="app">
      <Sidebar />
      <div className="main">
        <main className="content">{children}</main>
      </div>
    </div>
  );
}
