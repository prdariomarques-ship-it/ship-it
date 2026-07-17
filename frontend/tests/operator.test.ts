import { describe, expect, it } from "vitest";

import { buildOperatorInsights, confidenceSummary } from "@/lib/operator";
import type {
  CalendarEventRead,
  CurrentContext,
  GoalRead,
  JobRead,
  TaskRead,
} from "@/lib/admin-types";

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

function makeEvent(overrides: Partial<CalendarEventRead> = {}): CalendarEventRead {
  return {
    id: 1,
    user_id: 1,
    title: "Evento de teste",
    description: null,
    location: null,
    starts_at: NOW.toISOString(),
    ends_at: null,
    reminder_minutes: null,
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

function makeContext(overrides: Partial<CurrentContext> = {}): CurrentContext {
  return {
    user_id: 1,
    generated_at: NOW.toISOString(),
    trigger: "scheduler",
    goals: [],
    tasks: [],
    calendar: [],
    recent_events: [],
    conversations: [],
    pending_work: [],
    memory: [],
    degraded_sources: [],
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

describe("buildOperatorInsights — follow-ups", () => {
  it("flags a goal awaiting approval with an approve action", () => {
    const goal = makeGoal({ id: 5, title: "Aprovar orçamento", requires_approval: true });
    const insights = buildOperatorInsights({ ...baseInput, awaitingApprovalGoals: [goal] });

    const insight = insights.find((i) => i.id === "approve-5");
    expect(insight).toBeDefined();
    expect(insight?.category).toBe("follow_up");
    expect(insight?.action).toEqual({ label: "Aprovar", kind: "approve_goal", targetId: 5 });
    expect(insight?.confidence).toBe("high");
  });

  it("flags a task due within 48h as a follow-up, not a missed task", () => {
    const task = makeTask({ id: 2, due_date: new Date(NOW.getTime() + 24 * 3_600_000).toISOString() });
    const insights = buildOperatorInsights({ ...baseInput, tasks: [task] });

    expect(insights.find((i) => i.id === "followup-task-2")).toBeDefined();
    expect(insights.find((i) => i.id === "missed-2")).toBeUndefined();
  });
});

describe("buildOperatorInsights — missed tasks", () => {
  it("flags an overdue pending task", () => {
    const task = makeTask({ id: 3, due_date: new Date(NOW.getTime() - 3_600_000).toISOString(), priority: "high" });
    const insights = buildOperatorInsights({ ...baseInput, tasks: [task] });

    const insight = insights.find((i) => i.id === "missed-3");
    expect(insight).toBeDefined();
    expect(insight?.category).toBe("missed_task");
    expect(insight?.reason).toContain("alta");
  });

  it("does not flag a completed task even if its due date is in the past", () => {
    const task = makeTask({ id: 4, status: "done", due_date: new Date(NOW.getTime() - 3_600_000).toISOString() });
    const insights = buildOperatorInsights({ ...baseInput, tasks: [task] });
    expect(insights.find((i) => i.id === "missed-4")).toBeUndefined();
  });
});

describe("buildOperatorInsights — highest priority", () => {
  it("surfaces the top ready goals (order preserved, already ranked by backend)", () => {
    const goals = [
      makeGoal({ id: 1, title: "Primeira", priority: "urgent" }),
      makeGoal({ id: 2, title: "Segunda", priority: "medium" }),
    ];
    const insights = buildOperatorInsights({ ...baseInput, readyGoals: goals });

    const first = insights.find((i) => i.id === "priority-goal-1");
    const second = insights.find((i) => i.id === "priority-goal-2");
    expect(first?.severity).toBe("urgent");
    expect(second?.severity).toBe("attention");
  });
});

describe("buildOperatorInsights — calendar conflicts", () => {
  it("detects two overlapping events with explicit end times", () => {
    const a = makeEvent({
      id: 1,
      title: "Call A",
      starts_at: "2026-07-17T10:00:00Z",
      ends_at: "2026-07-17T11:00:00Z",
    });
    const b = makeEvent({
      id: 2,
      title: "Call B",
      starts_at: "2026-07-17T10:30:00Z",
      ends_at: "2026-07-17T11:30:00Z",
    });
    const insights = buildOperatorInsights({ ...baseInput, calendarEvents: [a, b] });

    const conflict = insights.find((i) => i.category === "calendar_conflict");
    expect(conflict).toBeDefined();
    expect(conflict?.confidence).toBe("high");
    expect(conflict?.reason).not.toContain("assumida");
  });

  it("does not flag two back-to-back (non-overlapping) events", () => {
    const a = makeEvent({ id: 1, starts_at: "2026-07-17T10:00:00Z", ends_at: "2026-07-17T11:00:00Z" });
    const b = makeEvent({ id: 2, starts_at: "2026-07-17T11:00:00Z", ends_at: "2026-07-17T12:00:00Z" });
    const insights = buildOperatorInsights({ ...baseInput, calendarEvents: [a, b] });
    expect(insights.find((i) => i.category === "calendar_conflict")).toBeUndefined();
  });

  it("assumes a 30min duration for an event with no end time, and discloses the assumption", () => {
    const a = makeEvent({ id: 1, title: "Sem fim", starts_at: "2026-07-17T10:00:00Z", ends_at: null });
    const b = makeEvent({ id: 2, title: "Logo depois", starts_at: "2026-07-17T10:15:00Z", ends_at: "2026-07-17T10:45:00Z" });
    const insights = buildOperatorInsights({ ...baseInput, calendarEvents: [a, b] });

    const conflict = insights.find((i) => i.category === "calendar_conflict");
    expect(conflict).toBeDefined();
    expect(conflict?.confidence).toBe("medium");
    expect(conflict?.reason).toContain("assumida");
  });

  it("does not double-report the same pair", () => {
    const a = makeEvent({ id: 1, starts_at: "2026-07-17T10:00:00Z", ends_at: "2026-07-17T11:00:00Z" });
    const b = makeEvent({ id: 2, starts_at: "2026-07-17T10:30:00Z", ends_at: "2026-07-17T11:30:00Z" });
    const insights = buildOperatorInsights({ ...baseInput, calendarEvents: [a, b] });
    expect(insights.filter((i) => i.category === "calendar_conflict")).toHaveLength(1);
  });
});

describe("buildOperatorInsights — risk", () => {
  it("flags a failed job with a retry action", () => {
    const job = makeJob({ id: 9, name: "whatsapp.send_text", last_error: "timeout" });
    const insights = buildOperatorInsights({ ...baseInput, failedJobs: [job] });

    const insight = insights.find((i) => i.id === "retry-9");
    expect(insight?.severity).toBe("urgent");
    expect(insight?.action).toEqual({ label: "Tentar novamente", kind: "retry_job", targetId: 9 });
  });

  it("flags WhatsApp disconnected", () => {
    const insights = buildOperatorInsights({ ...baseInput, whatsappConnected: false });
    expect(insights.find((i) => i.id === "risk-whatsapp")?.severity).toBe("urgent");
  });

  it("does not flag WhatsApp when connected", () => {
    const insights = buildOperatorInsights({ ...baseInput, whatsappConnected: true });
    expect(insights.find((i) => i.id === "risk-whatsapp")).toBeUndefined();
  });

  it("flags degraded observation sources", () => {
    const context = makeContext({ degraded_sources: ["goals", "memory"] });
    const insights = buildOperatorInsights({ ...baseInput, context });
    const insight = insights.find((i) => i.id === "risk-observation-degraded");
    expect(insight?.reason).toContain("goals, memory");
  });

  it("flags a goal with a near deadline and low progress", () => {
    const goal = makeGoal({
      id: 7,
      title: "Meta arriscada",
      deadline: new Date(NOW.getTime() + 2 * 86_400_000).toISOString(),
      progress_percent: 20,
    });
    const insights = buildOperatorInsights({ ...baseInput, readyGoals: [goal] });
    expect(insights.find((i) => i.id === "risk-goal-7")).toBeDefined();
  });

  it("does not flag a near-deadline goal with healthy progress", () => {
    const goal = makeGoal({
      id: 8,
      deadline: new Date(NOW.getTime() + 2 * 86_400_000).toISOString(),
      progress_percent: 90,
    });
    const insights = buildOperatorInsights({ ...baseInput, readyGoals: [goal] });
    expect(insights.find((i) => i.id === "risk-goal-8")).toBeUndefined();
  });
});

describe("buildOperatorInsights — opportunity", () => {
  it("flags a goal close to completion", () => {
    const goal = makeGoal({ id: 6, title: "Quase pronta", progress_percent: 85 });
    const insights = buildOperatorInsights({ ...baseInput, readyGoals: [goal] });
    expect(insights.find((i) => i.id === "opportunity-goal-6")).toBeDefined();
  });

  it("flags a quiet system with no urgent work as an opportunity", () => {
    const goal = makeGoal({ id: 1, progress_percent: 10 });
    const insights = buildOperatorInsights({ ...baseInput, readyGoals: [goal] });
    expect(insights.find((i) => i.id === "opportunity-quiet")).toBeDefined();
  });

  it("does not claim a quiet system when a task is overdue", () => {
    const goal = makeGoal({ id: 1 });
    const task = makeTask({ id: 1, due_date: new Date(NOW.getTime() - 3_600_000).toISOString() });
    const insights = buildOperatorInsights({ ...baseInput, readyGoals: [goal], tasks: [task] });
    expect(insights.find((i) => i.id === "opportunity-quiet")).toBeUndefined();
  });
});

describe("buildOperatorInsights — automatable", () => {
  it("flags a recurring goal as already automated", () => {
    const goal = makeGoal({ id: 10, title: "Backup semanal", recurrence_interval_days: 7 });
    const insights = buildOperatorInsights({ ...baseInput, readyGoals: [goal] });
    const insight = insights.find((i) => i.id === "automatable-goal-10");
    expect(insight?.reason).toContain("7 dia(s)");
  });

  it("surfaces pending background jobs as automated work already running", () => {
    const job = makeJob({ id: 1, status: "queued" });
    const insights = buildOperatorInsights({ ...baseInput, pendingJobs: [job] });
    expect(insights.find((i) => i.id === "automatable-jobs")).toBeDefined();
  });
});

describe("buildOperatorInsights — recently observed changes", () => {
  it("reports a count delta between two CurrentContext snapshots", () => {
    const previous = makeContext({ goals: [{ source: "goal", content: "a" }] });
    const current = makeContext({
      goals: [
        { source: "goal", content: "a" },
        { source: "goal", content: "b" },
      ],
    });
    const insights = buildOperatorInsights({ ...baseInput, context: current, previousContext: previous });
    const insight = insights.find((i) => i.id === "change-goals");
    expect(insight?.title).toBe("Metas: 1 → 2");
    expect(insight?.reason).toContain("+1");
  });

  it("reports nothing when there is no previous snapshot to diff against", () => {
    const current = makeContext({ goals: [{ source: "goal", content: "a" }] });
    const insights = buildOperatorInsights({ ...baseInput, context: current, previousContext: undefined });
    expect(insights.filter((i) => i.category === "recent_change")).toHaveLength(0);
  });

  it("reports nothing when nothing changed", () => {
    const snapshot = makeContext({ goals: [{ source: "goal", content: "a" }] });
    const insights = buildOperatorInsights({ ...baseInput, context: snapshot, previousContext: snapshot });
    expect(insights.filter((i) => i.category === "recent_change")).toHaveLength(0);
  });
});

describe("confidenceSummary", () => {
  it("reports no recommendations when the list is empty", () => {
    expect(confidenceSummary([])).toBe("Nenhuma recomendação no momento.");
  });

  it("counts high-confidence insights out of the total", () => {
    const insights = buildOperatorInsights({
      ...baseInput,
      failedJobs: [makeJob({ id: 1 })],
      readyGoals: [makeGoal({ id: 1, progress_percent: 85 })],
    });
    const highCount = insights.filter((i) => i.confidence === "high").length;
    expect(confidenceSummary(insights)).toBe(
      `${highCount} de ${insights.length} recomendações são de alta confiança (baseadas em dados diretos, não inferência).`
    );
  });
});
