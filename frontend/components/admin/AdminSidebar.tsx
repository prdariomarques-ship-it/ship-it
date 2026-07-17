"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  BarChart3,
  Bot,
  Clock,
  Database,
  LayoutDashboard,
  MessageCircle,
  Newspaper,
  ScrollText,
  Server,
  Settings,
  ShieldCheck,
  Users,
  Wrench,
} from "lucide-react";

import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/admin", label: "Dashboard", icon: LayoutDashboard, exact: true },
  { href: "/admin/briefing", label: "Briefing Diário", icon: Newspaper },
  { href: "/admin/timeline", label: "Timeline", icon: Clock },
  { href: "/admin/agents", label: "Agents", icon: Bot },
  { href: "/admin/tools", label: "Tools", icon: Wrench },
  { href: "/admin/executions", label: "Executions", icon: Activity },
  { href: "/admin/memory", label: "Memory (vector)", icon: Database },
  { href: "/admin/google", label: "Google Workspace", icon: ShieldCheck },
  { href: "/admin/whatsapp", label: "WhatsApp", icon: MessageCircle },
  { href: "/admin/users", label: "Users", icon: Users },
  { href: "/admin/logs", label: "Logs", icon: ScrollText },
  { href: "/admin/metrics", label: "Metrics", icon: BarChart3 },
  { href: "/admin/system", label: "System", icon: Server },
  { href: "/admin/settings", label: "Settings", icon: Settings },
];

export function AdminSidebar() {
  const pathname = usePathname();

  return (
    <nav className="flex h-full w-60 shrink-0 flex-col gap-1 border-r border-border bg-card px-3 py-5">
      <div className="mb-4 flex items-center gap-2 px-3">
        <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-primary-foreground text-sm font-bold">
          D
        </div>
        <div className="flex flex-col leading-none">
          <span className="text-sm font-semibold">Dario OS</span>
          <span className="text-[11px] text-muted-foreground">Admin</span>
        </div>
      </div>

      {NAV_ITEMS.map(({ href, label, icon: Icon, exact }) => {
        const active = exact ? pathname === href : pathname === href || pathname.startsWith(`${href}/`);
        return (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors",
              active
                ? "bg-primary/15 font-medium text-primary"
                : "text-muted-foreground hover:bg-accent hover:text-foreground"
            )}
          >
            <Icon className="h-4 w-4 shrink-0" />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
