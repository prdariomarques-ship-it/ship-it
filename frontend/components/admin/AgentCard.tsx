import { Bot } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/admin/ui/card";
import { Badge } from "@/components/admin/ui/badge";
import { Separator } from "@/components/admin/ui/separator";
import { formatDuration, formatNumber, formatRelativeTime } from "@/lib/format";
import type { AgentAdminInfo } from "@/lib/admin-types";

export function AgentCard({ agent }: { agent: AgentAdminInfo }) {
  const hasStats = agent.runs_total !== null;

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between space-y-0">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary/15 text-primary">
            <Bot className="h-4 w-4" />
          </div>
          <div>
            <CardTitle className="text-sm">{agent.name}</CardTitle>
            <CardDescription className="mt-0.5">{agent.tool_count} tool(s)</CardDescription>
          </div>
        </div>
        {agent.runs_error ? (
          <Badge variant="destructive">{agent.runs_error} erro(s)</Badge>
        ) : (
          <Badge variant="success">saudável</Badge>
        )}
      </CardHeader>
      <CardContent>
        <p className="mb-3 text-xs text-muted-foreground">{agent.description}</p>
        <Separator className="mb-3" />
        <div className="grid grid-cols-2 gap-y-2 text-xs">
          <span className="text-muted-foreground">Execuções</span>
          <span className="text-right font-medium">{hasStats ? formatNumber(agent.runs_total) : "não disponível"}</span>
          <span className="text-muted-foreground">Tempo médio</span>
          <span className="text-right font-medium">{formatDuration(agent.avg_duration_seconds)}</span>
          <span className="text-muted-foreground">Erros</span>
          <span className="text-right font-medium">{hasStats ? formatNumber(agent.runs_error) : "não disponível"}</span>
          <span className="text-muted-foreground">Última execução</span>
          <span className="text-right font-medium">
            {agent.last_execution ? formatRelativeTime(agent.last_execution) : "sem registro"}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}
