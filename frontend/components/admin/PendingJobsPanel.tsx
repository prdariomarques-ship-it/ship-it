import { Badge } from "@/components/admin/ui/badge";
import { Button } from "@/components/admin/ui/button";
import { EmptyState } from "@/components/admin/EmptyState";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/admin/ui/table";
import { formatDateTime } from "@/lib/format";
import type { JobRead } from "@/lib/admin-types";

const STATUS_TONE: Record<string, "secondary" | "warning" | "destructive"> = {
  queued: "secondary",
  running: "warning",
};

interface PendingJobsPanelProps {
  jobs: JobRead[];
  onCancel: (jobId: number) => void;
  cancelingId: number | null;
}

export function PendingJobsPanel({ jobs, onCancel, cancelingId }: PendingJobsPanelProps) {
  if (jobs.length === 0) {
    return <EmptyState title="Nenhum job pendente" description="Nada na fila ou em execução agora." />;
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Job</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Tentativas</TableHead>
          <TableHead>Agendado para</TableHead>
          <TableHead />
        </TableRow>
      </TableHeader>
      <TableBody>
        {jobs.map((job) => (
          <TableRow key={job.id}>
            <TableCell className="font-mono text-xs">{job.name}</TableCell>
            <TableCell>
              <Badge variant={STATUS_TONE[job.status] ?? "secondary"}>{job.status}</Badge>
            </TableCell>
            <TableCell className="text-xs text-muted-foreground">
              {job.attempts}/{job.max_attempts}
            </TableCell>
            <TableCell className="text-xs text-muted-foreground">{formatDateTime(job.scheduled_at)}</TableCell>
            <TableCell>
              <Button
                variant="outline"
                size="sm"
                disabled={cancelingId === job.id}
                onClick={() => onCancel(job.id)}
              >
                {cancelingId === job.id ? "Cancelando…" : "Cancelar"}
              </Button>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
