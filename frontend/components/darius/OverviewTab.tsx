"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/admin/ui/card";
import { Unavailable } from "@/components/darius/common";
import { DariusStatusCard } from "@/components/darius/DariusStatusCard";
import { useDariusTasks, useSuspension, useWhatsAppLinks, useWhatsAppRouting } from "@/lib/darius-api";

function Figure({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{label}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-semibold">{children}</div>
        {hint ? <p className="mt-1 text-xs text-muted-foreground">{hint}</p> : null}
      </CardContent>
    </Card>
  );
}

/** Every figure comes from its own endpoint; a failed read shows "indisponível", never 0. */
export function OverviewTab({ onOpen }: { onOpen: (tab: "approvals" | "whatsapp" | "suspension") => void }) {
  const paused = useDariusTasks({ status: "PAUSED", limit: 1 });
  const links = useWhatsAppLinks({ limit: 1 });
  const routing = useWhatsAppRouting();
  const suspension = useSuspension();

  // react-query keeps the last good `data` when a refetch fails. A figure from before the outage must not pass as
  // current, so a query in error is treated as having no value at all.
  const pausedData = paused.isError ? undefined : paused.data;
  const linksData = links.isError ? undefined : links.data;
  const suspensionData = suspension.isError ? undefined : suspension.data;

  const failedLinks = (linksData?.counts.failed ?? 0) + (linksData?.counts.expired ?? 0);
  const suspendedScopes = suspensionData
    ? suspensionData.suspended_instances.length + (suspensionData.global_suspended ? 1 : 0)
    : null;

  return (
    <div className="flex flex-col gap-4">
      <DariusStatusCard />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <button type="button" className="text-left" onClick={() => onOpen("approvals")} aria-label="Abrir aprovações">
          <Figure label="Aguardando aprovação" hint="tarefas em PAUSED no DARIUS">
            {pausedData ? pausedData.total : <Unavailable reason={paused.isLoading ? "carregando" : "DARIUS não respondeu"} />}
          </Figure>
        </button>
        <button type="button" className="text-left" onClick={() => onOpen("whatsapp")} aria-label="Abrir WhatsApp">
          <Figure label="WhatsApp → DARIUS" hint="mensagens roteadas (total registrado)">
            {linksData ? (
              Object.values(linksData.counts).reduce((sum, value) => sum + value, 0)
            ) : (
              <Unavailable reason={links.isLoading ? "carregando" : "leitura falhou"} />
            )}
          </Figure>
        </button>
        <Figure label="Falhas / expiradas" hint="mensagens roteadas sem resposta enviada">
          {linksData ? failedLinks : <Unavailable reason={links.isLoading ? "carregando" : "leitura falhou"} />}
        </Figure>
        <button type="button" className="text-left" onClick={() => onOpen("suspension")} aria-label="Abrir suspensão">
          <Figure label="Escopos suspensos" hint={suspensionData?.global_suspended ? "inclui suspensão global" : "global e instâncias"}>
            {suspendedScopes !== null ? suspendedScopes : <Unavailable reason={suspension.isLoading ? "carregando" : "leitura falhou"} />}
          </Figure>
        </button>
      </div>
      {routing.data && !routing.data.enabled ? (
        <p className="text-sm text-muted-foreground">
          O roteamento WhatsApp→DARIUS está desligado: os números acima de WhatsApp só crescem depois de ligar a flag para
          uma instância.
        </p>
      ) : null}
    </div>
  );
}
