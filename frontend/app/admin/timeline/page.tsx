"use client";

import { useMemo, useState } from "react";
import {
  Activity,
  Bot,
  Calendar,
  CheckCircle2,
  ListTodo,
  MessageCircle,
  Server,
  Sunrise,
  Target,
} from "lucide-react";

import { AdminPageHeader } from "@/components/admin/PageHeader";
import { TimelineEventCard } from "@/components/admin/TimelineEventCard";
import { EmptyState } from "@/components/admin/EmptyState";
import { ErrorState } from "@/components/admin/ErrorState";
import { LoadingRows } from "@/components/admin/LoadingGrid";
import { Badge } from "@/components/admin/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/admin/ui/card";
import {
  useAdminLogs,
  useAllGoals,
  useCalendarEvents,
  useRecentMessages,
  useTasks,
} from "@/lib/admin-api";
import { useLastLogin } from "@/hooks/use-last-login";
import {
  buildTimelineEvents,
  filterRange,
  groupBySection,
  morningActivity,
  summarizeChanges,
} from "@/lib/timeline";
import type { ChangeSummary, TimelineFilter, TimelineSection } from "@/lib/timeline";

const FILTERS: { value: TimelineFilter; label: string }[] = [
  { value: "today", label: "Hoje" },
  { value: "yesterday", label: "Ontem" },
  { value: "7d", label: "7 dias" },
  { value: "30d", label: "30 dias" },
  { value: "everything", label: "Tudo" },
];

const SECTION_ORDER: TimelineSection[] = [
  "recent_conversations",
  "goal_progress",
  "task_progress",
  "calendar_changes",
  "whatsapp_activity",
  "ai_decisions",
  "system_events",
  "observation_engine",
];

const SECTION_LABEL: Record<TimelineSection, string> = {
  recent_conversations: "Conversas recentes",
  goal_progress: "Progresso de metas",
  task_progress: "Progresso de tarefas",
  calendar_changes: "Mudanças na agenda",
  whatsapp_activity: "Atividade do WhatsApp",
  ai_decisions: "Decisões da IA",
  system_events: "Eventos do sistema",
  observation_engine: "Observation Engine",
};

const SECTION_ICON: Record<TimelineSection, React.ElementType> = {
  recent_conversations: MessageCircle,
  goal_progress: Target,
  task_progress: ListTodo,
  calendar_changes: Calendar,
  whatsapp_activity: MessageCircle,
  ai_decisions: Bot,
  system_events: Server,
  observation_engine: Activity,
};

// The list of section groups always operates on a 30-day base fetch,
// independent of the active filter tab — the filter narrows *which of
// those* events are shown; the quick-answer cards ("since yesterday",
// "since last login") need that same wide dataset regardless of which tab
// is currently selected, so one fetch serves both.
//
// observation.tick is fetched as its own small, separate, bounded query —
// not because it's uninteresting, but because a naive "most recent 1000
// rows" fetch lets a routine, high-frequency source crowd out rare real
// events entirely once enough ticks have run since them (see
// admin/router.py::admin_logs's `exclude_source` docstring). This limit is
// generous enough to cover a full day at the default 5-minute tick
// interval (2 rows/tick × 288 ticks/day ≈ 576) with headroom.
const TICK_SAMPLE_LIMIT = 800;

function QuickAnswerCard({ summary }: { summary: ChangeSummary }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{summary.label}</CardTitle>
      </CardHeader>
      <CardContent>
        {summary.totalEvents === 0 ? (
          <p className="text-sm text-muted-foreground">Nada registrado nesse período.</p>
        ) : (
          <div className="flex flex-col gap-2">
            <p className="text-xs text-muted-foreground">
              {summary.totalEvents} evento(s) — {Object.entries(summary.byCategory)
                .map(([category, count]) => `${SECTION_LABEL[category as TimelineSection]}: ${count}`)
                .join(" · ")}
            </p>
            <ul className="flex flex-col gap-2">
              {summary.highlights.map((event) => (
                <TimelineEventCard key={event.id} event={event} />
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function AdminTimelinePage() {
  const [filter, setFilter] = useState<TimelineFilter>("today");
  const now = useMemo(() => new Date(), []);
  const lastLogin = useLastLogin();

  const baseRange = filterRange("30d", now);
  // Two independent queries: real content (tick noise excluded so it can
  // never crowd it out of the 1000-row budget) and a bounded tick sample
  // (just enough to report "still observing regularly" — see
  // TICK_SAMPLE_LIMIT above).
  const logs = useAdminLogs({
    since: baseRange.since?.toISOString(),
    excludeSource: "job:observation.tick",
    limit: 1000,
  });
  const tickLogs = useAdminLogs({
    since: baseRange.since?.toISOString(),
    source: "job:observation.tick",
    limit: TICK_SAMPLE_LIMIT,
  });
  const messages = useRecentMessages(200);
  const goals = useAllGoals();
  const tasks = useTasks();
  const calendarEvents = useCalendarEvents();

  const isLoading =
    logs.isLoading ||
    tickLogs.isLoading ||
    messages.isLoading ||
    goals.isLoading ||
    tasks.isLoading ||
    calendarEvents.isLoading;
  const firstError =
    logs.error ?? tickLogs.error ?? messages.error ?? goals.error ?? tasks.error ?? calendarEvents.error;

  const allEvents = useMemo(
    () =>
      buildTimelineEvents(
        {
          logs: [...(logs.data ?? []), ...(tickLogs.data ?? [])],
          messages: messages.data ?? [],
          goals: goals.data ?? [],
          tasks: tasks.data ?? [],
          calendarEvents: calendarEvents.data ?? [],
        },
        baseRange.since,
        TICK_SAMPLE_LIMIT
      ),
    [logs.data, tickLogs.data, messages.data, goals.data, tasks.data, calendarEvents.data, baseRange.since]
  );

  const activeRange = filterRange(filter, now);
  const filteredEvents = useMemo(
    () =>
      allEvents.filter((event) => {
        const t = new Date(event.timestamp).getTime();
        if (activeRange.since && t < activeRange.since.getTime()) return false;
        if (activeRange.until && t >= activeRange.until.getTime()) return false;
        return true;
      }),
    [allEvents, activeRange.since, activeRange.until]
  );

  const yesterdaySummary = useMemo(() => {
    const since = filterRange("yesterday", now).since as Date;
    return summarizeChanges(allEvents, since, "O que mudou desde ontem?");
  }, [allEvents, now]);

  const lastLoginSummary = useMemo(() => {
    if (!lastLogin) return null;
    return summarizeChanges(allEvents, lastLogin, "O que mudou desde meu último login?");
  }, [allEvents, lastLogin]);

  const mostImportantSummary = useMemo(
    () => summarizeChanges(allEvents, baseRange.since ?? new Date(0), "Mudanças mais importantes (30 dias)"),
    [allEvents, baseRange.since]
  );

  const morning = useMemo(
    () => (filter === "today" || filter === "yesterday" ? morningActivity(filteredEvents, activeRange.since ?? now) : []),
    [filteredEvents, filter, activeRange.since, now]
  );

  const grouped = groupBySection(filteredEvents);

  return (
    <div>
      <AdminPageHeader
        title="Timeline"
        subtitle="A memória operacional do Dario OS: o que aconteceu, por quê, o que mudou e o que vale lembrar — organizado por assunto, não uma lista de logs. (Não confundir com a página Memory — aquela é sobre a memória vetorial/Qdrant.)"
      />

      {isLoading ? (
        <LoadingRows count={6} />
      ) : firstError ? (
        <ErrorState message={(firstError as Error).message} />
      ) : (
        <>
          <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
            <QuickAnswerCard summary={yesterdaySummary} />
            {lastLoginSummary ? (
              <QuickAnswerCard summary={lastLoginSummary} />
            ) : (
              <Card>
                <CardHeader>
                  <CardTitle>O que mudou desde meu último login?</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-muted-foreground">Esta é sua primeira visita registrada nesta sessão.</p>
                </CardContent>
              </Card>
            )}
            <QuickAnswerCard summary={mostImportantSummary} />
          </div>

          <div className="mb-4 flex flex-wrap gap-1.5">
            {FILTERS.map((item) => (
              <Badge
                key={item.value}
                variant={filter === item.value ? "default" : "outline"}
                className="cursor-pointer"
                onClick={() => setFilter(item.value)}
              >
                {item.label}
              </Badge>
            ))}
          </div>

          {morning.length > 0 ? (
            <Card className="mb-4">
              <CardHeader>
                <CardTitle className="flex items-center gap-1.5">
                  <Sunrise className="h-4 w-4" /> Atividade da manhã
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="flex flex-col gap-2">
                  {morning.map((event) => (
                    <TimelineEventCard key={event.id} event={event} />
                  ))}
                </ul>
              </CardContent>
            </Card>
          ) : null}

          {filteredEvents.length === 0 ? (
            <EmptyState
              title="Nada para lembrar neste período"
              description="Ajuste o filtro de período acima para ver mais atividade."
              icon={CheckCircle2}
            />
          ) : (
            SECTION_ORDER.filter((section) => grouped[section]?.length).map((section) => {
              const Icon = SECTION_ICON[section];
              return (
                <Card key={section} className="mb-4">
                  <CardHeader>
                    <CardTitle className="flex items-center gap-1.5">
                      <Icon className="h-4 w-4" /> {SECTION_LABEL[section]}
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ul className="flex flex-col gap-2">
                      {grouped[section]?.map((event) => (
                        <TimelineEventCard key={event.id} event={event} />
                      ))}
                    </ul>
                  </CardContent>
                </Card>
              );
            })
          )}
        </>
      )}
    </div>
  );
}
