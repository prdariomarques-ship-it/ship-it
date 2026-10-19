"use client";

import { useState } from "react";

import { EmptyState } from "@/components/admin/EmptyState";
import { LoadingRows } from "@/components/admin/LoadingGrid";
import { Badge } from "@/components/admin/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/admin/ui/table";
import { Banner, ErrorLine, FilterSelect, Pager, truncate } from "@/components/darius/common";
import { usePausedConversations, useWhatsAppRouting } from "@/lib/darius-api";
import { formatDateTime } from "@/lib/format";

const PAGE_SIZE = 25;

/**
 * Conversations a human took over. The automation (DARIUS included) stays silent on these until someone resumes
 * them, so this list is where an operator learns why a contact is not being answered. Read-only: resuming happens
 * in the conversation itself, with the revision check that protects an in-flight send.
 */
export function PausedTab() {
  const [instance, setInstance] = useState("");
  const [offset, setOffset] = useState(0);
  const routing = useWhatsAppRouting();
  const { data, isLoading, isError, error } = usePausedConversations({
    instance: instance || undefined,
    limit: PAGE_SIZE,
    offset,
  });
  const instances = routing.data?.instances.map((item) => item.instance) ?? [];

  return (
    <div className="flex flex-col gap-4">
      <Banner tone="info">
        Conversas assumidas por uma pessoa: a automação não responde nelas enquanto estiverem pausadas. O número do
        contato aparece mascarado (últimos 4 dígitos).
      </Banner>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <FilterSelect
          label="Instância"
          value={instance}
          onChange={(value) => {
            setInstance(value);
            setOffset(0);
          }}
          options={instances}
        />
        {data ? <span className="text-sm text-muted-foreground">{data.total} conversa(s) pausada(s)</span> : null}
      </div>

      {isLoading ? (
        <LoadingRows count={4} />
      ) : isError ? (
        <ErrorLine error={error} />
      ) : data && data.items.length === 0 ? (
        <EmptyState title="Nenhuma conversa pausada" description="Nenhum humano assumiu conversas neste filtro." />
      ) : data ? (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Contato</TableHead>
                <TableHead>Instância</TableHead>
                <TableHead>Pausada em</TableHead>
                <TableHead>Motivo</TableHead>
                <TableHead>Envio</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.items.map((item) => (
                <TableRow key={`${item.instance}-${item.contact_id}`}>
                  <TableCell>
                    {item.contact_name ?? `Contato ${item.contact_id}`}
                    {item.phone_tail ? <span className="text-muted-foreground"> · …{item.phone_tail}</span> : null}
                  </TableCell>
                  <TableCell>{item.instance}</TableCell>
                  <TableCell>{item.paused_since ? formatDateTime(item.paused_since) : "indisponível"}</TableCell>
                  <TableCell title={item.reason ?? undefined}>
                    {item.reason ? truncate(item.reason) : <span className="text-muted-foreground">sem motivo registrado</span>}
                    {item.actor_id === null ? <span className="text-muted-foreground"> · automático</span> : null}
                  </TableCell>
                  <TableCell>
                    {item.send_in_flight ? <Badge variant="warning">envio em andamento</Badge> : <Badge variant="outline">livre</Badge>}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <Pager offset={offset} pageSize={PAGE_SIZE} nextOffset={data.next_offset} onChange={setOffset} />
        </>
      ) : null}
    </div>
  );
}
