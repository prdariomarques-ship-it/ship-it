"use client";

import { useEffect, useState } from "react";
import { AdminPageHeader } from "@/components/admin/PageHeader";
import { EmptyState } from "@/components/admin/EmptyState";
import { ErrorState } from "@/components/admin/ErrorState";
import { LoadingRows } from "@/components/admin/LoadingGrid";
import { Search } from "lucide-react";
import { Input } from "@/components/admin/ui/input";
import { Card, CardContent } from "@/components/admin/ui/card";
import { Badge } from "@/components/admin/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/admin/ui/table";
import { drtApi, type DRTExecution } from "@/lib/drt-api";
import { formatDateTime } from "@/lib/format";

export default function RuntimeExecutionsPage() {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const [executions, setExecutions] = useState<DRTExecution[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadExecutions = async () => {
      try {
        setLoading(true);
        setError(null);
        // In a real implementation, this would call an endpoint to list executions
        // For now, we show empty state as the API doesn't have a list endpoint
        setExecutions([]);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load executions");
      } finally {
        setLoading(false);
      }
    };

    loadExecutions();
    const interval = setInterval(loadExecutions, 5000);
    return () => clearInterval(interval);
  }, []);

  const filteredExecutions = executions.filter((exec) => {
    const matchesSearch =
      exec.execution_id?.toLowerCase().includes(search.toLowerCase()) ||
      exec.correlation_id?.toLowerCase().includes(search.toLowerCase());
    const matchesStatus = status === "all" || exec.status === status;
    return matchesSearch && matchesStatus;
  });

  const getStatusColor = (execStatus: string) => {
    switch (execStatus) {
      case "running":
        return "default";
      case "completed":
        return "success";
      case "failed":
        return "destructive";
      case "recovered":
        return "secondary";
      default:
        return "secondary";
    }
  };

  return (
    <div>
      <AdminPageHeader
        title="Executions"
        subtitle="Monitor all workflow executions, including running, completed, recovered, and failed"
      />

      <div className="mb-6 flex flex-col gap-4 md:flex-row">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search execution ID or correlation ID..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-10"
            aria-label="Search executions"
          />
        </div>
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="rounded-md border border-input bg-background px-3 py-2 text-sm"
          aria-label="Filter by execution status"
        >
          <option value="all">All Status</option>
          <option value="running">Running</option>
          <option value="completed">Completed</option>
          <option value="recovered">Recovered</option>
          <option value="failed">Failed</option>
        </select>
      </div>

      <Card>
        <CardContent className="pt-4">
          {loading ? (
            <LoadingRows count={5} />
          ) : error ? (
            <ErrorState message={error} onRetry={() => window.location.reload()} />
          ) : filteredExecutions.length === 0 ? (
            <EmptyState title="No executions yet" description="Start by executing a workflow from the Workflows page" />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Execution ID</TableHead>
                  <TableHead>Correlation ID</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Started</TableHead>
                  <TableHead>Duration</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredExecutions.map((exec) => (
                  <TableRow key={exec.execution_id}>
                    <TableCell className="font-mono text-xs">{exec.execution_id}</TableCell>
                    <TableCell className="font-mono text-xs">{exec.correlation_id || "—"}</TableCell>
                    <TableCell>
                      <Badge variant={getStatusColor(exec.status)}>{exec.status}</Badge>
                    </TableCell>
                    <TableCell className="text-xs">{formatDateTime(exec.started_at)}</TableCell>
                    <TableCell className="text-xs">{exec.duration_ms ? `${exec.duration_ms}ms` : "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
