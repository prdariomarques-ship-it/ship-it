import { describe, expect, it } from "vitest";

import { buildDailyBriefing } from "@/lib/briefing";
import type {
  AdminLogEntry,
  CalendarEventRead,
  GoalRead,
  JobRead,
  MessageRead,
  TaskRead,
} from "@/lib/admin-types";
import type { CurrentContext } from "@/lib/admin-types";

const NOW = new Date("2026-07-17T09:00:00Z"); // Friday, 09:00 UTC

function makeGoal(overrides: Partial<GoalRead> = {}): GoalRead {
  return {
    id: 1,
    user_id: 1,
    title: "Meta",
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
    title: "Tarefa",
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
    title: "Evento",
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

const emptyContext: CurrentContext = {
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
};

const baseInput = {
  readyGoals: [] as GoalRead[],
  awaitingApprovalGoals: [] as GoalRead[],
  tasks: [] as TaskRead[],
  calendarEvents: [] as CalendarEventRead[],
  failedJobs: [] as JobRead[],
  pendingJobs: [] as JobRead[],
  context: emptyContext,
  previousContext: undefined,
  logs: [] as AdminLogEntry[],
  messages: [] as MessageRead[],
  goals: [] as GoalRead[],
  now: NOW,
  lastLogin: null as Date | null,
  whatsappConnected: true as boolean | undefined,
};

describe("buildDailyBriefing — health score", () => {
  it("scores a perfectly quiet day at 100 with no deductions", () => {
    const briefing = buildDailyBriefing(baseInput);
    expect(briefing.healthScore.score).toBe(100);
    expect(briefing.healthScore.deductions).toHaveLength(0);
    expect(briefing.healthScore.formula).toContain("nenhum problema");
  });

  it("deducts 5 points per overdue task, capped at 25", () => {
    const overdueTasks = Array.from({ length: 10 }, (_, i) =>
      makeTask({ id: i + 1, due_date: new Date(NOW.getTime() - 3_600_000).toISOString() })
    );
    const briefing = buildDailyBriefing({ ...baseInput, tasks: overdueTasks });
    const deduction = briefing.healthScore.deductions.find((d) => d.label === "Tarefas atrasadas");
    expect(deduction?.points).toBe(25); // capped, not 50
    expect(briefing.healthScore.score).toBe(75);
  });

  it("deducts for WhatsApp disconnected and explains why", () => {
    const briefing = buildDailyBriefing({ ...baseInput, whatsappConnected: false });
    const deduction = briefing.healthScore.deductions.find((d) => d.label === "Saúde do sistema");
    expect(deduction?.points).toBe(20);
    expect(deduction?.reason).toContain("WhatsApp desconectado");
  });

  it("deducts for a failed job under 'pending actions'", () => {
    const briefing = buildDailyBriefing({ ...baseInput, failedJobs: [makeJob({ id: 1 })] });
    const deduction = briefing.healthScore.deductions.find((d) => d.label === "Ações pendentes");
    expect(deduction?.points).toBe(10);
  });

  it("never goes below 0 even with many compounding problems", () => {
    const briefing = buildDailyBriefing({
      ...baseInput,
      tasks: Array.from({ length: 20 }, (_, i) => makeTask({ id: i + 1, due_date: new Date(NOW.getTime() - 3_600_000).toISOString() })),
      awaitingApprovalGoals: Array.from({ length: 10 }, (_, i) => makeGoal({ id: i + 1, requires_approval: true })),
      failedJobs: Array.from({ length: 10 }, (_, i) => makeJob({ id: i + 1 })),
      whatsappConnected: false,
      context: { ...emptyContext, degraded_sources: ["goals", "tasks", "calendar"] },
    });
    expect(briefing.healthScore.score).toBe(0);
  });

  it("builds a readable formula string reflecting every deduction", () => {
    const briefing = buildDailyBriefing({ ...baseInput, whatsappConnected: false });
    expect(briefing.healthScore.formula).toBe("100 - 20 = 80");
  });
});

describe("buildDailyBriefing — recommendations carry decision support", () => {
  it("every top priority has whyNow and consequenceIfIgnored, not just the underlying insight", () => {
    const job = makeJob({ id: 1, name: "whatsapp.send_text" });
    const briefing = buildDailyBriefing({ ...baseInput, failedJobs: [job] });
    const rec = briefing.risks.find((r) => r.insight.id === "retry-1");
    expect(rec?.whyNow).toBeTruthy();
    expect(rec?.consequenceIfIgnored).toBeTruthy();
    expect(rec?.insight.confidence).toBeGreaterThan(0);
  });

  it("an automatable item's consequence-if-ignored is explicitly 'none'", () => {
    const goal = makeGoal({ id: 1, recurrence_interval_days: 7 });
    const briefing = buildDailyBriefing({ ...baseInput, readyGoals: [goal] });
    const rec = briefing.automations.find((r) => r.insight.id === "automatable-goal-1");
    expect(rec?.consequenceIfIgnored).toContain("Nenhuma");
  });
});

describe("buildDailyBriefing — execution plan", () => {
  it("places a calendar event in the period matching its actual start time", () => {
    const morningEvent = makeEvent({ id: 1, title: "Reunião matinal", starts_at: "2026-07-17T09:00:00Z" });
    const eveningEvent = makeEvent({ id: 2, title: "Jantar", starts_at: "2026-07-17T20:00:00Z" });
    const briefing = buildDailyBriefing({ ...baseInput, calendarEvents: [morningEvent, eveningEvent] });

    const morningItem = briefing.executionPlan.find((i) => i.title === "Reunião matinal");
    const eveningItem = briefing.executionPlan.find((i) => i.title === "Jantar");
    expect(morningItem?.period).toBe("morning");
    expect(eveningItem?.period).toBe("evening");
  });

  it("computes a calendar event's duration from starts_at/ends_at", () => {
    const event = makeEvent({ id: 1, starts_at: "2026-07-17T09:00:00Z", ends_at: "2026-07-17T09:30:00Z" });
    const briefing = buildDailyBriefing({ ...baseInput, calendarEvents: [event] });
    expect(briefing.executionPlan[0].estimatedMinutes).toBe(30);
  });

  it("front-loads an urgent (non-calendar) item into the morning", () => {
    const job = makeJob({ id: 1 });
    const briefing = buildDailyBriefing({ ...baseInput, failedJobs: [job] });
    const item = briefing.executionPlan.find((i) => i.title.includes("test.job"));
    expect(item?.period).toBe("morning");
  });

  it("places a today-bucket (not urgent) item into the afternoon", () => {
    const goal = makeGoal({ id: 1, requires_approval: true, title: "Aprovar X" });
    const briefing = buildDailyBriefing({ ...baseInput, awaitingApprovalGoals: [goal] });
    const item = briefing.executionPlan.find((i) => i.title.includes("Aprovar X"));
    expect(item?.period).toBe("afternoon");
  });

  it("sorts the plan morning-first regardless of insertion order", () => {
    const eveningEvent = makeEvent({ id: 1, title: "Noite", starts_at: "2026-07-17T21:00:00Z" });
    const job = makeJob({ id: 1 }); // urgent -> morning
    const briefing = buildDailyBriefing({ ...baseInput, calendarEvents: [eveningEvent], failedJobs: [job] });
    const periods = briefing.executionPlan.map((i) => i.period);
    expect(periods.indexOf("morning")).toBeLessThan(periods.indexOf("evening"));
  });
});

describe("buildDailyBriefing — greeting and closing line", () => {
  it("mentions overdue follow-ups, calendar conflicts, and WhatsApp status by name", () => {
    const task = makeTask({ id: 1, due_date: new Date(NOW.getTime() - 3_600_000).toISOString() });
    const briefing = buildDailyBriefing({ ...baseInput, tasks: [task], whatsappConnected: false });
    expect(briefing.greeting).toContain("atrasada");
    expect(briefing.greeting).toContain("desconectado");
  });

  it("says nothing is overdue and no conflicts exist on a genuinely quiet day", () => {
    const briefing = buildDailyBriefing(baseInput);
    expect(briefing.greeting).toContain("Nenhum follow-up importante está atrasado");
    expect(briefing.greeting).toContain("Não há conflitos de agenda");
  });

  it("closes with the single top priority when one exists", () => {
    const job = makeJob({ id: 1, name: "important.job" });
    const briefing = buildDailyBriefing({ ...baseInput, failedJobs: [job] });
    expect(briefing.closingLine).toContain("important.job");
  });

  it("closes with a fallback message when nothing is actionable", () => {
    const briefing = buildDailyBriefing(baseInput);
    expect(briefing.closingLine).toContain("não há nada urgente pendente");
  });
});

describe("buildDailyBriefing — changes since yesterday / last login", () => {
  it("reports null for 'since last login' when there is no previous login", () => {
    const briefing = buildDailyBriefing({ ...baseInput, lastLogin: null });
    expect(briefing.changedSinceLastLogin).toBeNull();
  });

  it("computes 'since last login' when a previous login timestamp exists", () => {
    const briefing = buildDailyBriefing({ ...baseInput, lastLogin: new Date("2026-07-16T00:00:00Z") });
    expect(briefing.changedSinceLastLogin).not.toBeNull();
    expect(briefing.changedSinceLastLogin?.label).toBe("Desde seu último login");
  });
});

describe("buildDailyBriefing — executive summary", () => {
  it("names the biggest risk and biggest opportunity when they exist", () => {
    const failedJob = makeJob({ id: 1, name: "risky.job" });
    const goal = makeGoal({ id: 1, title: "Quase lá", progress_percent: 90 });
    const briefing = buildDailyBriefing({ ...baseInput, failedJobs: [failedJob], readyGoals: [goal] });
    expect(briefing.executiveSummary.biggestRisk).toContain("risky.job");
    expect(briefing.executiveSummary.biggestOpportunity).toContain("Quase lá");
  });

  it("reports null for biggest risk/opportunity when none exist", () => {
    const briefing = buildDailyBriefing(baseInput);
    expect(briefing.executiveSummary.biggestRisk).toBeNull();
    expect(briefing.executiveSummary.biggestOpportunity).toBeNull();
  });
});
