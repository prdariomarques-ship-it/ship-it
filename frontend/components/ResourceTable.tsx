"use client";

import { useEffect, useRef, useState } from "react";

import { useApi } from "@/hooks/useApi";

interface Column {
  key: string;
  label: string;
  render?: (value: unknown, row: Record<string, unknown>) => React.ReactNode;
}

export default function ResourceTable({
  path,
  columns,
  emptyMessage = "Nenhum registro encontrado.",
}: {
  path: string;
  columns: Column[];
  emptyMessage?: string;
}) {
  const { data, loading, error } = useApi<Record<string, unknown>[]>(path);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [canScroll, setCanScroll] = useState(false);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    setCanScroll(el.scrollWidth > el.clientWidth);
  }, [data]);

  if (loading) return <p className="muted">Carregando…</p>;
  if (error) return <p className="error">Erro: {error}</p>;
  if (!data || data.length === 0) return <p className="muted">{emptyMessage}</p>;

  return (
    <div className="card">
      <div className="table-scroll" ref={scrollRef}>
        <table>
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column.key}>{column.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.map((row) => (
              <tr key={String(row.id)}>
                {columns.map((column) => (
                  <td key={column.key}>
                    {column.render
                      ? column.render(row[column.key], row)
                      : String(row[column.key] ?? "—")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {/* Table itself scrolls fine without this — but nothing hinted that it
          could, so a user on a narrow screen just saw truncated columns
          (confirmed in HOMOLOGATION_REPORT_v1.3.1.md). Only shown when the
          table is actually wider than its container. */}
      {canScroll && <p className="table-scroll-hint">← arraste para o lado para ver mais →</p>}
    </div>
  );
}
