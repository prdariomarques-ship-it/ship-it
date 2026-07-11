"use client";

import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { SeriesPoint } from "@/hooks/use-rolling-series";
import { EmptyState } from "@/components/admin/EmptyState";

interface MetricChartProps {
  data: SeriesPoint[];
  color?: string;
  unit?: string;
  height?: number;
}

/** Thin Recharts wrapper — one look for every "line over time" panel in the
 * dashboard (CPU%, executions/min, tokens/min, latency, ...). Colors come
 * from CSS custom properties so the chart follows the same dark theme
 * tokens as the rest of the admin UI instead of hardcoded hex values. */
export function MetricChart({ data, color = "hsl(217 91% 60%)", unit = "", height = 160 }: MetricChartProps) {
  if (data.length < 2) {
    return (
      <div style={{ height }} className="flex items-center justify-center">
        <EmptyState
          compact
          title="Coletando dados…"
          description="O gráfico aparece após duas leituras consecutivas."
        />
      </div>
    );
  }

  const gradientId = `grad-${color.replace(/[^a-zA-Z0-9]/g, "")}`;

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 6, right: 8, left: -20, bottom: 0 }}>
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={color} stopOpacity={0.35} />
            <stop offset="95%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <XAxis
          dataKey="t"
          tickFormatter={(t: number) => new Date(t).toLocaleTimeString("pt-BR", { minute: "2-digit", second: "2-digit" })}
          tick={{ fontSize: 10, fill: "hsl(215 14% 58%)" }}
          axisLine={{ stroke: "hsl(222 16% 17%)" }}
          tickLine={false}
          minTickGap={30}
        />
        <YAxis tick={{ fontSize: 10, fill: "hsl(215 14% 58%)" }} axisLine={false} tickLine={false} width={36} />
        <Tooltip
          contentStyle={{
            background: "hsl(222 20% 9%)",
            border: "1px solid hsl(222 16% 17%)",
            borderRadius: 8,
            fontSize: 12,
          }}
          labelFormatter={(t) => (typeof t === "number" ? new Date(t).toLocaleTimeString("pt-BR") : "")}
          formatter={(value) => [`${Number(value).toFixed(2)}${unit}`, ""]}
        />
        <Area type="monotone" dataKey="v" stroke={color} strokeWidth={2} fill={`url(#${gradientId})`} isAnimationActive={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
}
