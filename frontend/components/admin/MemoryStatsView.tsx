import { Card, CardContent, CardHeader, CardTitle } from "@/components/admin/ui/card";
import { Badge } from "@/components/admin/ui/badge";
import { MetricCard } from "@/components/admin/MetricCard";
import { formatDateTime, formatNumber } from "@/lib/format";
import type { MemoryStats } from "@/lib/admin-types";

export function MemoryStatsView({ stats }: { stats: MemoryStats }) {
  const sources = Object.entries(stats.embeddings_by_source);

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard label="Embeddings totais" value={formatNumber(stats.embeddings_total)} />
        <MetricCard
          label="Pontos no Qdrant"
          value={stats.collection.points_count !== null ? formatNumber(stats.collection.points_count) : "não disponível"}
          hint={stats.collection.status ? `status: ${stats.collection.status}` : undefined}
        />
        <MetricCard label="Arquivos do Drive indexados" value={formatNumber(stats.drive_indexed_files)} />
        <MetricCard label="Cache" value={stats.cache_backend} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Coleções (Qdrant)</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2 text-sm">
          <div className="flex justify-between border-b border-border pb-2">
            <span className="text-muted-foreground">Nome</span>
            <span className="font-medium">{stats.collection.name}</span>
          </div>
          <div className="flex justify-between border-b border-border pb-2">
            <span className="text-muted-foreground">Vetores</span>
            <span className="font-medium">
              {stats.collection.vectors_count !== null ? formatNumber(stats.collection.vectors_count) : "não disponível"}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Última indexação (Drive)</span>
            <span className="font-medium">{formatDateTime(stats.drive_last_indexed_at)}</span>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Chunks por origem</CardTitle>
        </CardHeader>
        <CardContent>
          {sources.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nenhum embedding armazenado ainda.</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {sources.map(([source, count]) => (
                <Badge key={source} variant="secondary">
                  {source}: {formatNumber(count)}
                </Badge>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
