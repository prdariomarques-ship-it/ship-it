"use client";

// Shared by AIOperatorCenter, BriefingRecommendationCard and the Action
// Center page — one workflow control per recommendation, not a bare
// button. SAFE_AUTOMATIC executes in one click; REQUIRES_CONFIRMATION shows
// the workflow steps (+ draft content, when the action creates a new
// record) and needs a second click; MANUAL_ONLY only links to where a
// human has to go look. See ACTION_CENTER.md.

import { useState } from "react";
import Link from "next/link";
import { CheckCircle2, ExternalLink, RotateCcw } from "lucide-react";

import { Button } from "@/components/admin/ui/button";
import { useActionExecution } from "@/hooks/use-action-execution";
import { buildActionPreview, planAction, planAlternatives } from "@/lib/actions";
import type { ActionPlan } from "@/lib/actions";
import type { OperatorInsight } from "@/lib/operator";

function draftSummary(plan: ActionPlan): string | null {
  if (!plan.draft) return null;
  if ("due_date" in plan.draft) {
    return `"${plan.draft.title}" — prazo ${new Date(plan.draft.due_date).toLocaleString("pt-BR")}`;
  }
  return `"${plan.draft.title}" — ${new Date(plan.draft.starts_at).toLocaleString("pt-BR")}`;
}

function WorkflowTrail({ steps }: { steps: string[] }) {
  if (steps.length === 0) return null;
  return <p className="text-[11px] text-muted-foreground">{steps.join(" › ")}</p>;
}

/** "Before executing any action, show a preview" — every field answers a
 * fixed question (what happens / what's affected / undo-able / how long /
 * side effects / confidence). Full panel only for REQUIRES_CONFIRMATION,
 * where the second click is exactly the moment to review it — see
 * ACTION_CENTER.md "Action Preview". */
function ActionPreviewPanel({ plan }: { plan: ActionPlan }) {
  const preview = buildActionPreview(plan);
  if (!preview) return null;
  return (
    <div className="flex flex-col gap-1 text-[11px] text-muted-foreground">
      <p><span className="font-medium text-foreground">O que vai acontecer: </span>{preview.whatWillHappen}</p>
      <p><span className="font-medium text-foreground">Afeta: </span>{preview.affectedEntities.join(", ")}</p>
      <p>
        <span className="font-medium text-foreground">Pode ser desfeito: </span>
        {preview.reversible ? "Sim" : "Não"} — {preview.rollbackNote}
      </p>
      <p><span className="font-medium text-foreground">Tempo estimado: </span>{preview.estimatedExecutionTime}</p>
      {preview.sideEffects.length > 0 ? (
        <div>
          <span className="font-medium text-foreground">Efeitos colaterais: </span>
          <ul className="ml-3.5 list-disc">
            {preview.sideEffects.map((effect) => (
              <li key={effect}>{effect}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <p><span className="font-medium text-foreground">Confiança de execução: </span>{preview.executionConfidence}</p>
    </div>
  );
}

function safeAutomaticTooltip(plan: ActionPlan): string {
  const preview = buildActionPreview(plan);
  if (!preview) return plan.steps.join(" › ");
  const rollback = preview.reversible ? `reversível — ${preview.rollbackNote}` : "não reversível";
  return [plan.steps.join(" › "), preview.whatWillHappen, rollback].join(" | ");
}

interface ActionButtonProps {
  plan: ActionPlan;
  onExecute: (plan: ActionPlan) => void;
  isExecuting: boolean;
  variant?: "outline" | "ghost";
}

function ActionButton({ plan, onExecute, isExecuting, variant = "outline" }: ActionButtonProps) {
  const [confirming, setConfirming] = useState(false);

  if (plan.classification === "MANUAL_ONLY") {
    return (
      <Button variant="ghost" size="sm" title={plan.classificationReason} asChild>
        <Link href={plan.url ?? "/admin"}>
          <ExternalLink className="h-3.5 w-3.5" />
          {plan.actionLabel}
        </Link>
      </Button>
    );
  }

  if (plan.classification === "REQUIRES_CONFIRMATION" && confirming) {
    return (
      <div className="flex flex-col gap-1.5 rounded-md border border-border bg-muted/30 p-2">
        <WorkflowTrail steps={plan.steps} />
        {draftSummary(plan) ? <p className="text-xs text-muted-foreground">{draftSummary(plan)}</p> : null}
        <ActionPreviewPanel plan={plan} />
        <div className="flex gap-1.5">
          <Button
            variant="outline"
            size="sm"
            disabled={isExecuting}
            onClick={() => {
              onExecute(plan);
              setConfirming(false);
            }}
          >
            Confirmar
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setConfirming(false)}>
            Cancelar
          </Button>
        </div>
      </div>
    );
  }

  if (plan.classification === "REQUIRES_CONFIRMATION") {
    return (
      <Button variant={variant} size="sm" title={plan.classificationReason} onClick={() => setConfirming(true)}>
        {plan.actionLabel}
      </Button>
    );
  }

  // SAFE_AUTOMATIC: one click, workflow steps visible as a tooltip.
  return (
    <Button
      variant={variant}
      size="sm"
      disabled={isExecuting}
      title={safeAutomaticTooltip(plan)}
      onClick={() => onExecute(plan)}
    >
      {plan.actionKind === "retry_job" ? (
        <RotateCcw className="h-3.5 w-3.5" />
      ) : (
        <CheckCircle2 className="h-3.5 w-3.5" />
      )}
      {plan.actionLabel}
    </Button>
  );
}

export function ActionWorkflowControl({ insight }: { insight: OperatorInsight }) {
  const { execute, isExecuting } = useActionExecution();
  const plan = planAction(insight);
  const alternatives = planAlternatives(insight);

  if (!plan) return null;

  const runPlan = (p: ActionPlan) => {
    const base = {
      category: p.category,
      title: p.title,
      estimatedMinutes: p.estimatedMinutes,
      relatedEntities: [insight.title],
    };
    switch (p.actionKind) {
      case "approve_goal":
      case "retry_job":
      case "complete_task":
      case "reschedule_task":
        if (p.targetId === undefined) return;
        execute({ ...base, kind: p.actionKind, targetId: p.targetId });
        return;
      case "create_followup_task":
        if (!p.draft || !("due_date" in p.draft)) return;
        execute({ ...base, kind: "create_followup_task", draft: p.draft });
        return;
      case "schedule_time":
        if (!p.draft || !("starts_at" in p.draft)) return;
        execute({ ...base, kind: "schedule_time", draft: p.draft });
        return;
      case "open_related_item":
        return;
    }
  };

  return (
    <div className="flex flex-wrap items-start gap-1.5">
      <ActionButton plan={plan} onExecute={runPlan} isExecuting={isExecuting(plan.actionKind, plan.targetId)} />
      {alternatives.map((alt) => (
        <ActionButton
          key={alt.actionKind}
          plan={alt}
          onExecute={runPlan}
          isExecuting={isExecuting(alt.actionKind, alt.targetId)}
          variant="ghost"
        />
      ))}
    </div>
  );
}
