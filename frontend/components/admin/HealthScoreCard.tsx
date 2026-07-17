import type { DailyHealthScore } from "@/lib/briefing";

function scoreColor(score: number): string {
  if (score >= 80) return "text-success";
  if (score >= 50) return "text-warning";
  return "text-destructive";
}

export function HealthScoreCard({ health }: { health: DailyHealthScore }) {
  return (
    <div>
      <div className="flex items-baseline gap-2">
        <span className={`text-4xl font-bold ${scoreColor(health.score)}`}>{health.score}</span>
        <span className="text-sm text-muted-foreground">/ 100</span>
      </div>
      <p className="mt-1 font-mono text-xs text-muted-foreground">{health.formula}</p>
      {health.deductions.length > 0 ? (
        <ul className="mt-3 flex flex-col gap-1.5">
          {health.deductions.map((d) => (
            <li key={d.label} className="flex items-start justify-between gap-2 text-xs">
              <span className="text-muted-foreground">
                <span className="font-medium text-foreground">{d.label}: </span>
                {d.reason}
              </span>
              <span className="shrink-0 text-destructive">-{d.points}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-xs text-muted-foreground">Nenhum problema detectado hoje.</p>
      )}
    </div>
  );
}
