"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

const NAV_ITEMS = [
  { href: "/", label: "Início" },
  { href: "/conversas", label: "Conversas" },
  { href: "/agenda", label: "Agenda" },
  { href: "/calendario", label: "Calendário" },
  { href: "/tarefas", label: "Tarefas" },
  { href: "/metas", label: "Metas" },
  { href: "/notas", label: "Notas" },
  { href: "/loja", label: "Loja" },
  { href: "/igreja", label: "Igreja" },
  { href: "/analytics", label: "Analytics" },
  { href: "/admin/logs", label: "Logs" },
  { href: "/configuracoes", label: "Configurações" },
  { href: "/admin", label: "Admin" },
];

export default function Sidebar() {
  const pathname = usePathname();
  const navRef = useRef<HTMLElement>(null);
  const [canScroll, setCanScroll] = useState(false);

  useEffect(() => {
    const el = navRef.current;
    if (!el) return;
    const check = () => setCanScroll(el.scrollWidth > el.clientWidth);
    check();
    const observer = new ResizeObserver(check);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <div className="sidebar-wrap">
      <nav className="sidebar" ref={navRef}>
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
      {/* Below 860px .sidebar becomes a horizontally-scrolling bar (9 of 12
          items sit off-screen at rest) with no hint that it scrolls —
          confirmed reachable only by testing an actual swipe
          (HOMOLOGATION_REPORT_v1.3.1.md). Only shown when there's actually
          more to scroll to, and sits over the nav rather than inside it so
          it doesn't scroll away with the content. */}
      {canScroll && <div className="sidebar-scroll-hint" aria-hidden="true" />}
    </div>
  );
}
