"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/admin/ui/card";
import { MetricChart } from "@/components/admin/charts/MetricChart";
import { useRollingSeries } from "@/hooks/use-rolling-series";
import { formatPercent } from "@/lib/format";

interface ResourceGaugeProps {
  label: string;
  percent: number | null;
  usedLabel: string | null;
}

function ResourceGauge({ label, percent, usedLabel }: ResourceGaugeProps) {
  const series = useRollingSeries(percent, 24);
  const tone = percent === null ? "hsl(215 14% 58%)" : percent > 85 ? "hsl(0 72% 51%)" : percent > 65 ? "hsl(38 92% 50%)" : "hsl(217 91% 60%)";

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-baseline justify-between">
          <span>{label}</span>
          <span className="text-lg font-semibold text-foreground">{formatPercent(percent)}</span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <MetricChart data={series} color={tone} unit="%" height={90} />
        {usedLabel ? <p className="mt-2 text-xs text-muted-foreground">{usedLabel}</p> : null}
      </CardContent>
    </Card>
  );
}

interface SystemHealthProps {
  cpuPercent: number | null;
  memoryPercent: number | null;
  memoryUsedMb: number | null;
  memoryTotalMb: number | null;
  diskPercent: number | null;
  diskUsedGb: number | null;
  diskTotalGb: number | null;
}

export function SystemHealth({
  cpuPercent,
  memoryPercent,
  memoryUsedMb,
  memoryTotalMb,
  diskPercent,
  diskUsedGb,
  diskTotalGb,
}: SystemHealthProps) {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
      <ResourceGauge label="CPU" percent={cpuPercent} usedLabel={null} />
      <ResourceGauge
        label="Memória"
        percent={memoryPercent}
        usedLabel={memoryUsedMb !== null && memoryTotalMb !== null ? `${Math.round(memoryUsedMb)} MB / ${Math.round(memoryTotalMb)} MB` : null}
      />
      <ResourceGauge
        label="Disco"
        percent={diskPercent}
        usedLabel={diskUsedGb !== null && diskTotalGb !== null ? `${diskUsedGb.toFixed(1)} GB / ${diskTotalGb.toFixed(1)} GB` : null}
      />
    </div>
  );
}
