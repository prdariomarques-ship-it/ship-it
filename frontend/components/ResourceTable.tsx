"use client";

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

  if (loading) return <p className="muted">Carregando…</p>;
  if (error) return <p className="error">Erro: {error}</p>;
  if (!data || data.length === 0) return <p className="muted">{emptyMessage}</p>;

  return (
    <div className="card">
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
  );
}
