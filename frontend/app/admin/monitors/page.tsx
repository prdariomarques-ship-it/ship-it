"use client";

import { LineChart, AlertTriangle, Clock } from "lucide-react";

import { AdminPageHeader } from "@/components/admin/PageHeader";
import { LoadingGrid } from "@/components/admin/LoadingGrid";
import { ErrorState } from "@/components/admin/ErrorState";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/admin/ui/card";
import { Badge } from "@/components/admin/ui/badge";
import { useAdminJobs } from "@/lib/admin-api";
import type { JobRead, JobStatus } from "@/lib/admin-types";
import { formatDateTime, formatRelativeTime } from "@/lib/format";

// The three legacy Telegram bots (spcx-monitor, @dariozcodebot/PMX,
// "Mercado") managed from DarioOS — each its own self-rescheduling job,
// still delivering to its own separate Telegram bot/chat (see
// backend/investments/jobs.py) rather than one shared destination.
const MONITORS: { jobName: string; label: string; description: string }[] = [
  {
    jobName: "market.check_spcx34",
    label: "SPCX34 (Bollinger)",
    description: "Alerta quando SPCX34.SA fura a banda superior (ex-Monitor SPCX Dário, Telegram).",
  },
  {
    jobName: "market.send_b3_summary",
    label: "B3 / Ibovespa",
    description: "IBOVESPA + USD/BRL a cada checagem (ex-PMX, @dariozcodebot).",
  },
  {
    jobName: "market.send_daily_briefing",
    label: "Radar de Mercado",
    description: "Curva de juros EUA, câmbio, bolsas e commodities (ex-\"Mercado\"/Small11).",
  },
];

const STATUS_VARIANT: Record<JobStatus, "default" | "success" | "destructive" | "warning" | "secondary"> = {
  queued: "default",
  running: "warning",
  succeeded: "success",
  failed: "destructive",
  cancelled: "secondary",
};

const STATUS_LABEL: Record<JobStatus, string> = {
  queued: "Agendado",
  running: "Rodando",
  succeeded: "Sucesso",
  failed: "Falhou",
  cancelled: "Cancelado",
};

function latestByStatus(jobs: JobRead[], jobName: string, statuses: JobStatus[]): JobRead | undefined {
  return jobs.find((job) => job.name === jobName && statuses.includes(job.status));
}

export default function AdminMonitorsPage() {
  const { data, isLoading, isError, error, refetch } = useAdminJobs();

  const jobs = data ?? [];
  const seenNames = new Set(MONITORS.map((monitor) => monitor.jobName));
  const unexpected = jobs.filter((job) => !seenNames.has(job.name) && job.name.startsWith("market."));

  return (
    <div>
      <AdminPageHeader
        title="Monitores"
        subtitle="Bots de mercado antigos (Telegram, fora do git) migrados para jobs autossustentáveis no DarioOS."
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
                        última execução: {formatRelativeTime(last.finished_at)}
                        {last.status === "failed" ? " — falhou" : ""}
                      </p>
                    ) : null}
                    {next ? (
                      <p className="text-xs text-muted-foreground">
                        próxima: {formatDateTime(next.scheduled_at)}
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
            docker/.env). MARKET_MONITORS_ENABLED fica desligado até os bots antigos serem confirmados parados.
          </p>
        </div>
      )}
    </div>
  );
}
