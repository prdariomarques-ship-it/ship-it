import { describe, expect, it } from "vitest";

import {
  buildActionPreview,
  buildFollowupTaskDraft,
  buildScheduleTimeDraft,
  computeAutomationScore,
  parseActionLog,
  planAction,
  planAlternatives,
} from "@/lib/actions";
import { buildOperatorInsights } from "@/lib/operator";
import type { OperatorInsight } from "@/lib/operator";
import type { AdminLogEntry, CalendarEventRead, GoalRead, JobRead, TaskRead } from "@/lib/admin-types";

const NOW = new Date("2026-07-17T12:00:00Z");

function makeGoal(overrides: Partial<GoalRead> = {}): GoalRead {
  return {
    id: 1,
    user_id: 1,
    title: "Meta de teste",
    description: null,
    status: "pending",
    priority: "medium",
    deadline: null,
    progress_percent: 0,
    requires_approval: false,
    approved_at: null,
    approved_by_id: null,
    recurrence_interval_days: null,
    recurrence_parent_id: null,
    created_at: NOW.toISOString(),
    updated_at: NOW.toISOString(),
    ...overrides,
  };
}

function makeTask(overrides: Partial<TaskRead> = {}): TaskRead {
  return {
    id: 1,
    user_id: 1,
    title: "Tarefa de teste",
    description: null,
    status: "pending",
    priority: "medium",
    due_date: null,
    created_at: NOW.toISOString(),
    updated_at: NOW.toISOString(),
    ...overrides,
  };
}

function makeJob(overrides: Partial<JobRead> = {}): JobRead {
  return {
    id: 1,
    name: "test.job",
    payload: {},
    status: "failed",
    attempts: 3,
    max_attempts: 3,
    scheduled_at: NOW.toISOString(),
    started_at: NOW.toISOString(),
    finished_at: NOW.toISOString(),
    last_error: null,
    created_at: NOW.toISOString(),
    ...overrides,
  };
}

function makeLog(overrides: Partial<AdminLogEntry> = {}): AdminLogEntry {
  return {
    id: 1,
    level: "info",
    source: "admin:action.complete_task",
    message: "Ação executada: teste",
    payload: { result: "success", estimated_minutes: 5 },
    created_at: NOW.toISOString(),
    ...overrides,
  };
}

const baseInput = {
  readyGoals: [] as GoalRead[],
  awaitingApprovalGoals: [] as GoalRead[],
  tasks: [] as TaskRead[],
  calendarEvents: [] as CalendarEventRead[],
  failedJobs: [] as JobRead[],
  pendingJobs: [] as JobRead[],
  context: undefined,
  previousContext: undefined,
  whatsappConnected: true,
  now: NOW,
};

describe("planAction — classification", () => {
  it("classifies retry_job and complete_task as SAFE_AUTOMATIC", () => {
    const [job] = buildOperatorInsights({ ...baseInput, failedJobs: [makeJob({ id: 9 })] })
      .filter((i) => i.id === "retry-9");
    expect(planAction(job)?.classification).toBe("SAFE_AUTOMATIC");

    const task = makeTask({ id: 3, due_date: new Date(NOW.getTime() - 3_600_000).toISOString() });
    const [missed] = buildOperatorInsights({ ...baseInput, tasks: [task] }).filter((i) => i.id === "missed-3");
    expect(planAction(missed)?.classification).toBe("SAFE_AUTOMATIC");
    expect(planAction(missed)?.steps.length).toBeGreaterThan(0);
  });

  it("classifies approve_goal, create_followup_task and schedule_time as REQUIRES_CONFIRMATION", () => {
    const approve = buildOperatorInsights({
      ...baseInput,
      awaitingApprovalGoals: [makeGoal({ id: 5, requires_approval: true })],
    }).find((i) => i.id === "approve-5")!;
    expect(planAction(approve)?.classification).toBe("REQUIRES_CONFIRMATION");

    const priority = buildOperatorInsights({
      ...baseInput,
      readyGoals: [makeGoal({ id: 1, priority: "urgent" })],
    }).find((i) => i.id === "priority-goal-1")!;
    const plan = planAction(priority);
    expect(plan?.classification).toBe("REQUIRES_CONFIRMATION");
    expect(plan?.draft).toBeDefined();
  });

  it("classifies a calendar conflict as MANUAL_ONLY with a working URL and explains why", () => {
    const a: CalendarEventRead = {
      id: 1,
      user_id: 1,
      title: "A",
      description: null,
      location: null,
      starts_at: "2026-07-17T10:00:00Z",
      ends_at: "2026-07-17T11:00:00Z",
      reminder_minutes: null,
      created_at: NOW.toISOString(),
      updated_at: NOW.toISOString(),
    };
    const b: CalendarEventRead = { ...a, id: 2, title: "B", starts_at: "2026-07-17T10:30:00Z", ends_at: "2026-07-17T11:30:00Z" };
    const conflict = buildOperatorInsights({ ...baseInput, calendarEvents: [a, b] }).find(
      (i) => i.category === "calendar_conflict"
    )!;
    const plan = planAction(conflict);
    expect(plan?.classification).toBe("MANUAL_ONLY");
    expect(plan?.url).toBe("/admin");
    expect(plan?.classificationReason.length).toBeGreaterThan(0);
    expect(plan?.steps).toEqual([]);
  });

  it("returns null for purely informational insights (nothing to act on)", () => {
    const insights = buildOperatorInsights({
      ...baseInput,
      pendingJobs: [makeJob({ id: 1, status: "queued" })],
    });
    const automatable = insights.find((i) => i.id === "automatable-jobs")!;
    expect(planAction(automatable)).toBeNull();
  });
});

describe("planAlternatives", () => {
  it("exposes reschedule_task as an OR-branch of complete_task, same classification rules", () => {
    const task = makeTask({ id: 3, due_date: new Date(NOW.getTime() - 3_600_000).toISOString() });
    const missed = buildOperatorInsights({ ...baseInput, tasks: [task] }).find((i) => i.id === "missed-3")!;
    const alternatives = planAlternatives(missed);
    expect(alternatives).toHaveLength(1);
    expect(alternatives[0].actionKind).toBe("reschedule_task");
    expect(alternatives[0].classification).toBe("SAFE_AUTOMATIC");
  });

  it("returns an empty array when there are no alternatives", () => {
    const [job] = buildOperatorInsights({ ...baseInput, failedJobs: [makeJob({ id: 9 })] }).filter(
      (i) => i.id === "retry-9"
    );
    expect(planAlternatives(job)).toEqual([]);
  });
});

describe("draft builders — never a silent guess", () => {
  it("buildFollowupTaskDraft is due today, end of day, titled after the goal", () => {
    const draft = buildFollowupTaskDraft("Migrar WhatsApp", NOW);
    expect(draft.title).toBe("Avançar meta: Migrar WhatsApp");
    expect(new Date(draft.due_date).toISOString().slice(0, 10)).toBe("2026-07-17");
  });

  it("buildScheduleTimeDraft starts 1h from now for 30 minutes", () => {
    const draft = buildScheduleTimeDraft("Migrar WhatsApp", NOW);
    expect(draft.title).toBe("Trabalhar em: Migrar WhatsApp");
    expect(new Date(draft.starts_at).getTime() - NOW.getTime()).toBe(60 * 60_000);
    expect(new Date(draft.ends_at).getTime() - new Date(draft.starts_at).getTime()).toBe(30 * 60_000);
  });
});

describe("buildActionPreview — answers every question before execution", () => {
  it("returns null for open_related_item (navigation, not an action with consequences)", () => {
    const a: CalendarEventRead = {
      id: 1,
      user_id: 1,
      title: "A",
      description: null,
      location: null,
      starts_at: "2026-07-17T10:00:00Z",
      ends_at: "2026-07-17T11:00:00Z",
      reminder_minutes: null,
      created_at: NOW.toISOString(),
      updated_at: NOW.toISOString(),
    };
    const b: CalendarEventRead = { ...a, id: 2, title: "B", starts_at: "2026-07-17T10:30:00Z", ends_at: "2026-07-17T11:30:00Z" };
    const conflict = buildOperatorInsights({ ...baseInput, calendarEvents: [a, b] }).find(
      (i) => i.category === "calendar_conflict"
    )!;
    expect(buildActionPreview(planAction(conflict)!)).toBeNull();
  });

  it("marks approve_goal as not reversible, and complete_task as reversible", () => {
    const approve = buildOperatorInsights({
      ...baseInput,
      awaitingApprovalGoals: [makeGoal({ id: 5, requires_approval: true })],
    }).find((i) => i.id === "approve-5")!;
    const approvePreview = buildActionPreview(planAction(approve)!)!;
    expect(approvePreview.reversible).toBe(false);
    expect(approvePreview.rollbackNote.length).toBeGreaterThan(0);

    const task = makeTask({ id: 3, due_date: new Date(NOW.getTime() - 3_600_000).toISOString() });
    const missed = buildOperatorInsights({ ...baseInput, tasks: [task] }).find((i) => i.id === "missed-3")!;
    const completePreview = buildActionPreview(planAction(missed)!)!;
    expect(completePreview.reversible).toBe(true);
  });

  it("shows the drafted new entity's title as the affected entity for create_followup_task", () => {
    const goal = makeGoal({
      id: 7,
      title: "Meta arriscada",
      deadline: new Date(NOW.getTime() + 0.5 * 86_400_000).toISOString(),
      progress_percent: 20,
    });
    const insight = buildOperatorInsights({ ...baseInput, readyGoals: [goal] }).find((i) => i.id === "risk-goal-7")!;
    const preview = buildActionPreview(planAction(insight)!)!;
    expect(preview.affectedEntities).toEqual(["Avançar meta: Meta arriscada"]);
  });

  it("every preview answers all six required questions", () => {
    const [job] = buildOperatorInsights({ ...baseInput, failedJobs: [makeJob({ id: 9 })] }).filter(
      (i) => i.id === "retry-9"
    );
    const preview = buildActionPreview(planAction(job)!)!;
    expect(preview.whatWillHappen.length).toBeGreaterThan(0);
    expect(preview.affectedEntities.length).toBeGreaterThan(0);
    expect(typeof preview.reversible).toBe("boolean");
    expect(preview.estimatedExecutionTime.length).toBeGreaterThan(0);
    expect(preview.sideEffects.length).toBeGreaterThan(0);
    expect(preview.executionConfidence.length).toBeGreaterThan(0);
  });
});

describe("parseActionLog", () => {
  it("parses a real admin:action.* entry into a typed ActionLogItem", () => {
    const log = makeLog({
      payload: {
        action_type: "complete_task",
        category: "missed_task",
        recommendation_title: "Tarefa atrasada: X",
        result: "success",
        related_entities: ["X"],
        estimated_minutes: 5,
      },
    });
    const item = parseActionLog(log);
    expect(item?.result).toBe("success");
    expect(item?.recommendationTitle).toBe("Tarefa atrasada: X");
    expect(item?.relatedEntities).toEqual(["X"]);
    expect(item?.estimatedMinutes).toBe(5);
  });

  it("returns null for a log entry that isn't an Action Center entry", () => {
    const log = makeLog({ source: "admin:job_cancel", payload: {} });
    expect(parseActionLog(log)).toBeNull();
  });

  it("treats a missing/non-failure result as success, never silently drops a failure", () => {
    const failure = makeLog({ payload: { result: "failure", detail: "HTTP 500" } });
    expect(parseActionLog(failure)?.result).toBe("failure");
    expect(parseActionLog(failure)?.detail).toBe("HTTP 500");
  });
});

describe("computeAutomationScore — derived only from real entries", () => {
  it("counts only today's successful entries, sums their real estimated minutes", () => {
    const logs: AdminLogEntry[] = [
      makeLog({ id: 1, created_at: NOW.toISOString(), payload: { result: "success", estimated_minutes: 5 } }),
      makeLog({ id: 2, created_at: NOW.toISOString(), payload: { result: "success", estimated_minutes: 10 } }),
      makeLog({ id: 3, created_at: NOW.toISOString(), payload: { result: "failure" } }),
      makeLog({
        id: 4,
        created_at: new Date(NOW.getTime() - 2 * 86_400_000).toISOString(),
        payload: { result: "success", estimated_minutes: 100 },
      }),
    ];
    const score = computeAutomationScore(logs, 3, NOW);
    expect(score.actionsCompletedToday).toBe(2);
    expect(score.estimatedMinutesSavedToday).toBe(15);
    expect(score.manualStepsAvoidedToday).toBe(2);
    expect(score.pendingConfirmations).toBe(3);
  });

  it("ignores logs from sources other than admin:action.*", () => {
    const logs: AdminLogEntry[] = [
      makeLog({ id: 1, source: "job:observation.tick", created_at: NOW.toISOString(), payload: { result: "success" } }),
    ];
    const score = computeAutomationScore(logs, 0, NOW);
    expect(score.actionsCompletedToday).toBe(0);
  });

  it("treats a missing estimated_minutes as 0, never fabricates a number", () => {
    const logs: AdminLogEntry[] = [makeLog({ id: 1, created_at: NOW.toISOString(), payload: { result: "success" } })];
    const score = computeAutomationScore(logs, 0, NOW);
    expect(score.actionsCompletedToday).toBe(1);
    expect(score.estimatedMinutesSavedToday).toBe(0);
  });

  it("reports zero when there are no entries at all", () => {
    const score = computeAutomationScore([], 0, NOW);
    expect(score).toEqual({
      actionsCompletedToday: 0,
      estimatedMinutesSavedToday: 0,
      manualStepsAvoidedToday: 0,
      pendingConfirmations: 0,
    });
  });
});
