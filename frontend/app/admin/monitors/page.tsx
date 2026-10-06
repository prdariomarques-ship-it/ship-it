"use client";

import { LineChart, AlertTriangle, Clock, Send } from "lucide-react";

import { AdminPageHeader } from "@/components/admin/PageHeader";
import { LoadingGrid } from "@/components/admin/LoadingGrid";
import { ErrorState } from "@/components/admin/ErrorState";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/admin/ui/card";
import { Badge } from "@/components/admin/ui/badge";
import { useFinancialJobs } from "@/lib/admin-api";
import type { FinancialJobRead, FinancialJobStatus } from "@/lib/admin-types";
import { formatDateTime, formatRelativeTime } from "@/lib/format";

// The three legacy Telegram bots (spcx-monitor, @dariozcodebot/PMX,
// "Mercado") managed from DarioOS — each its own self-rescheduling job on
// the isolated financial worker (backend/investments/), still delivering
// to its own separate Telegram bot/chat rather than one shared destination.
// This page is read-only: it queries /investments/jobs (financial_jobs),
// never /jobs (WhatsApp's queue) — see investments/router.py.
const MONITORS: { jobName: string; feed: string; label: string; description: string }[] = [
  {
    jobName: "market.check_spcx34",
    feed: "spcx",
    label: "SPCX34 (Bollinger)",
    description: "Alerta quando SPCX34.SA fura a banda superior (ex-Monitor SPCX Dário, Telegram).",
  },
  {
    jobName: "market.send_b3_summary",
    feed: "b3",
    label: "B3 / Ibovespa",
    description: "IBOVESPA + USD/BRL a cada checagem (ex-PMX, @dariozcodebot).",
  },
  {
    jobName: "market.send_daily_briefing",
    feed: "mercado",
    label: "Radar de Mercado",
    description: "Curva de juros EUA, câmbio, bolsas e commodities (ex-\"Mercado\"/Small11).",
  },
];

const STATUS_VARIANT: Record<FinancialJobStatus, "default" | "success" | "destructive" | "warning" | "secondary"> = {
  queued: "default",
  running: "warning",
  succeeded: "success",
  failed: "destructive",
};

const STATUS_LABEL: Record<FinancialJobStatus, string> = {
  queued: "Agendado",
  running: "Rodando",
  succeeded: "Sucesso",
  failed: "Falhou",
};

function latestByStatus(
  jobs: FinancialJobRead[], jobName: string, statuses: FinancialJobStatus[]
): FinancialJobRead | undefined {
  return jobs.find((job) => job.name === jobName && statuses.includes(job.status));
}

// A check job finishing SUCCEEDED only proves the report was generated —
// never that a Telegram message went out. Delivery is a separate
// telegram.send_message row for the same feed, read from its own result.
function latestDeliveryForFeed(jobs: FinancialJobRead[], feed: string): FinancialJobRead | undefined {
  return jobs.find(
    (job) => job.name === "telegram.send_message" && job.payload?.feed === feed && job.status !== "queued"
  );
}

function deliveryBadge(delivery: FinancialJobRead | undefined) {
  if (!delivery) return { variant: "secondary" as const, label: "sem envio ainda" };
  const result = delivery.result;
  if (!result) return { variant: "secondary" as const, label: "resultado desconhecido" };
  if (result.delivered === true) return { variant: "success" as const, label: `entregue (id ${result.message_id ?? "?"})` };
  if (result.delivered === null) return { variant: "warning" as const, label: "resultado incerto — checar manualmente" };
  const reasonLabel: Record<string, string> = {
    monitors_disabled: "monitores desligados",
    missing_credential: "credencial não configurada",
    permanent_error: "falha permanente",
  };
  return { variant: "destructive" as const, label: `não entregue — ${reasonLabel[result.reason ?? ""] ?? result.reason ?? "motivo desconhecido"}` };
}

export default function AdminMonitorsPage() {
  const { data, isLoading, isError, error, refetch } = useFinancialJobs();

  const jobs = data ?? [];
  const seenNames = new Set(MONITORS.map((monitor) => monitor.jobName));
  const unexpected = jobs.filter((job) => !seenNames.has(job.name) && job.name.startsWith("market."));

  return (
    <div>
      <AdminPageHeader
        title="Monitores"
        subtitle="Bots de mercado antigos (Telegram, fora do git) migrados para jobs autossustentáveis no DarioOS — execução roda num processo separado do atendimento WhatsApp."
      />

      {isLoading ? (
        <LoadingGrid count={3} />
      ) : isError ? (
        <ErrorState message={(error as Error).message} onRetry={() => refetch()} />
      ) : (
        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {MONITORS.map((monitor) => {
              const next = latestByStatus(jobs, monitor.jobName, ["queued", "running"]);
              const last = latestByStatus(jobs, monitor.jobName, ["succeeded", "failed"]);
              const everSeen = next || last;
              const delivery = latestDeliveryForFeed(jobs, monitor.feed);
              const deliveryStatus = deliveryBadge(delivery);

              return (
                <Card key={monitor.jobName}>
                  <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="flex items-center gap-2 text-base">
                      <LineChart className="h-4 w-4" />
                      {monitor.label}
                    </CardTitle>
                    {everSeen ? (
                      <Badge variant={STATUS_VARIANT[(next ?? last!).status]}>
                        {STATUS_LABEL[(next ?? last!).status]}
                      </Badge>
                    ) : (
                      <Badge variant="secondary">Nunca rodou</Badge>
                    )}
                  </CardHeader>
                  <CardContent className="flex flex-col gap-2">
                    <p className="text-sm text-muted-foreground">{monitor.description}</p>
                    {last ? (
                      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                        <Clock className="h-3.5 w-3.5" />
                        relatório gerado: {formatRelativeTime(last.finished_at)}
                        {last.status === "failed" ? " — falhou" : ""}
                      </p>
                    ) : null}
                    {/* Report generation vs. confirmed delivery — two different things,
                        shown as two separate lines so one can never be read as proof of the other. */}
                    <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                      <Send className="h-3.5 w-3.5" />
                      entrega Telegram: <Badge variant={deliveryStatus.variant}>{deliveryStatus.label}</Badge>
                    </p>
                    {next ? (
                      <p className="text-xs text-muted-foreground">
                        próximo relatório: {formatDateTime(next.scheduled_at)}
                      </p>
                    ) : null}
                    {last?.last_error ? (
                      <p className="flex items-start gap-1.5 rounded-md bg-destructive/10 p-2 text-xs text-destructive">
                        <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                        {last.last_error}
                      </p>
                    ) : null}
                  </CardContent>
                </Card>
              );
            })}
          </div>

          {unexpected.length > 0 ? (
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Outros jobs de mercado</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-xs text-muted-foreground">
                  {unexpected.length} job(s) com prefixo &quot;market.&quot; não listados acima.
                </p>
              </CardContent>
            </Card>
          ) : null}

          <p className="text-xs text-muted-foreground">
            Cada monitor entrega no seu próprio bot/chat do Telegram (TELEGRAM_BOT_TOKEN_SPCX, _B3, _MERCADO — ver
            docker/.env). MARKET_MONITORS_ENABLED fica desligado até os bots antigos serem confirmados parados —
            desligar também bloqueia qualquer envio já enfileirado, não só os próximos ciclos.
          </p>
        </div>
      )}
    </div>
  );
}
