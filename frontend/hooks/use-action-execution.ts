"use client";

// Action Center (Phase 4) — the one place that actually executes a
// recommendation's action, then records why (see ACTION_CENTER.md). Every
// mutation here calls an endpoint that already existed before this phase;
// this hook adds nothing except: (a) picking the right existing endpoint
// per action kind, (b) invalidating the same queries the dashboard already
// depends on, and (c) recording the execution via POST /admin/actions/log
// so it appears in the existing Timeline. Logging is fire-and-forget and
// never blocks or fails the user-visible action — an audit trail gap is
// far less harmful than a real action silently not happening because its
// own bookkeeping call failed.

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "@/hooks/useApi";
import { useToast } from "@/hooks/use-toast";
import type { ActionLogCreate } from "@/lib/admin-types";
import type { FollowupTaskDraft, ScheduleTimeDraft } from "@/lib/actions";

export type ExecuteArgs = {
  category: string;
  title: string;
  estimatedMinutes: number | null;
  relatedEntities?: string[];
} & (
  | { kind: "approve_goal" | "retry_job" | "complete_task" | "reschedule_task"; targetId: number }
  | { kind: "create_followup_task"; draft: FollowupTaskDraft }
  | { kind: "schedule_time"; draft: ScheduleTimeDraft }
);

function invalidateForKind(queryClient: ReturnType<typeof useQueryClient>, kind: ExecuteArgs["kind"]) {
  queryClient.invalidateQueries({ queryKey: ["admin", "observation"] });
  if (kind === "approve_goal") queryClient.invalidateQueries({ queryKey: ["goals"] });
  if (kind === "retry_job") queryClient.invalidateQueries({ queryKey: ["jobs"] });
  if (kind === "complete_task" || kind === "reschedule_task")
    queryClient.invalidateQueries({ queryKey: ["tasks"] });
  if (kind === "create_followup_task") queryClient.invalidateQueries({ queryKey: ["tasks"] });
  if (kind === "schedule_time") queryClient.invalidateQueries({ queryKey: ["calendar"] });
}

async function performExecute(args: ExecuteArgs): Promise<void> {
  switch (args.kind) {
    case "approve_goal":
      await apiFetch(`/goals/${args.targetId}/approve`, { method: "POST" });
      return;
    case "retry_job":
      await apiFetch(`/admin/jobs/${args.targetId}/retry`, { method: "POST" });
      return;
    case "complete_task":
      await apiFetch(`/tasks/${args.targetId}`, {
        method: "PATCH",
        body: JSON.stringify({ status: "done" }),
      });
      return;
    case "reschedule_task": {
      const tomorrow = new Date();
      tomorrow.setUTCDate(tomorrow.getUTCDate() + 1);
      await apiFetch(`/tasks/${args.targetId}`, {
        method: "PATCH",
        body: JSON.stringify({ due_date: tomorrow.toISOString() }),
      });
      return;
    }
    case "create_followup_task":
      await apiFetch("/tasks", { method: "POST", body: JSON.stringify(args.draft) });
      return;
    case "schedule_time":
      await apiFetch("/calendar", { method: "POST", body: JSON.stringify(args.draft) });
      return;
  }
}

/** Best-effort in the sense that a failed audit write never fails or blocks
 * the user-visible action (see module comment) — but the caller still needs
 * to know when the write actually landed, so the Action Center's own
 * "Concluídas"/Automation Score queries aren't invalidated (and therefore
 * refetched) before the row they're supposed to show even exists. Returning
 * the settled promise, rather than firing-and-truly-forgetting, is what
 * fixes that race. */
export function logAction(entry: ActionLogCreate): Promise<void> {
  return apiFetch("/admin/actions/log", { method: "POST", body: JSON.stringify(entry) })
    .then(() => undefined)
    .catch(() => undefined);
}

export function useActionExecution() {
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const execute = useMutation({
    mutationFn: (args: ExecuteArgs) => performExecute(args),
    onSuccess: (_data, args) => {
      invalidateForKind(queryClient, args.kind);
      toast({ title: "Ação concluída", description: args.title, variant: "success" });
      logAction({
        action_type: args.kind,
        category: args.category,
        recommendation_title: args.title,
        result: "success",
        related_entities: args.relatedEntities ?? [],
        estimated_minutes: args.estimatedMinutes,
      }).then(() => {
        queryClient.invalidateQueries({ queryKey: ["admin", "logs"] });
      });
    },
    onError: (error: Error, args) => {
      toast({ title: "Falha ao executar ação", description: error.message, variant: "destructive" });
      logAction({
        action_type: args.kind,
        category: args.category,
        recommendation_title: args.title,
        result: "failure",
        related_entities: args.relatedEntities ?? [],
        estimated_minutes: args.estimatedMinutes,
        detail: error.message,
      }).then(() => {
        queryClient.invalidateQueries({ queryKey: ["admin", "logs"] });
      });
    },
  });

  const isExecuting = (kind: ExecuteArgs["kind"] | "open_related_item", targetId?: number): boolean => {
    if (kind === "open_related_item") return false; // navigation only, never executed
    if (!execute.isPending || !execute.variables) return false;
    if (execute.variables.kind !== kind) return false;
    if (targetId === undefined) return true;
    return "targetId" in execute.variables && execute.variables.targetId === targetId;
  };

  return { execute: execute.mutate, isExecuting };
}
