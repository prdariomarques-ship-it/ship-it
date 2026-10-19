"use client";

import { LoadingGrid } from "@/components/admin/LoadingGrid";
import { Badge } from "@/components/admin/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/admin/ui/card";
import { Banner, ErrorLine, Unavailable } from "@/components/darius/common";
import { useDariusStatus } from "@/lib/darius-api";
import { formatDateTime } from "@/lib/format";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between border-b border-border py-2 text-sm last:border-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{children}</span>
    </div>
  );
}

const yesNo = (value: boolean) => (value ? "sim" : "não");

/** Service state straight from `GET /admin/darius/status` -- measured now, never cached or assumed. */
export function DariusStatusCard() {
  const { data, isLoading, isError, error } = useDariusStatus();

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle>Estado do serviço DARIUS</CardTitle>
        {data ? (
          <Badge variant={data.reachable ? "success" : "destructive"}>
            {data.reachable ? "acessível" : "indisponível"}
          </Badge>
        ) : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {isLoading ? (
          <LoadingGrid count={1} />
        ) : isError ? (
          <ErrorLine error={error} />
        ) : data ? (
          <>
            {!data.configured ? (
              <Banner tone="warning">
                DARIUS não configurado neste backend ({data.error ?? "DARIUS_NOT_CONFIGURED"}). Tarefas, aprovações e o
                fluxo WhatsApp→DARIUS não têm dados.
              </Banner>
            ) : !data.reachable ? (
              <Banner tone="destructive" role="alert">
                DARIUS configurado, mas sem resposta ({data.error ?? "erro não informado"}). Os dados de tarefas ficam
                indisponíveis até o serviço voltar.
              </Banner>
            ) : null}
            <div>
              <Row label="Endereço">{data.base_url || <Unavailable />}</Row>
              <Row label="Integração configurada">{yesNo(data.configured)}</Row>
              <Row label="Circuito (disjuntor)">{data.circuit}</Row>
              <Row label="Latência do health">
                {data.latency_ms !== null ? `${data.latency_ms} ms` : <Unavailable reason="sem medição neste instante" />}
              </Row>
              <Row label="Credencial de serviço">{yesNo(data.service_credential_configured)}</Row>
              <Row label="Credencial de operador">{yesNo(data.operator_credential_configured)}</Row>
              <Row label="Verificado em">{formatDateTime(data.checked_at)}</Row>
            </div>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
