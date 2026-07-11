"use client";

import { useState } from "react";

import { Badge } from "@/components/admin/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/admin/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/admin/ui/table";
import { EmptyState } from "@/components/admin/EmptyState";
import { formatNumber, formatRelativeTime } from "@/lib/format";
import type { ToolAdminInfo } from "@/lib/admin-types";

export function ToolTable({ tools }: { tools: ToolAdminInfo[] }) {
  const [selected, setSelected] = useState<ToolAdminInfo | null>(null);

  if (tools.length === 0) {
    return <EmptyState title="Nenhuma tool registrada" />;
  }

  return (
    <>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Nome</TableHead>
            <TableHead>Categoria</TableHead>
            <TableHead>Agente(s)</TableHead>
            <TableHead>Permissões</TableHead>
            <TableHead className="text-right">Execuções</TableHead>
            <TableHead className="text-right">Falhas</TableHead>
            <TableHead>Última chamada</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {tools.map((tool) => (
            <TableRow
              key={tool.name}
              className="cursor-pointer"
              onClick={() => setSelected(tool)}
              tabIndex={0}
              onKeyDown={(event) => event.key === "Enter" && setSelected(tool)}
            >
              <TableCell className="font-medium">{tool.name}</TableCell>
              <TableCell>
                <Badge variant="secondary">{tool.category}</Badge>
              </TableCell>
              <TableCell className="text-muted-foreground">
                {tool.agents.length > 0 ? tool.agents.join(", ") : "—"}
              </TableCell>
              <TableCell className="text-muted-foreground">{tool.permissions ?? "não disponível"}</TableCell>
              <TableCell className="text-right">
                {tool.calls_total !== null ? formatNumber(tool.calls_total) : "não disponível"}
              </TableCell>
              <TableCell className="text-right">
                {tool.calls_error !== null ? formatNumber(tool.calls_error) : "não disponível"}
              </TableCell>
              <TableCell className="text-muted-foreground">
                {tool.last_call ? formatRelativeTime(tool.last_call) : "não disponível"}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      <Dialog open={selected !== null} onOpenChange={(open) => !open && setSelected(null)}>
        <DialogContent>
          {selected ? (
            <>
              <DialogHeader>
                <DialogTitle>{selected.name}</DialogTitle>
                <DialogDescription>{selected.description}</DialogDescription>
              </DialogHeader>
              <div className="flex flex-col gap-3">
                <div>
                  <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Schema JSON (input)
                  </p>
                  <pre className="admin-scroll max-h-64 overflow-auto rounded-md border border-border bg-background p-3 text-xs">
                    {JSON.stringify(selected.parameters, null, 2)}
                  </pre>
                </div>
                <div>
                  <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Output</p>
                  <p className="text-xs text-muted-foreground">
                    Não há exemplos de input/output reais armazenados — não existe uma tabela de auditoria de
                    execuções por tool nesta versão (ver docs/DASHBOARD.md). O schema acima é o contrato JSON
                    exposto ao modelo.
                  </p>
                </div>
              </div>
            </>
          ) : null}
        </DialogContent>
      </Dialog>
    </>
  );
}
