import { describe, expect, it } from "vitest";

import {
  buildTimelineEvents,
  filterRange,
  groupBySection,
  morningActivity,
  mostImportantChanges,
  summarizeChanges,
} from "@/lib/timeline";
import type {
  AdminLogEntry,
  CalendarEventRead,
  GoalRead,
  MessageRead,
  TaskRead,
} from "@/lib/admin-types";

const NOW = new Date("2026-07-17T15:00:00Z"); // afternoon, for morningActivity tests

function makeLog(overrides: Partial<AdminLogEntry> = {}): AdminLogEntry {
  return {
    id: 1,
    level: "info",
    source: "webhook",
    message: "something happened",
    payload: {},
    created_at: NOW.toISOString(),
    ...overrides,
  };
}

function makeMessage(overrides: Partial<MessageRead> = {}): MessageRead {
  return {
    id: 1,
    contact_id: 7,
    direction: "inbound",
    media_type: "text",
    content: "oi",
    external_id: null,
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

function makeCalendarEvent(overrides: Partial<CalendarEventRead> = {}): CalendarEventRead {
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

const emptyInput = { logs: [], messages: [], goals: [] as GoalRead[], tasks: [], calendarEvents: [] };

describe("filterRange", () => {
  it("today: since is midnight UTC, no until", () => {
    const range = filterRange("today", NOW);
    expect(range.since?.toISOString()).toBe("2026-07-17T00:00:00.000Z");
    expect(range.until).toBeUndefined();
  });

  it("yesterday: a full calendar day, not a trailing 48h window", () => {
    const range = filterRange("yesterday", NOW);
    expect(range.since?.toISOString()).toBe("2026-07-16T00:00:00.000Z");
    expect(range.until?.toISOString()).toBe("2026-07-17T00:00:00.000Z");
  });

  it("7d: trailing 7-day window from now", () => {
    const range = filterRange("7d", NOW);
    expect(range.since?.toISOString()).toBe("2026-07-10T15:00:00.000Z");
    expect(range.until).toBeUndefined();
  });

  it("30d: trailing 30-day window from now", () => {
    const range = filterRange("30d", NOW);
    expect(range.since?.toISOString()).toBe("2026-06-17T15:00:00.000Z");
  });

  it("everything: no bounds at all", () => {
    expect(filterRange("everything", NOW)).toEqual({});
  });
});

describe("buildTimelineEvents — goal events", () => {
  it("maps an awaiting_approval goal with a suggested follow-up", () => {
    const log = makeLog({
      id: 1,
      source: "goal:5",
      message: "Goal 5 created",
      payload: { goal_id: 5, title: "Orçamento", status: "awaiting_approval", priority: "urgent" },
    });
    const events = buildTimelineEvents({ ...emptyInput, logs: [log] });
    const event = events.find((e) => e.id === "log-1");
    expect(event?.category).toBe("goal_progress");
    expect(event?.actor).toBe("user");
    expect(event?.suggestedFollowUp).toContain("Aprovar");
  });

  it("attributes a recurrence spawn to the system, not the user", () => {
    const log = makeLog({
      id: 2,
      source: "goal:9",
      message: "Goal 9 created",
      payload: { goal_id: 9, title: "Backup", status: "pending", detail: "recurrence" },
    });
    const events = buildTimelineEvents({ ...emptyInput, logs: [log] });
    expect(events.find((e) => e.id === "log-2")?.actor).toBe("system");
  });

  it("raises importance for a completed goal", () => {
    const log = makeLog({
      id: 3,
      source: "goal:1",
      message: "Goal 1 status_changed",
      payload: { title: "Meta", status: "completed" },
    });
    const events = buildTimelineEvents({ ...emptyInput, logs: [log] });
    expect(events.find((e) => e.id === "log-3")?.importance).toBe(70);
  });
});

describe("buildTimelineEvents — job events", () => {
  it("categorizes a whatsapp job under whatsapp_activity", () => {
    const log = makeLog({
      id: 4,
      source: "job:whatsapp.send_text",
      message: "Job 1 succeeded",
      payload: { status: "succeeded" },
    });
    const events = buildTimelineEvents({ ...emptyInput, logs: [log] });
    expect(events.find((e) => e.id === "log-4")?.category).toBe("whatsapp_activity");
  });

  it("categorizes a non-whatsapp job under system_events with low importance when it succeeds", () => {
    const log = makeLog({
      id: 5,
      source: "job:contact.summarize",
      message: "Job 2 succeeded",
      level: "info",
      payload: { status: "succeeded" },
    });
    const events = buildTimelineEvents({ ...emptyInput, logs: [log] });
    const event = events.find((e) => e.id === "log-5");
    expect(event?.category).toBe("system_events");
    expect(event?.importance).toBeLessThan(50);
  });

  it("raises importance and adds a follow-up when a job fails", () => {
    const log = makeLog({
      id: 6,
      source: "job:whatsapp.send_text",
      level: "error",
      message: "Job 3 failed",
      payload: { status: "failed", attempts: 3, detail: "timeout" },
    });
    const events = buildTimelineEvents({ ...emptyInput, logs: [log] });
    const event = events.find((e) => e.id === "log-6");
    expect(event?.importance).toBeGreaterThanOrEqual(80);
    expect(event?.suggestedFollowUp).toBeDefined();
  });

  it("attributes the auto-reply job to the AI, not generic system", () => {
    const log = makeLog({
      id: 7,
      source: "job:whatsapp.process_inbound",
      message: "Job 4 succeeded",
      payload: { status: "succeeded" },
    });
    const events = buildTimelineEvents({ ...emptyInput, logs: [log] });
    expect(events.find((e) => e.id === "log-7")?.actor).toBe("ai");
  });
});

describe("buildTimelineEvents — cognitive pipeline (AI decisions)", () => {
  it("maps a pipeline run needing confirmation with a follow-up", () => {
    const log = makeLog({
      id: 8,
      source: "cognitive_pipeline",
      payload: { intent: "question", priority: "normal", agents: ["assistant"], needs_confirmation: true },
    });
    const events = buildTimelineEvents({ ...emptyInput, logs: [log] });
    const event = events.find((e) => e.id === "log-8");
    expect(event?.category).toBe("ai_decisions");
    expect(event?.actor).toBe("ai");
    expect(event?.suggestedFollowUp).toBeDefined();
  });
});

describe("buildTimelineEvents — admin (user) actions", () => {
  it("attributes a job cancel to the user", () => {
    const log = makeLog({
      id: 9,
      source: "admin:job_cancel",
      payload: { job_id: 3, job_name: "whatsapp.send_text" },
    });
    const events = buildTimelineEvents({ ...emptyInput, logs: [log] });
    expect(events.find((e) => e.id === "log-9")?.actor).toBe("user");
  });
});

describe("buildTimelineEvents — WhatsApp infra events", () => {
  it("flags a session-error event as high importance with a follow-up", () => {
    const log = makeLog({ id: 10, source: "whatsapp:openwa", level: "error", message: "session lost" });
    const events = buildTimelineEvents({ ...emptyInput, logs: [log] });
    const event = events.find((e) => e.id === "log-10");
    expect(event?.category).toBe("whatsapp_activity");
    expect(event?.importance).toBeGreaterThanOrEqual(80);
  });
});

describe("buildTimelineEvents — observation.tick rollup", () => {
  it("rolls up successful ticks into one summary event instead of N raw lines", () => {
    const logs = [
      makeLog({ id: 20, source: "job:observation.tick", message: "Job 100 succeeded" }),
      makeLog({ id: 21, source: "job:observation.tick", message: "Job 100 started" }),
      makeLog({ id: 22, source: "job:observation.tick", message: "Job 99 succeeded" }),
      makeLog({ id: 23, source: "job:observation.tick", message: "Job 99 started" }),
    ];
    const events = buildTimelineEvents({ ...emptyInput, logs });
    const observationEvents = events.filter((e) => e.category === "observation_engine");
    expect(observationEvents).toHaveLength(1);
    expect(observationEvents[0].summary).toContain("2 observação");
  });

  it("never rolls up a failed tick — it's shown as its own noteworthy event", () => {
    const logs = [
      makeLog({ id: 24, source: "job:observation.tick", level: "error", message: "Job 101 failed" }),
      makeLog({ id: 25, source: "job:observation.tick", message: "Job 100 succeeded" }),
    ];
    const events = buildTimelineEvents({ ...emptyInput, logs });
    const observationEvents = events.filter((e) => e.category === "observation_engine");
    expect(observationEvents).toHaveLength(2);
    const failure = observationEvents.find((e) => e.importance >= 75);
    expect(failure?.suggestedFollowUp).toBeDefined();
  });

  it("shows an exact count when the tick sample is smaller than its fetch limit", () => {
    const logs = [
      makeLog({ id: 1, source: "job:observation.tick", message: "Job 1 succeeded" }),
      makeLog({ id: 2, source: "job:observation.tick", message: "Job 2 succeeded" }),
    ];
    const events = buildTimelineEvents({ ...emptyInput, logs }, undefined, 800);
    const rollup = events.find((e) => e.category === "observation_engine");
    expect(rollup?.summary).toContain("2 observação");
    expect(rollup?.summary).not.toContain("+");
  });

  it("labels the count as 'N+' when the tick sample hit its fetch limit — honest about possible truncation", () => {
    const logs = Array.from({ length: 3 }, (_, i) =>
      makeLog({ id: i + 1, source: "job:observation.tick", message: `Job ${i + 1} succeeded` })
    );
    // tickSampleLimit == the number of tick rows fetched: exactly the
    // "might not be all of them" case a real 800-row-capped query would hit.
    const events = buildTimelineEvents({ ...emptyInput, logs }, undefined, 3);
    const rollup = events.find((e) => e.category === "observation_engine");
    expect(rollup?.summary).toContain("3+ observação");
  });
});

describe("buildTimelineEvents — conversations", () => {
  it("attributes an inbound message to the system and an outbound one to the AI", () => {
    const messages = [
      makeMessage({ id: 1, direction: "inbound" }),
      makeMessage({ id: 2, direction: "outbound" }),
    ];
    const events = buildTimelineEvents({ ...emptyInput, messages });
    expect(events.find((e) => e.id === "message-1")?.actor).toBe("system");
    expect(events.find((e) => e.id === "message-2")?.actor).toBe("ai");
  });

  it("truncates long message content in the reason field", () => {
    const messages = [makeMessage({ id: 1, content: "a".repeat(200) })];
    const events = buildTimelineEvents({ ...emptyInput, messages });
    expect(events.find((e) => e.id === "message-1")?.reason.length).toBeLessThan(150);
  });
});

describe("buildTimelineEvents — task progress", () => {
  it("reports a created task and, separately, a completed one", () => {
    const tasks = [
      makeTask({ id: 1, title: "Nova", status: "pending" }),
      makeTask({ id: 2, title: "Feita", status: "done" }),
    ];
    const events = buildTimelineEvents({ ...emptyInput, tasks });
    expect(events.find((e) => e.id === "task-created-1")).toBeDefined();
    expect(events.find((e) => e.id === "task-created-2")).toBeDefined();
    expect(events.find((e) => e.id === "task-done-2")).toBeDefined();
    expect(events.find((e) => e.id === "task-done-1")).toBeUndefined();
  });

  it("excludes a task created before the `since` boundary", () => {
    const oldTask = makeTask({ id: 1, created_at: "2020-01-01T00:00:00Z", updated_at: "2020-01-01T00:00:00Z" });
    const events = buildTimelineEvents({ ...emptyInput, tasks: [oldTask] }, NOW);
    expect(events.find((e) => e.id === "task-created-1")).toBeUndefined();
  });
});

describe("buildTimelineEvents — calendar changes", () => {
  it("reports a created event and, separately, an updated one (best-effort proxy)", () => {
    const created = makeCalendarEvent({ id: 1, title: "Novo" });
    const updated = makeCalendarEvent({
      id: 2,
      title: "Alterado",
      created_at: "2026-07-01T00:00:00Z",
      updated_at: NOW.toISOString(),
    });
    const events = buildTimelineEvents({ ...emptyInput, calendarEvents: [created, updated] });
    expect(events.find((e) => e.id === "calendar-created-1")).toBeDefined();
    expect(events.find((e) => e.id === "calendar-updated-2")).toBeDefined();
    expect(events.find((e) => e.id === "calendar-created-2")).toBeUndefined();
  });
});

describe("buildTimelineEvents — never silently drops an unrecognized log source", () => {
  it("falls back to a generic system event", () => {
    const log = makeLog({ id: 30, source: "some_new_source_nobody_mapped_yet" });
    const events = buildTimelineEvents({ ...emptyInput, logs: [log] });
    expect(events.find((e) => e.id === "log-30")?.category).toBe("system_events");
  });
});

describe("groupBySection", () => {
  it("groups events by category", () => {
    const logs = [
      makeLog({ id: 1, source: "goal:1", payload: { title: "A" } }),
      makeLog({ id: 2, source: "goal:2", payload: { title: "B" } }),
    ];
    const events = buildTimelineEvents({ ...emptyInput, logs });
    const grouped = groupBySection(events);
    expect(grouped.goal_progress).toHaveLength(2);
    expect(grouped.whatsapp_activity).toBeUndefined();
  });
});

describe("morningActivity", () => {
  it("includes an event from 09:00 and excludes one from 14:00, on the same day", () => {
    const morningLog = makeLog({ id: 1, created_at: "2026-07-17T09:00:00Z" });
    const afternoonLog = makeLog({ id: 2, created_at: "2026-07-17T14:00:00Z" });
    const events = buildTimelineEvents({ ...emptyInput, logs: [morningLog, afternoonLog] });
    const morning = morningActivity(events, NOW);
    expect(morning.map((e) => e.id)).toEqual(["log-1"]);
  });
});

describe("mostImportantChanges", () => {
  it("orders by importance descending", () => {
    const logs = [
      makeLog({ id: 1, source: "job:x", level: "info", message: "Job 1 succeeded", payload: { status: "succeeded" } }),
      makeLog({ id: 2, source: "job:whatsapp.send_text", level: "error", message: "Job 2 failed", payload: { status: "failed", attempts: 3 } }),
    ];
    const events = buildTimelineEvents({ ...emptyInput, logs });
    const top = mostImportantChanges(events, 1);
    expect(top[0].id).toBe("log-2");
  });
});

describe("summarizeChanges — 'what changed since X'", () => {
  it("counts events by category and surfaces highlights, since a given timestamp", () => {
    const since = new Date("2026-07-16T00:00:00Z");
    const logs = [
      makeLog({ id: 1, source: "goal:1", payload: { title: "A", status: "completed" }, created_at: "2026-07-16T12:00:00Z" }),
      makeLog({ id: 2, source: "goal:2", payload: { title: "B" }, created_at: "2020-01-01T00:00:00Z" }), // before `since`
    ];
    const events = buildTimelineEvents({ ...emptyInput, logs });
    const summary = summarizeChanges(events, since, "desde ontem");
    expect(summary.label).toBe("desde ontem");
    expect(summary.totalEvents).toBe(1);
    expect(summary.byCategory.goal_progress).toBe(1);
    expect(summary.highlights[0].id).toBe("log-1");
  });
});
