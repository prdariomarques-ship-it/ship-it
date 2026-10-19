import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/hooks/useApi", () => ({ apiFetch: vi.fn() }));

import AdminDariusPage from "@/app/admin/darius/page";
import { DariusPanel } from "@/components/darius/DariusPanel";
import { renderWithQueryClient } from "./test-utils";
import { apiError, DARIUS_OK, LINKS, ROUTING, serve, SUSPENSION, TASK } from "./darius-test-utils";

const page = (items: unknown[], total = items.length, next_offset: number | null = null) => ({ items, total, next_offset });

describe("DARIUS page", () => {
  it("renders the title and all six sections as tabs", async () => {
    serve({
      "/admin/darius/status": DARIUS_OK,
      "/admin/darius/tasks": page([]),
      "/admin/darius/whatsapp-tasks": LINKS,
      "/admin/darius/whatsapp-routing": ROUTING,
      "/admin/automation/suspension": SUSPENSION,
    });
    renderWithQueryClient(<AdminDariusPage />);
    expect(screen.getByRole("heading", { name: "DARIUS" })).toBeInTheDocument();
    for (const name of ["Visão geral", "Tarefas", "Aprovações", "WhatsApp", "Suspensão", "Logs"]) {
      expect(screen.getByRole("tab", { name })).toBeInTheDocument();
    }
    expect(screen.getByRole("tab", { name: "Visão geral" })).toHaveAttribute("aria-selected", "true");
  });
});

describe("Overview", () => {
  it("shows the measured service state and real figures", async () => {
    serve({
      "/admin/darius/status": DARIUS_OK,
      "/admin/darius/tasks": page([TASK], 3),
      "/admin/darius/whatsapp-tasks": LINKS,
      "/admin/darius/whatsapp-routing": ROUTING,
      "/admin/automation/suspension": SUSPENSION,
    });
    renderWithQueryClient(<DariusPanel />);
    expect(await screen.findByText("12.5 ms")).toBeInTheDocument();
    expect(screen.getByText("acessível")).toBeInTheDocument();
    // 3 waiting approval, 4 routed messages (1+1+2), 3 failed+expired, 1 suspended scope
    const figure = (label: string) => screen.getByText(label).closest("div")!.parentElement!;
    await waitFor(() => expect(within(figure("Aguardando aprovação")).getByText("3")).toBeInTheDocument());
    expect(within(figure("WhatsApp → DARIUS")).getByText("4")).toBeInTheDocument();
    expect(within(figure("Falhas / expiradas")).getByText("3")).toBeInTheDocument();
    expect(within(figure("Escopos suspensos")).getByText("1")).toBeInTheDocument();
  });

  it("says 'indisponível' (never 0) when DARIUS is unreachable and its endpoints fail", async () => {
    serve({
      "/admin/darius/status": { ...DARIUS_OK, reachable: false, latency_ms: null, error: "DARIUS_UNAVAILABLE" },
      "/admin/darius/tasks": apiError("DARIUS indisponível", 502, { message: "DARIUS indisponível", code: "DARIUS_UNAVAILABLE" }),
      "/admin/darius/whatsapp-tasks": apiError("falhou", 500),
      "/admin/darius/whatsapp-routing": ROUTING,
      "/admin/automation/suspension": apiError("falhou", 500),
    });
    renderWithQueryClient(<DariusPanel />);
    expect(await screen.findByRole("alert")).toHaveTextContent("DARIUS_UNAVAILABLE");
    await waitFor(() => expect(screen.getAllByText("indisponível").length).toBeGreaterThanOrEqual(5));
    const paused = screen.getByText("Aguardando aprovação").closest("div")!.parentElement!;
    expect(within(paused).queryByText("0")).not.toBeInTheDocument();
  });

  it("explains a backend without a configured DARIUS", async () => {
    serve({
      "/admin/darius/status": {
        ...DARIUS_OK, configured: false, reachable: false, latency_ms: null, error: "DARIUS_NOT_CONFIGURED", base_url: "",
      },
      "/admin/darius/tasks": apiError("não configurado", 503, { message: "não configurado", code: "DARIUS_NOT_CONFIGURED" }),
      "/admin/darius/whatsapp-tasks": { items: [], counts: {}, next_offset: null },
      "/admin/darius/whatsapp-routing": { ...ROUTING, enabled: false },
      "/admin/automation/suspension": SUSPENSION,
    });
    renderWithQueryClient(<DariusPanel />);
    expect(await screen.findByText(/DARIUS não configurado neste backend/)).toBeInTheDocument();
    expect(await screen.findByText(/roteamento WhatsApp→DARIUS está desligado/)).toBeInTheDocument();
  });

  it("jumps to a section from a figure", async () => {
    const user = userEvent.setup();
    serve({
      "/admin/darius/status": DARIUS_OK,
      "/admin/darius/tasks": page([TASK], 1),
      "/admin/darius/whatsapp-tasks": LINKS,
      "/admin/darius/whatsapp-routing": ROUTING,
      "/admin/automation/suspension": SUSPENSION,
    });
    renderWithQueryClient(<DariusPanel />);
    await user.click(await screen.findByRole("button", { name: "Abrir suspensão" }));
    expect(screen.getByRole("tab", { name: "Suspensão" })).toHaveAttribute("aria-selected", "true");
  });
});

describe("Tasks", () => {
  it("lists tasks, filters by status and pages with the server cursor", async () => {
    const user = userEvent.setup();
    const api = serve({
      "/admin/darius/tasks": (path: string) =>
        path.includes("offset=25") ? page([{ ...TASK, id: "second-page", status: "COMPLETED" }], 30) : page([TASK], 30, 25),
    });
    renderWithQueryClient(<DariusPanel initialTab="tasks" />);
    expect(await screen.findByText(TASK.objective)).toBeInTheDocument();
    expect(screen.getByText("30 tarefa(s)")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Próxima" }));
    expect(await screen.findByRole("button", { name: /Ver second-p/ })).toBeInTheDocument();
    expect(api.paths().some((p) => p.includes("limit=25") && p.includes("offset=25"))).toBe(true);

    await user.selectOptions(screen.getByLabelText("Estado"), "FAILED");
    await waitFor(() => expect(api.paths().some((p) => p.includes("status=FAILED") && p.includes("offset=0"))).toBe(true));
  });

  it("shows an empty state and an explained error", async () => {
    serve({ "/admin/darius/tasks": page([]) });
    const { unmount } = renderWithQueryClient(<DariusPanel initialTab="tasks" />);
    expect(await screen.findByText("Nenhuma tarefa")).toBeInTheDocument();
    unmount();

    serve({
      "/admin/darius/tasks": apiError("sem rede", 502, { message: "sem rede", code: "DARIUS_UNAVAILABLE" }),
    });
    renderWithQueryClient(<DariusPanel initialTab="tasks" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("sem rede");
    expect(screen.getByRole("alert")).toHaveTextContent("inacessível");
  });

  it("opens a task with its result and execution trail", async () => {
    const user = userEvent.setup();
    const api = serve({
      "/admin/darius/tasks/": (path: string) =>
        path.endsWith("/result")
          ? { id: TASK.id, status: "COMPLETED", done: true, result: "Contrato enviado.", error: null, updatedAt: TASK.updatedAt }
          : {
              taskId: TASK.id, objective: TASK.objective, status: "COMPLETED", currentState: "VERIFY", iterations: 2,
              trace: [{ state: "THINK", timestamp: TASK.createdAt }, { state: "ACT", error: "timeout simulado" }],
            },
      "/admin/darius/tasks": page([{ ...TASK, status: "COMPLETED" }]),
    });
    renderWithQueryClient(<DariusPanel initialTab="tasks" />);
    await user.click(await screen.findByRole("button", { name: /Ver 11111111/ }));
    expect(await screen.findByText("Contrato enviado.")).toBeInTheDocument();
    expect(screen.getByText("timeout simulado")).toBeInTheDocument();
    expect(screen.getByText(/iterações: 2/)).toBeInTheDocument();
    expect(api.paths()).toContain(`/admin/darius/tasks/${encodeURIComponent(TASK.id)}/result`);
    await user.click(screen.getByRole("button", { name: "Fechar" }));
    expect(screen.queryByText("Contrato enviado.")).not.toBeInTheDocument();
  });
});

describe("Approvals", () => {
  const paused = () => ({ "/admin/darius/tasks": page([TASK], 1) });

  it("lists only PAUSED tasks and sends nothing before the explicit confirmation", async () => {
    const user = userEvent.setup();
    const api = serve(paused());
    renderWithQueryClient(<DariusPanel initialTab="approvals" />);
    expect(await screen.findByText(TASK.objective)).toBeInTheDocument();
    expect(api.paths().every((p) => p.includes("status=PAUSED"))).toBe(true);

    await user.click(screen.getByRole("button", { name: `Aprovar ${TASK.id}` }));
    expect(screen.getByRole("group", { name: "Confirmar decisão" })).toBeInTheDocument();
    expect(api.posts()).toHaveLength(0);
  });

  it("approves after confirmation and reports it", async () => {
    const user = userEvent.setup();
    const api = serve({
      "/admin/darius/tasks/": { id: TASK.id, status: "RUNNING", decision: "APPROVED" },
      ...paused(),
    });
    renderWithQueryClient(<DariusPanel initialTab="approvals" />);
    await user.click(await screen.findByRole("button", { name: `Aprovar ${TASK.id}` }));
    await user.click(screen.getByRole("button", { name: "Confirmar" }));
    await waitFor(() => expect(screen.getByText(`Tarefa ${TASK.id} aprovada.`)).toBeInTheDocument());
    expect(api.posts()).toHaveLength(1);
    expect(api.posts()[0].path).toBe(`/admin/darius/tasks/${encodeURIComponent(TASK.id)}/approve`);
    expect(api.posts()[0].options?.method).toBe("POST");
  });

  it("rejects with the typed reason", async () => {
    const user = userEvent.setup();
    const api = serve({ "/admin/darius/tasks/": { id: TASK.id, status: "CANCELLED", decision: "REJECTED" }, ...paused() });
    renderWithQueryClient(<DariusPanel initialTab="approvals" />);
    await user.click(await screen.findByRole("button", { name: `Rejeitar ${TASK.id}` }));
    await user.type(screen.getByLabelText("Motivo da rejeição"), "valor fora do combinado");
    await user.click(screen.getByRole("button", { name: "Confirmar" }));
    await waitFor(() => expect(api.posts()).toHaveLength(1));
    expect(api.posts()[0].path.endsWith("/reject")).toBe(true);
    expect(JSON.parse(String(api.posts()[0].options?.body))).toEqual({ reason: "valor fora do combinado" });
  });

  it("cancels through the cancel endpoint without a body", async () => {
    const user = userEvent.setup();
    const api = serve({ "/admin/darius/tasks/": { id: TASK.id, status: "CANCELLED" }, ...paused() });
    renderWithQueryClient(<DariusPanel initialTab="approvals" />);
    await user.click(await screen.findByRole("button", { name: `Cancelar tarefa ${TASK.id}` }));
    await user.click(screen.getByRole("button", { name: "Confirmar" }));
    await waitFor(() => expect(api.posts()).toHaveLength(1));
    expect(api.posts()[0].path.endsWith("/cancel")).toBe(true);
    expect(api.posts()[0].options?.body).toBeUndefined();
  });

  it("shows a conflict (task already decided) without retrying, and refreshes the list", async () => {
    const user = userEvent.setup();
    const api = serve({
      "/admin/darius/tasks/": apiError("Task is not awaiting approval", 409, {
        message: "Task is not awaiting approval", status: "RUNNING", outcome_unknown: false,
      }),
      ...paused(),
    });
    renderWithQueryClient(<DariusPanel initialTab="approvals" />);
    await user.click(await screen.findByRole("button", { name: `Aprovar ${TASK.id}` }));
    await user.click(screen.getByRole("button", { name: "Confirmar" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Task is not awaiting approval");
    expect(alert).toHaveTextContent("já mudou de estado");
    expect(api.posts()).toHaveLength(1);
    await waitFor(() => expect(api.paths().filter((p) => p === "/admin/darius/tasks?status=PAUSED&limit=10&offset=0").length).toBeGreaterThan(1));
  });

  it("warns when the outcome is unknown instead of inviting a blind retry", async () => {
    const user = userEvent.setup();
    serve({
      "/admin/darius/tasks/": apiError("timeout", 502, { message: "timeout", code: "DARIUS_UNAVAILABLE", outcome_unknown: true }),
      ...paused(),
    });
    renderWithQueryClient(<DariusPanel initialTab="approvals" />);
    await user.click(await screen.findByRole("button", { name: `Aprovar ${TASK.id}` }));
    await user.click(screen.getByRole("button", { name: "Confirmar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("resultado é desconhecido");
  });

  it("has an empty state", async () => {
    serve({ "/admin/darius/tasks": page([]) });
    renderWithQueryClient(<DariusPanel initialTab="approvals" />);
    expect(await screen.findByText("Nada aguardando aprovação")).toBeInTheDocument();
  });
});

describe("WhatsApp", () => {
  it("shows per-instance routing/suspension and the audit links without any message text", async () => {
    serve({
      "/admin/darius/whatsapp-routing": { ...ROUTING, unknown_routed_instances: ["ghost"] },
      "/admin/darius/whatsapp-tasks": LINKS,
    });
    renderWithQueryClient(<DariusPanel initialTab="whatsapp" />);
    expect(await screen.findByText("Exceeded maximum iterations")).toBeInTheDocument();
    const rows = screen.getAllByRole("row");
    const store = rows.find((row) => within(row).queryByText("DARIUS"))!;
    expect(within(store).getByText("ativa")).toBeInTheDocument();
    const personal = rows.find((row) => within(row).queryByText("fluxo local"))!;
    expect(within(personal).getByText(/suspensa: manutenção do número/)).toBeInTheDocument();
    expect(screen.getByText(/ghost/)).toBeInTheDocument();
    expect(screen.getByText("expired: 2")).toBeInTheDocument();
    expect(screen.getByText(/O texto das mensagens e das respostas não é armazenado/)).toBeInTheDocument();
  });

  it("passes the status and instance filters to the endpoint", async () => {
    const user = userEvent.setup();
    const api = serve({ "/admin/darius/whatsapp-routing": ROUTING, "/admin/darius/whatsapp-tasks": LINKS });
    renderWithQueryClient(<DariusPanel initialTab="whatsapp" />);
    await screen.findByText("Exceeded maximum iterations");
    await user.selectOptions(screen.getAllByLabelText("Estado")[0], "failed");
    await user.selectOptions(await screen.findByLabelText("Instância"), "store");
    await waitFor(() =>
      expect(api.paths().some((p) => p.includes("status=failed") && p.includes("instance=store") && p.includes("offset=0"))).toBe(true)
    );
  });

  it("flags a global suspension and a disabled flag", async () => {
    serve({
      "/admin/darius/whatsapp-routing": {
        ...ROUTING, enabled: false, global_suspended: true, global_suspension_reason: "incidente",
      },
      "/admin/darius/whatsapp-tasks": { items: [], counts: {}, next_offset: null },
    });
    renderWithQueryClient(<DariusPanel initialTab="whatsapp" />);
    expect(await screen.findByText(/Automação suspensa globalmente: incidente/)).toBeInTheDocument();
    expect(screen.getByText(/desligado/)).toBeInTheDocument();
    expect(await screen.findByText("Nenhuma mensagem roteada")).toBeInTheDocument();
  });

  it("explains routing on but DARIUS not configured", async () => {
    serve({
      "/admin/darius/whatsapp-routing": { ...ROUTING, darius_configured: false },
      "/admin/darius/whatsapp-tasks": LINKS,
    });
    renderWithQueryClient(<DariusPanel initialTab="whatsapp" />);
    expect(await screen.findByText(/DARIUS não está configurado/)).toBeInTheDocument();
  });
});

describe("Suspension", () => {
  it("requires a reason and an explicit confirmation before suspending globally", async () => {
    const user = userEvent.setup();
    const api = serve({
      "/admin/automation/suspension/global": { ...SUSPENSION, global_suspended: true, changed: true },
      "/admin/automation/suspension": SUSPENSION,
    });
    renderWithQueryClient(<DariusPanel initialTab="suspension" />);
    await user.click(await screen.findByRole("button", { name: /Suspender Global/ }));
    const confirm = screen.getByRole("button", { name: "Confirmar" });
    expect(confirm).toBeDisabled();
    expect(api.posts()).toHaveLength(0);

    await user.type(screen.getByLabelText("Motivo"), "ab");
    expect(confirm).toBeDisabled();
    await user.type(screen.getByLabelText("Motivo"), "c  ");
    expect(confirm).toBeEnabled();
    await user.click(confirm);

    await waitFor(() => expect(api.posts()).toHaveLength(1));
    expect(api.posts()[0].path).toBe("/admin/automation/suspension/global");
    expect(api.posts()[0].options?.method).toBe("PUT");
    expect(JSON.parse(String(api.posts()[0].options?.body))).toEqual({ suspended: true, reason: "abc" });
    expect(await screen.findByText("Automação (global) suspensa.")).toBeInTheDocument();
  });

  it("resumes a single instance through its own endpoint and reports a no-op honestly", async () => {
    const user = userEvent.setup();
    const api = serve({
      "/admin/automation/suspension/instances/": { ...SUSPENSION, suspended_instances: [], changed: false },
      "/admin/automation/suspension": SUSPENSION,
    });
    renderWithQueryClient(<DariusPanel initialTab="suspension" />);
    expect(await screen.findByText(/manutenção do número/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Retomar Instância personal/ }));
    await user.type(screen.getByLabelText("Motivo"), "voltou ao ar");
    await user.click(screen.getByRole("button", { name: "Confirmar" }));
    await waitFor(() => expect(api.posts()).toHaveLength(1));
    expect(api.posts()[0].path).toBe("/admin/automation/suspension/instances/personal");
    expect(JSON.parse(String(api.posts()[0].options?.body))).toEqual({ suspended: false, reason: "voltou ao ar" });
    expect(await screen.findByText(/Sem mudança: a automação \(instância personal\) já estava ativa/)).toBeInTheDocument();
  });

  it("shows server-side refusals (unknown instance) and keeps the form open", async () => {
    const user = userEvent.setup();
    serve({
      "/admin/automation/suspension/instances/": apiError("Instância desconhecida", 404),
      "/admin/automation/suspension": SUSPENSION,
    });
    renderWithQueryClient(<DariusPanel initialTab="suspension" />);
    await user.click(await screen.findByRole("button", { name: /Suspender Instância store/ }));
    await user.type(screen.getByLabelText("Motivo"), "teste");
    await user.click(screen.getByRole("button", { name: "Confirmar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Instância desconhecida");
    expect(screen.getByRole("group", { name: "Confirmar suspensão" })).toBeInTheDocument();
  });

  it("tells the operator when the environment switch holds the suspension", async () => {
    serve({
      "/admin/automation/suspension": { ...SUSPENSION, global_suspended: true, global_forced_by_environment: true },
    });
    renderWithQueryClient(<DariusPanel initialTab="suspension" />);
    expect(await screen.findByText(/variável de ambiente do backend \(AUTOMATION_SUSPENDED\)/)).toBeInTheDocument();
  });

  it("is explicit when the state cannot be read", async () => {
    serve({ "/admin/automation/suspension": apiError("Acesso negado", 403) });
    renderWithQueryClient(<DariusPanel initialTab="suspension" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Acesso negado");
    expect(screen.queryByRole("button", { name: /Suspender/ })).not.toBeInTheDocument();
  });
});

describe("Logs", () => {
  it("merges DARIUS and suspension audit entries, newest first", async () => {
    serve({
      "/admin/logs": (path: string) =>
        path.includes("source_prefix=darius")
          ? [
              { id: 1, level: "info", source: "darius_decision", message: "approve t-1: ok", payload: {}, created_at: "2026-10-19T10:00:00Z" },
              { id: 2, level: "warning", source: "darius_whatsapp", message: "Fluxo DARIUS encerrado: failed", payload: {}, created_at: "2026-10-19T12:00:00Z" },
            ]
          : [{ id: 9, level: "info", source: "automation_suspension", message: "global suspensa", payload: {}, created_at: "2026-10-19T11:00:00Z" }],
    });
    renderWithQueryClient(<DariusPanel initialTab="logs" />);
    await screen.findByText("global suspensa");
    const messages = screen.getAllByRole("row").slice(1).map((row) => row.textContent ?? "");
    expect(messages[0]).toContain("Fluxo DARIUS encerrado");
    expect(messages[1]).toContain("global suspensa");
    expect(messages[2]).toContain("approve t-1: ok");
  });

  it("has an empty state and an error state", async () => {
    serve({ "/admin/logs": [] });
    const { unmount } = renderWithQueryClient(<DariusPanel initialTab="logs" />);
    expect(await screen.findByText("Sem registros")).toBeInTheDocument();
    unmount();
    serve({ "/admin/logs": apiError("Falha de banco", 500) });
    renderWithQueryClient(<DariusPanel initialTab="logs" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Falha de banco");
  });
});
