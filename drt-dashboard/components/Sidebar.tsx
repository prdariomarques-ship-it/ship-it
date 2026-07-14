"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Home,
  Activity,
  Play,
  Zap,
  AlertCircle,
  Settings,
  FileText,
  Database,
} from "lucide-react";

const NAVIGATION = [
  { name: "Home", href: "/", icon: Home },
  { name: "Executions", href: "/executions", icon: Activity },
  { name: "Workflows", href: "/workflows", icon: Play },
  { name: "Audit", href: "/audit", icon: AlertCircle },
  { name: "System Health", href: "/system", icon: Zap },
  { name: "API", href: "/api", icon: Database },
  { name: "Logs", href: "/logs", icon: FileText },
  { name: "Settings", href: "/settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-64 bg-drt-900 border-r border-drt-800 flex flex-col">
      <div className="p-6 border-b border-drt-800">
        <div className="flex items-center gap-2 mb-1">
          <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
          <h1 className="text-xl font-bold text-white">DRT Runtime</h1>
        </div>
        <p className="text-xs text-drt-400">v1.0.0-LTS</p>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1">
        {NAVIGATION.map((item) => {
          const isActive = pathname === item.href;
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? "bg-drt-800 text-white"
                  : "text-drt-400 hover:bg-drt-800 hover:text-drt-100"
              }`}
            >
              <Icon className="w-4 h-4" />
              {item.name}
            </Link>
          );
        })}
      </nav>

      <div className="p-4 border-t border-drt-800">
        <div className="bg-drt-800 rounded-lg p-3">
          <p className="text-xs text-drt-300 font-semibold mb-2">
            Long-Term Support
          </p>
          <p className="text-xs text-drt-400">
            2026-07-14 to 2028-01-14
          </p>
        </div>
      </div>
    </aside>
  );
}
