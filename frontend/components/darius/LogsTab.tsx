"use client";

import { EmptyState } from "@/components/admin/EmptyState";
import { LoadingRows } from "@/components/admin/LoadingGrid";
import { Badge } from "@/components/admin/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/admin/ui/table";
import { ErrorLine } from "@/components/darius/common";
import { useDariusLogs } from "@/lib/darius-api";
import { formatDateTime } from "@/lib/format";

const LEVEL_VARIANT: Record<string, "destructive" | "warning" | "secondary"> = {
  error: "destructive",
  critical: "destructive",
  warning: "warning",
};

/** Audit trail: DARIUS decisions (with the admin user), the WhatsApp->DARIUS flow and suspension changes. */
export function LogsTab() {
  const { entries, isLoading, isError, error } = useDariusLogs(100);

  if (isLoading) return <LoadingRows count={5} />;
  if (isError) return <ErrorLine error={error} />;
  if (entries.length === 0) {
    return <EmptyState title="Sem registros" description="Nenhuma decisão, suspensão ou mensagem roteada foi registrada." />;
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Quando</TableHead>
          <TableHead>Nível</TableHead>
          <TableHead>Origem</TableHead>
          <TableHead>Mensagem</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {entries.map((entry) => (
          <TableRow key={`${entry.source}-${entry.id}`}>
            <TableCell>{formatDateTime(entry.created_at)}</TableCell>
            <TableCell>
              <Badge variant={LEVEL_VARIANT[entry.level] ?? "secondary"}>{entry.level}</Badge>
            </TableCell>
            <TableCell className="font-mono text-xs">{entry.source}</TableCell>
            <TableCell>{entry.message}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
