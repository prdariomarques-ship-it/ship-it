import Sidebar from "@/components/Sidebar";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="layout">
      <Sidebar />
      <main className="content">{children}</main>
    </div>
  );
}
