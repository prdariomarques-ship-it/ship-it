"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/", label: "Início" },
  { href: "/conversas", label: "Conversas" },
  { href: "/agenda", label: "Agenda" },
  { href: "/tarefas", label: "Tarefas" },
  { href: "/loja", label: "Loja" },
  { href: "/igreja", label: "Igreja" },
  { href: "/analytics", label: "Analytics" },
  { href: "/logs", label: "Logs" },
  { href: "/configuracoes", label: "Configurações" },
];

export default function Sidebar() {
  const pathname = usePathname();
  return (
    <nav className="sidebar">
      <div className="brand">Dario OS</div>
      {NAV_ITEMS.map((item) => (
        <Link
          key={item.href}
          href={item.href}
          className={pathname === item.href ? "active" : ""}
        >
          {item.label}
        </Link>
      ))}
    </nav>
  );
}
