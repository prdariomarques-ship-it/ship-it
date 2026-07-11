import type { MetricsSnapshot, PrometheusSample } from "@/lib/admin-types";

// Mirrors backend/admin/service.py::_metric_value exactly: `metrics.metrics`
// groups samples by Prometheus's *base* metric name (e.g.
// "darioos_agent_runs", without the "_total"/"_sum"/"_count" suffix a
// Counter/Histogram sample carries) — so this searches every sample's own
// `name` field across every group, rather than trusting the outer dict key
// to already be the exact sample name.
export function sumMetric(
  snapshot: MetricsSnapshot | undefined,
  sampleName: string,
  labelFilter: Record<string, string> = {}
): number {
  if (!snapshot) return 0;
  let total = 0;
  for (const samples of Object.values(snapshot.metrics)) {
    for (const sample of samples as PrometheusSample[]) {
      if (sample.name !== sampleName) continue;
      const matches = Object.entries(labelFilter).every(([key, value]) => sample.labels[key] === value);
      if (matches) total += sample.value;
    }
  }
  return total;
}
