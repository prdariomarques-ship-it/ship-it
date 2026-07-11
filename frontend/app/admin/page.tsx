"use client";

import { motion } from "framer-motion";
import { Bot, Clock, MessageCircle, ShieldCheck, Users, Wrench } from "lucide-react";

import { AdminPageHeader } from "@/components/admin/PageHeader";
import { StatusCard } from "@/components/admin/StatusCard";
import { MetricCard } from "@/components/admin/MetricCard";
import { MetricChart } from "@/components/admin/charts/MetricChart";
import { LoadingGrid } from "@/components/admin/LoadingGrid";
import { ErrorState } from "@/components/admin/ErrorState";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/admin/ui/card";
import { useAdminIndex, useAdminMetrics, useAdminStatus } from "@/lib/admin-api";
import { useRatePerMinute } from "@/hooks/use-rolling-series";
import { sumMetric } from "@/lib/metrics-helpers";
import { formatNumber, formatUptime } from "@/lib/format";

const FRONTEND_STATUS = {
  name: "frontend",
  online: true,
  detail: "você está usando agora",
  latency_ms: 0,
  last_heartbeat: new Date().toISOString(),
};

export default function AdminDashboardPage() {
  const index = useAdminIndex();
  const status = useAdminStatus();
  const metrics = useAdminMetrics();

  const executionsTotal = sumMetric(metrics.data, "darioos_agent_runs_total");
  const errorsTotal = sumMetric(metrics.data, "darioos_agent_runs_total", { status: "error" });
  const tokensTotal =
    sumMetric(metrics.data, "darioos_agent_tokens_total", { kind: "prompt" }) +
    sumMetric(metrics.data, "darioos_agent_tokens_total", { kind: "completion" });
  const httpDurationSum = sumMetric(metrics.data, "darioos_http_request_duration_seconds_sum");
  const httpDurationCount = sumMetric(metrics.data, "darioos_http_request_duration_seconds_count");
  const avgLatencyMs = httpDurationCount > 0 ? (httpDurationSum / httpDurationCount) * 1000 : null;

  const executionsSeries = useRatePerMinute(executionsTotal);
  const errorsSeries = useRatePerMinute(errorsTotal);
  const tokensSeries = useRatePerMinute(tokensTotal);
  const latencySeries = useRatePerMinute(avgLatencyMs);

  return (
    <div>
      <AdminPageHeader
        title="Dashboard"
        subtitle="Visão geral do Dario OS — status dos sistemas e atividade recente."
      />

      <section className="mb-8">
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">Status dos sistemas</h2>
        {status.isLoading ? (
          <LoadingGrid count={9} />
        ) : status.isError ? (
          <ErrorState message={(status.error as Error).message} onRetry={() => status.refetch()} />
        ) : (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
          >
            <StatusCard status={FRONTEND_STATUS} />
            {status.data?.map((item) => <StatusCard key={item.name} status={item} />)}
          </motion.div>
        )}
      </section>

      <section className="mb-8">
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">Visão geral</h2>
        {index.isLoading ? (
          <LoadingGrid count={6} />
        ) : index.isError ? (
          <ErrorState message={(index.error as Error).message} onRetry={() => index.refetch()} />
        ) : index.data ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
            <MetricCard label="Usuários" value={formatNumber(index.data.users_total)} icon={Users} />
            <MetricCard label="Agents" value={formatNumber(index.data.agents_total)} icon={Bot} />
            <MetricCard label="Tools" value={formatNumber(index.data.tools_total)} icon={Wrench} />
            <MetricCard
              label="Contas Google"
              value={formatNumber(index.data.google_connected_accounts)}
              icon={ShieldCheck}
            />
            <MetricCard
              label="WhatsApp"
              value={index.data.whatsapp_connected ? "Conectado" : "Desconectado"}
              icon={MessageCircle}
              tone={index.data.whatsapp_connected ? "success" : "destructive"}
            />
            <MetricCard label="Uptime" value={formatUptime(index.data.uptime_seconds)} icon={Clock} />
          </div>
        ) : null}
      </section>

      <section>
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">Gráficos em tempo real</h2>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Execuções/min</CardTitle>
            </CardHeader>
            <CardContent>
              <MetricChart data={executionsSeries} color="hsl(217 91% 60%)" />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Tokens/min</CardTitle>
            </CardHeader>
            <CardContent>
              <MetricChart data={tokensSeries} color="hsl(142 71% 45%)" />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Erros/min</CardTitle>
            </CardHeader>
            <CardContent>
              <MetricChart data={errorsSeries} color="hsl(0 72% 51%)" />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Latência média HTTP</CardTitle>
            </CardHeader>
            <CardContent>
              <MetricChart data={latencySeries} color="hsl(38 92% 50%)" unit="ms" />
            </CardContent>
          </Card>
        </div>
      </section>
    </div>
  );
}
