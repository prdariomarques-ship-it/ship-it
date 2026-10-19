"use client";

import { useState } from "react";

import { EmptyState } from "@/components/admin/EmptyState";
import { LoadingRows } from "@/components/admin/LoadingGrid";
import { Badge } from "@/components/admin/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/admin/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/admin/ui/table";
import { Banner, ErrorLine, FilterSelect, LinkStatusBadge, Pager, truncate } from "@/components/darius/common";
import { useWhatsAppLinks, useWhatsAppRouting } from "@/lib/darius-api";
import { WHATSAPP_LINK_STATUSES } from "@/lib/darius-types";
import { formatDateTime } from "@/lib/format";

const PAGE_SIZE = 25;

function RoutingCard() {
  const { data, isLoading, isError, error } = useWhatsAppRouting();
  return (
    <Card>
      <CardHeader>
        <CardTitle>Instâncias e roteamento</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {isLoading ? (
          <LoadingRows count={3} />
        ) : isError ? (
          <ErrorLine error={error} />
        ) : data ? (
          <>
            {!data.enabled ? (
              <Banner tone="info">
                O roteamento WhatsApp→DARIUS está <strong>desligado</strong> (flag). Todas as instâncias seguem o
                fluxo local.
              </Banner>
            ) : !data.darius_configured ? (
              <Banner tone="warning">
                Roteamento ligado, mas o DARIUS não está configurado (URL/credencial). As instâncias roteadas não
                respondem automaticamente.
              </Banner>
            ) : null}
            {data.global_suspended ? (
              <Banner tone="destructive" role="alert">
                Automação suspensa globalmente: {data.global_suspension_reason ?? "motivo não informado"}.
              </Banner>
            ) : null}
            {data.unknown_routed_instances.length > 0 ? (
              <Banner tone="warning">
                Roteadas na configuração, mas não reconhecidas como instância: {data.unknown_routed_instances.join(", ")}.
              </Banner>
            ) : null}
            {data.instances.length === 0 ? (
              <EmptyState compact title="Nenhuma instância configurada" />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Instância</TableHead>
                    <TableHead>Fluxo</TableHead>
                    <TableHead>Automação</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.instances.map((item) => (
                    <TableRow key={item.instance}>
                      <TableCell className="font-medium">{item.instance}</TableCell>
                      <TableCell>
                        <Badge variant={item.routed_to_darius ? "default" : "outline"}>
                          {item.routed_to_darius ? "DARIUS" : "fluxo local"}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {item.suspended ? (
                          <Badge variant="destructive" title={item.suspension_reason ?? undefined}>
                            suspensa{item.suspension_reason ? `: ${truncate(item.suspension_reason, 40)}` : ""}
                          </Badge>
                        ) : (
                          <Badge variant="success">ativa</Badge>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
            <p className="text-xs text-muted-foreground">
              Janela de resposta: {Math.round(data.reply_timeout_seconds / 60)} min. Sem resposta dentro dela, nada é
              enviado depois.
            </p>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}

function LinksCard() {
  const [status, setStatus] = useState("");
  const [instance, setInstance] = useState("");
  const [offset, setOffset] = useState(0);
  const routing = useWhatsAppRouting();
  const { data, isLoading, isError, error } = useWhatsAppLinks({
    status: status || undefined,
    instance: instance || undefined,
    limit: PAGE_SIZE,
    offset,
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Mensagens → tarefas DARIUS</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <FilterSelect
            label="Estado"
            value={status}
            onChange={(value) => {
              setStatus(value);
              setOffset(0);
            }}
            options={WHATSAPP_LINK_STATUSES}
          />
          <FilterSelect
            label="Instância"
            value={instance}
            onChange={(value) => {
              setInstance(value);
              setOffset(0);
            }}
            options={routing.data?.instances.map((item) => item.instance) ?? []}
          />
        </div>
        {data && Object.keys(data.counts).length > 0 ? (
          <div className="flex flex-wrap gap-2" aria-label="Totais por estado">
            {Object.entries(data.counts).map(([key, count]) => (
              <Badge key={key} variant="outline">
                {key}: {count}
              </Badge>
            ))}
          </div>
        ) : null}
        {isLoading ? (
          <LoadingRows count={4} />
        ) : isError ? (
          <ErrorLine error={error} />
        ) : data && data.items.length === 0 ? (
          <EmptyState
            title="Nenhuma mensagem roteada"
            description="Ainda não houve mensagem tratada pelo fluxo DARIUS neste filtro."
          />
        ) : data ? (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Quando</TableHead>
                  <TableHead>Instância</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead>Tarefa DARIUS</TableHead>
                  <TableHead>Tentativas</TableHead>
                  <TableHead>Erro</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.map((link) => (
                  <TableRow key={link.id}>
                    <TableCell>{formatDateTime(link.created_at)}</TableCell>
                    <TableCell>{link.instance}</TableCell>
                    <TableCell>
                      <LinkStatusBadge status={link.status} />
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {link.darius_task_id ?? "—"}
                      {link.darius_status ? ` (${link.darius_status})` : ""}
                    </TableCell>
                    <TableCell>{link.attempts}</TableCell>
                    <TableCell className="max-w-xs text-xs text-destructive" title={link.last_error ?? undefined}>
                      {link.last_error ? truncate(link.last_error, 60) : ""}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <Pager offset={offset} pageSize={PAGE_SIZE} nextOffset={data.next_offset} onChange={setOffset} />
          </>
        ) : null}
        <p className="text-xs text-muted-foreground">
          Esta trilha guarda ids, estados e tamanhos. O texto das mensagens e das respostas não é armazenado nem exibido.
        </p>
      </CardContent>
    </Card>
  );
}

export function WhatsAppTab() {
  return (
    <div className="flex flex-col gap-4">
      <RoutingCard />
      <LinksCard />
    </div>
  );
}
