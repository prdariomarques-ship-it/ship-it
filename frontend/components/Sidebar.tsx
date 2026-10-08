"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

type NavigationEntry = {
  href?: string;
  label: string;
  disabledReason?: string;
};

// Grupos e rótulos vêm da referência aprovada (proposta-dario-os +
// integração local — ver DARIUS_OS_FRONTEND_STATUS.md). Dois ajustes
// deliberados em relação à cópia local recebida:
//   - Grupo SISTEMA ganhou "Runtime" (/admin/runtime), que existe nesta
//     branch e não na cópia local — preserva funcionalidade já existente
//     aqui, sem inventar nada novo.
//   - O painel de bots financeiros (/admin/monitors) foi deliberadamente
//     deixado fora da navegação: a entrega visual não deve misturar essa
//     frente, por instrução explícita.
const NAV_GROUPS: { title: string; items: NavigationEntry[] }[] = [
  {
    title: "INTELIGÊNCIA FINANCEIRA",
    items: [
      { href: "/", label: "Visão geral" },
      { href: "/mercado-brasil", label: "Mercado · Brasil" },
      { href: "/mercado-global", label: "Mercado Global" },
      { href: "/conversas", label: "Conversas" },
    ],
  },
  {
    title: "PESSOAL",
    items: [
      { href: "/pessoal", label: "Pessoal" },
      { label: "Gêmeo Darius", disabledReason: "Rota dedicada não encontrada" },
      { label: "Conversas pessoais", disabledReason: "Filtro pessoal não comprovado" },
    ],
  },
  {
    title: "ÁREAS DE ATUAÇÃO",
    items: [
      { href: "/igreja", label: "Igreja · Azusa" },
      { href: "/loja", label: "Loja" },
      { label: "B2B", disabledReason: "Rota não encontrada nesta interface" },
    ],
  },
  {
    title: "ORGANIZAÇÃO",
    items: [
      { href: "/agenda", label: "Agenda" },
      { href: "/calendario", label: "Calendário" },
      { href: "/tarefas", label: "Tarefas" },
    ],
  },
  {
    title: "BRIEFINGS E OPERAÇÕES",
    items: [
      { href: "/admin/agents", label: "Agentes de IA" },
      { href: "/admin/executions", label: "Execuções" },
    ],
  },
  {
    title: "SISTEMA",
    items: [
      { href: "/analytics", label: "Analytics" },
      { href: "/admin/whatsapp", label: "WhatsApp / Evolution" },
      { href: "/admin/runtime", label: "Runtime" },
      { href: "/logs", label: "Logs" },
      { href: "/configuracoes", label: "Configurações" },
      { href: "/admin", label: "Admin" },
    ],
  },
];

export default function Sidebar() {
  const pathname = usePathname();
  const navRef = useRef<HTMLElement>(null);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    if (!mobileOpen) return;

    const firstLink = navRef.current?.querySelector<HTMLAnchorElement>("a[href]");
    firstLink?.focus();

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMobileOpen(false);
        menuButtonRef.current?.focus();
        return;
      }

      if (event.key !== "Tab") return;
      const links = navRef.current?.querySelectorAll<HTMLAnchorElement>("a[href]");
      if (!links?.length) return;
      const first = links[0];
      const last = links[links.length - 1];

      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [mobileOpen]);

  const closeAfterNavigation = () => {
    if (!mobileOpen) return;
    setMobileOpen(false);
    menuButtonRef.current?.focus();
  };

  return (
    <>
      <button
        ref={menuButtonRef}
        className="mobile-menu-toggle"
        type="button"
        aria-label={mobileOpen ? "Fechar navegação" : "Abrir navegação"}
        aria-controls="darius-sidebar-nav"
        aria-expanded={mobileOpen}
        onClick={() => setMobileOpen((open) => !open)}
      >
        <span aria-hidden="true">{mobileOpen ? "×" : "☰"}</span>
      </button>

      <button
        className="sidebar-backdrop"
        type="button"
        hidden={!mobileOpen}
        aria-label="Fechar navegação"
        onClick={closeAfterNavigation}
      />

      <div className="sidebar-wrap">
        <nav
          className={`sidebar${mobileOpen ? " is-open" : ""}`}
          id="darius-sidebar-nav"
          ref={navRef}
          aria-label="Navegação principal"
        >
          <Link className="brand" href="/" onClick={closeAfterNavigation}>
            <span className="brand-mark" aria-hidden="true">D</span>
            <span className="brand-copy">
              <strong>Darius OS</strong>
              <small>WORKSPACE</small>
            </span>
          </Link>

          {NAV_GROUPS.map((group) => (
            <section className="sidebar-group" key={group.title} aria-label={group.title}>
              <p className="sidebar-group-label">{group.title}</p>
              {group.items.map((item) => {
                if (!item.href) {
                  return (
                    <span
                      key={item.label}
                      className="sidebar-link sidebar-link-disabled"
                      aria-disabled="true"
                      title={item.disabledReason}
                    >
                      <span>{item.label}</span>
                      <small>{item.disabledReason}</small>
                    </span>
                  );
                }

                const active =
                  item.href === "/"
                    ? pathname === "/"
                    : pathname === item.href || pathname.startsWith(`${item.href}/`);

                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`sidebar-link${active ? " active" : ""}`}
                    aria-current={active ? "page" : undefined}
                    onClick={closeAfterNavigation}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </section>
          ))}
        </nav>
      </div>
    </>
  );
}
