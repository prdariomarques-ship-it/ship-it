import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/hooks/useApi", () => ({ apiFetch: vi.fn() }));

import { DariusPanel } from "@/components/darius/DariusPanel";
import { renderWithQueryClient } from "./test-utils";
import { apiError, ROUTING, serve, TASK } from "./darius-test-utils";

const METRICS = {
  generatedAt: 1760900000000,
  scope: { durable: "store" },
  tasks: {
    available: true,
    total: 7,
    byStatus: { PENDING: 0, QUEUED: 2, RUNNING: 1, PAUSED: 1, COMPLETED: 2, FAILED: 1, CANCELLED: 0 },
  },
  queue: { queued: 2, backingOff: 1, nextRetryAt: 1760900005000 },
  engine: {
    consumer: { running: true, inflight: 1, startedTotal: 3, lastPassAt: 1760899999000 },
    recovery: { running: true, sweeps: 9, requeuedTotal: 0, lastSweepAt: null },
    retry: { enabled: true, maxRetries: 3, scheduledTotal: 2, exhaustedTotal: 0 },
  },
  scheduler: { enabled: false },
};

const figure = (label: string) => screen.getByText(label).closest("div")!;

describe("Metrics", () => {
  it("shows what the runtime reported, and 'indisponível' (never 0) for what it did not", async () => {
    serve({ "/admin/darius/metrics": METRICS });
    renderWithQueryClient(<DariusPanel initialTab="metrics" />);
    expect(await screen.findByText("Fila e retry automático")).toBeInTheDocument();
    expect(within(figure("Total")).getByText("7")).toBeInTheDocument();
    expect(within(figure("Na fila")).getByText("2")).toBeInTheDocument();
    expect(within(figure("Em espera (backoff)")).getByText("1")).toBeInTheDocument();
    expect(within(figure("Retries agendados")).getByText("2")).toBeInTheDocument();
    // lastSweepAt is null in the payload: it must NOT render as a date or as 0
    expect(within(figure("Última varredura")).getByText("indisponível")).toBeInTheDocument();
    expect(screen.getByText(/Retry ligado \(máx\. 3 tentativas/)).toBeInTheDocument();
    expect(screen.getByText(/Agendador desligado neste DARIUS/)).toBeInTheDocument();
  });

  it("says retry is off, and marks missing counters unavailable on a sparse runtime", async () => {
    serve({
      "/admin/darius/metrics": {
        ...METRICS,
        queue: {},
        engine: { retry: { enabled: false } },
        tasks: { available: false },
      },
    });
    renderWithQueryClient(<DariusPanel initialTab="metrics" />);
    expect(await screen.findByText(/Retry automático desligado/)).toBeInTheDocument();
    expect(screen.getByText(/armazenamento de tarefas não informou contagens/)).toBeInTheDocument();
    expect(within(figure("Na fila")).getByText("indisponível")).toBeInTheDocument();
    expect(within(figure("Consumidor")).getByText("indisponível")).toBeInTheDocument();
  });

  it("lists scheduler counters only when the scheduler is on", async () => {
    serve({ "/admin/darius/metrics": { ...METRICS, scheduler: { enabled: true, fired: 4, lostCas: 0 } } });
    renderWithQueryClient(<DariusPanel initialTab="metrics" />);
    expect(await screen.findByText("fired")).toBeInTheDocument();
    expect(within(figure("fired")).getByText("4")).toBeInTheDocument();
    expect(within(figure("lostCas")).getByText("0")).toBeInTheDocument();
  });

  it("explains an unreachable DARIUS instead of showing numbers", async () => {
    serve({
      "/admin/darius/metrics": apiError("DARIUS indisponível", 502, { message: "DARIUS indisponível", code: "DARIUS_UNAVAILABLE" }),
    });
    renderWithQueryClient(<DariusPanel initialTab="metrics" />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("DARIUS indisponível");
    expect(alert).toHaveTextContent("inacessível");
    expect(screen.queryByText("Na fila")).not.toBeInTheDocument();
  });

  it("shows a loading state first", () => {
    serve({ "/admin/darius/metrics": new Promise(() => undefined) });
    renderWithQueryClient(<DariusPanel initialTab="metrics" />);
    expect(screen.queryByText("Na fila")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

const PAUSED = {
  items: [
    {
      contact_id: 5, contact_name: "Ana", phone_tail: "0001", instance: "store", revision: 3,
      paused_since: "2026-10-19T10:00:00Z", reason: "dono assumiu", actor_id: 1, send_in_flight: false,
    },
    {
      contact_id: 6, contact_name: null, phone_tail: null, instance: "personal", revision: 1,
      paused_since: null, reason: null, actor_id: null, send_in_flight: true,
    },
  ],
  total: 2,
  next_offset: null,
};

describe("Paused conversations", () => {
  it("lists them with a masked phone, the reason and the in-flight marker", async () => {
    serve({ "/admin/darius/paused-conversations": PAUSED, "/admin/darius/whatsapp-routing": ROUTING });
    renderWithQueryClient(<DariusPanel initialTab="paused" />);
    expect(await screen.findByText("Ana")).toBeInTheDocument();
    expect(screen.getByText(/…0001/)).toBeInTheDocument();
    expect(screen.getByText("dono assumiu")).toBeInTheDocument();
    expect(screen.getByText("2 conversa(s) pausada(s)")).toBeInTheDocument();
    expect(screen.getByText("Contato 6")).toBeInTheDocument();
    expect(screen.getByText("sem motivo registrado")).toBeInTheDocument();
    expect(screen.getByText("envio em andamento")).toBeInTheDocument();
    expect(screen.getByText("indisponível")).toBeInTheDocument(); // paused_since null
    expect(document.body.textContent).not.toMatch(/55\d{9,}/); // a full number never reaches the DOM
  });

  it("filters by instance and pages with the server cursor", async () => {
    const user = userEvent.setup();
    const api = serve({
      "/admin/darius/paused-conversations": (path: string) =>
        path.includes("offset=25") ? { ...PAUSED, items: [PAUSED.items[0]], next_offset: null } : { ...PAUSED, total: 30, next_offset: 25 },
      "/admin/darius/whatsapp-routing": ROUTING,
    });
    renderWithQueryClient(<DariusPanel initialTab="paused" />);
    await screen.findByText("Ana");
    await user.click(screen.getByRole("button", { name: "Próxima" }));
    await waitFor(() => expect(api.paths().some((p) => p.includes("limit=25") && p.includes("offset=25"))).toBe(true));
    await user.selectOptions(await screen.findByLabelText("Instância"), "store");
    await waitFor(() => expect(api.paths().some((p) => p.includes("instance=store") && p.includes("offset=0"))).toBe(true));
  });

  it("has empty and error states, and offers no way to act on a conversation", async () => {
    serve({ "/admin/darius/paused-conversations": { items: [], total: 0, next_offset: null }, "/admin/darius/whatsapp-routing": ROUTING });
    const { unmount } = renderWithQueryClient(<DariusPanel initialTab="paused" />);
    expect(await screen.findByText("Nenhuma conversa pausada")).toBeInTheDocument();
    unmount();

    serve({ "/admin/darius/paused-conversations": apiError("Acesso negado", 403), "/admin/darius/whatsapp-routing": ROUTING });
    renderWithQueryClient(<DariusPanel initialTab="paused" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Acesso negado");
    expect(screen.queryByRole("button", { name: /retomar|pausar/i })).not.toBeInTheDocument();
  });
});

describe("Task detail: failure class and retry", () => {
  const detail = (result: Record<string, unknown>) => ({
    "/admin/darius/tasks/": (path: string) =>
      path.endsWith("/result")
        ? { id: TASK.id, updatedAt: TASK.updatedAt, ...result }
        : { taskId: TASK.id, objective: TASK.objective, status: "FAILED", currentState: "ACT", iterations: 1, trace: [] },
    "/admin/darius/tasks": { items: [{ ...TASK, status: "FAILED" }], total: 1, next_offset: null },
  });

  it("warns that an EFFECT_UNKNOWN failure is not retried automatically", async () => {
    const user = userEvent.setup();
    serve(detail({ status: "FAILED", done: true, error: "x", failureClass: "EFFECT_UNKNOWN" }));
    renderWithQueryClient(<DariusPanel initialTab="tasks" />);
    await user.click(await screen.findByRole("button", { name: /Ver 11111111/ }));
    expect(await screen.findByText("Classe da falha: EFFECT_UNKNOWN")).toBeInTheDocument();
    expect(screen.getByText(/NÃO é repetida automaticamente/)).toBeInTheDocument();
  });

  it("shows the scheduled automatic attempt of a queued task", async () => {
    const user = userEvent.setup();
    serve(detail({ status: "QUEUED", done: false, retry: { attempts: 2, nextAttemptAt: 1760900005000 } }));
    renderWithQueryClient(<DariusPanel initialTab="tasks" />);
    await user.click(await screen.findByRole("button", { name: /Ver 11111111/ }));
    expect(await screen.findByText(/Tentativa automática agendada: 2 já feita\(s\)/)).toBeInTheDocument();
  });

  it("stays quiet on runtimes that report neither field", async () => {
    const user = userEvent.setup();
    serve(detail({ status: "COMPLETED", done: true, result: "ok" }));
    renderWithQueryClient(<DariusPanel initialTab="tasks" />);
    await user.click(await screen.findByRole("button", { name: /Ver 11111111/ }));
    await screen.findByText("ok");
    expect(screen.queryByText(/Classe da falha/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Tentativa automática/)).not.toBeInTheDocument();
  });

  it("renders an unknown future class without breaking", async () => {
    const user = userEvent.setup();
    serve(detail({ status: "FAILED", done: true, failureClass: "SOMETHING_NEW" }));
    renderWithQueryClient(<DariusPanel initialTab="tasks" />);
    await user.click(await screen.findByRole("button", { name: /Ver 11111111/ }));
    expect(await screen.findByText(/classe não reconhecida por este painel/)).toBeInTheDocument();
  });
});
