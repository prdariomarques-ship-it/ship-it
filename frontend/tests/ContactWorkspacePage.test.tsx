import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// A mutable mock (not a fixed literal) so the FIX 4 navigation test can
// simulate moving from one contact to another within a single test.
const mockUseParams = vi.fn(() => ({ id: "1" }));
vi.mock("next/navigation", () => ({
  useParams: () => mockUseParams(),
}));

import ContactWorkspacePage from "@/app/(dashboard)/contatos/[id]/page";

beforeEach(() => {
  mockUseParams.mockReturnValue({ id: "1" });
});

const WORKSPACE = {
  summary: {
    id: 1,
    name: "Ana Souza",
    phone: "+5511999990000",
    categories: ["loja"],
    tags: ["vip"],
    last_interaction_at: "2026-01-15T10:00:00Z",
    relationship_status: {
      tier: "at_risk",
      score: 40,
      signals: [
        {
          code: "relationship_at_risk",
          kind: "risk",
          severity: "urgent",
          reason: "No interaction in 90 day(s) (>= 45-day at-risk threshold).",
        },
      ],
    },
    suggested_next_action: "Reach out -- there has been no interaction in a long time.",
    ai_summary: "Cliente recorrente, prefere contato à tarde.",
    memory: {},
  },
  timeline: [
    {
      id: "note-1",
      type: "note",
      timestamp: "2026-01-10T00:00:00Z",
      title: "Prefere WhatsApp",
      subtitle: null,
      status: null,
      source: "notes",
      metadata: {},
    },
    {
      id: "meeting-1",
      type: "meeting",
      timestamp: "2026-02-01T10:00:00Z",
      title: "Reunião",
      subtitle: null,
      status: null,
      source: "calendar",
      metadata: {},
    },
  ],
  current_state: {
    open_tasks: [
      {
        id: 1,
        title: "Enviar orçamento",
        status: "pending",
        priority: "medium",
        due_date: null,
        created_at: "2026-01-10T00:00:00Z",
      },
    ],
    upcoming_events: [
      { id: 1, title: "Reunião", starts_at: "2026-02-01T10:00:00Z", location: null },
    ],
    pending_follow_ups: [],
    important_notes: [
      { id: 1, title: "Prefere WhatsApp", content: "x", pinned: true, created_at: "2026-01-10T00:00:00Z" },
    ],
  },
  recommendations: [],
};

describe("ContactWorkspacePage", () => {
  it("renders every relationship box from the workspace endpoint", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => WORKSPACE })
    );
    render(<ContactWorkspacePage />);

    expect(await screen.findByText("Ana Souza")).toBeInTheDocument();
    expect(screen.getByText(/Cliente recorrente/)).toBeInTheDocument();
    // "Prefere WhatsApp" appears twice on purpose: once as the Notes box's
    // own entry, once as the Timeline's rendering of that same note.
    expect(screen.getAllByText(/Prefere WhatsApp/).length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/Enviar orçamento/)).toBeInTheDocument();
    // "Reunião" appears in both the upcoming-events box and the timeline's meeting entry.
    expect(screen.getAllByText(/Reunião/).length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("Nenhuma recomendação disponível ainda.")).toBeInTheDocument();
  });

  it("shows honest empty states when a box has no data yet", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          ...WORKSPACE,
          timeline: [],
          current_state: {
            open_tasks: [],
            upcoming_events: [],
            pending_follow_ups: [],
            important_notes: [],
          },
          summary: { ...WORKSPACE.summary, ai_summary: null },
        }),
      })
    );
    render(<ContactWorkspacePage />);

    await screen.findByText("Ana Souza");
    expect(screen.getByText("Ainda sem resumo gerado.")).toBeInTheDocument();
    expect(screen.getByText("Nada registrado ainda.")).toBeInTheDocument();
    expect(screen.getByText("Nenhuma tarefa vinculada a este contato.")).toBeInTheDocument();
    expect(
      screen.getByText("Nenhum evento futuro vinculado a este contato.")
    ).toBeInTheDocument();
    expect(screen.getByText("Nenhuma resposta enviada recentemente.")).toBeInTheDocument();
    expect(screen.getByText("Nenhuma nota vinculada a este contato.")).toBeInTheDocument();
  });

  it("renders the P0-3 relationship tier, its signal reasons, and the suggested action", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => WORKSPACE })
    );
    render(<ContactWorkspacePage />);

    await screen.findByText("Ana Souza");
    expect(screen.getByText(/Status do relacionamento:/)).toBeInTheDocument();
    expect(screen.getByText(/Em risco/)).toBeInTheDocument();
    expect(
      screen.getByText(/No interaction in 90 day\(s\)/)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Próxima ação sugerida: Reach out/)
    ).toBeInTheDocument();
  });

  it("renders a P0-4 recommendation and executes it via the confirmation button", async () => {
    const RECOMMENDATION = {
      id: "1-follow_up",
      type: "follow_up" as const,
      priority: "urgent" as const,
      confidence: 95,
      explanation: "Reach out -- no reply sent since the last inbound message.",
      reasoning: ["Reach out -- no reply sent since the last inbound message."],
      supporting_signals: ["relationship_at_risk"],
      confirmation_required: true,
      execution_target: "create_task",
      execution_payload: { title: "Reach out to Ana Souza -- relationship at risk" },
      created_at: "2026-01-15T10:00:00Z",
      expires_at: "2026-01-16T10:00:00Z",
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ ...WORKSPACE, recommendations: [RECOMMENDATION] }),
      })
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ ok: true, result: {} }) })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ ...WORKSPACE, recommendations: [] }),
      });
    vi.stubGlobal("fetch", fetchMock);
    render(<ContactWorkspacePage />);

    expect(await screen.findByText(RECOMMENDATION.explanation)).toBeInTheDocument();
    expect(screen.getByText(/confiança 95%/)).toBeInTheDocument();
    const executeButton = screen.getByRole("button", { name: "Executar" });

    fireEvent.click(executeButton);

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/contacts/1/recommendations/1-follow_up/execute"),
        expect.objectContaining({ method: "POST" })
      )
    );
    await waitFor(() =>
      expect(screen.getByText("Nenhuma recomendação disponível ainda.")).toBeInTheDocument()
    );
  });

  it("guards against a double-click executing the same recommendation twice (FIX 1)", async () => {
    const RECOMMENDATION = {
      id: "1-follow_up",
      type: "follow_up" as const,
      priority: "urgent" as const,
      confidence: 95,
      explanation: "Reach out -- no reply sent since the last inbound message.",
      reasoning: ["Reach out -- no reply sent since the last inbound message."],
      supporting_signals: ["relationship_at_risk"],
      confirmation_required: true,
      execution_target: "create_task",
      execution_payload: { title: "Reach out to Ana Souza -- relationship at risk" },
      created_at: "2026-01-15T10:00:00Z",
      expires_at: "2026-01-16T10:00:00Z",
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ ...WORKSPACE, recommendations: [RECOMMENDATION] }),
      })
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ ok: true, result: {} }) })
      .mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ ...WORKSPACE, recommendations: [] }),
      });
    vi.stubGlobal("fetch", fetchMock);
    render(<ContactWorkspacePage />);

    const executeButton = await screen.findByRole("button", { name: "Executar" });
    // Three rapid clicks, synchronously -- the guard (a ref, not state) must
    // block the 2nd and 3rd before React ever commits the disabled attribute.
    fireEvent.click(executeButton);
    fireEvent.click(executeButton);
    fireEvent.click(executeButton);

    await waitFor(() => {
      const executeCalls = fetchMock.mock.calls.filter(
        ([url]) => typeof url === "string" && url.includes("/execute")
      );
      expect(executeCalls).toHaveLength(1);
    });
  });

  it("tracks execution state independently per recommendation, no cross-recommendation interference (FIX 2)", async () => {
    const RECOMMENDATION_A = {
      id: "1-follow_up",
      type: "follow_up" as const,
      priority: "urgent" as const,
      confidence: 95,
      explanation: "Reach out -- no reply sent since the last inbound message.",
      reasoning: ["Reach out -- no reply sent since the last inbound message."],
      supporting_signals: ["relationship_at_risk"],
      confirmation_required: true,
      execution_target: "create_task",
      execution_payload: { title: "A" },
      created_at: "2026-01-15T10:00:00Z",
      expires_at: "2026-01-16T10:00:00Z",
    };
    // A second confirmable recommendation is not producible by today's v1
    // engine (at most one follow_up per contact) -- constructed here only
    // to exercise the UI's independence guarantee, which must hold the
    // moment a second confirmable type ships (see ADR-0001).
    const RECOMMENDATION_B = {
      ...RECOMMENDATION_A,
      id: "1-second",
      execution_payload: { title: "B" },
    };

    const releasers: Record<string, () => void> = {};
    const fetchMock = vi.fn(async (url: string) => {
      if (url.includes("/workspace")) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            ...WORKSPACE,
            recommendations: [RECOMMENDATION_A, RECOMMENDATION_B],
          }),
        };
      }
      if (url.includes("/execute")) {
        const id = url.match(/recommendations\/([^/]+)\/execute/)?.[1] ?? "";
        return new Promise((resolve) => {
          releasers[id] = () =>
            resolve({ ok: true, status: 200, json: async () => ({ ok: true, result: {} }) });
        });
      }
      throw new Error(`Unexpected fetch call: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<ContactWorkspacePage />);

    const buttons = await screen.findAllByRole("button", { name: "Executar" });
    expect(buttons).toHaveLength(2);

    fireEvent.click(buttons[0]);
    await waitFor(() =>
      expect(screen.getAllByRole("button", { name: "Executando…" })).toHaveLength(1)
    );
    // The second recommendation's button must remain independently clickable.
    const stillIdle = screen.getAllByRole("button", { name: "Executar" });
    expect(stillIdle).toHaveLength(1);

    fireEvent.click(stillIdle[0]);
    await waitFor(() =>
      expect(screen.getAllByRole("button", { name: "Executando…" })).toHaveLength(2)
    );

    releasers["1-follow_up"]();
    await waitFor(() =>
      expect(screen.getAllByRole("button", { name: "Executando…" })).toHaveLength(1)
    );

    releasers["1-second"]();
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Executando…" })).not.toBeInTheDocument()
    );
  });

  it("resets execution state and error when navigating to a different contact (FIX 4)", async () => {
    mockUseParams.mockReturnValue({ id: "1" });
    const RECOMMENDATION_1 = {
      id: "1-follow_up",
      type: "follow_up" as const,
      priority: "urgent" as const,
      confidence: 95,
      explanation: "Reach out -- no reply sent since the last inbound message.",
      reasoning: ["Reach out -- no reply sent since the last inbound message."],
      supporting_signals: ["relationship_at_risk"],
      confirmation_required: true,
      execution_target: "create_task",
      execution_payload: { title: "Reach out to Ana Souza" },
      created_at: "2026-01-15T10:00:00Z",
      expires_at: "2026-01-16T10:00:00Z",
    };
    const fetchMock = vi.fn(async (url: string) => {
      if (url.includes("/contacts/1/workspace")) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ ...WORKSPACE, recommendations: [RECOMMENDATION_1] }),
        };
      }
      if (url.includes("/contacts/2/workspace")) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            ...WORKSPACE,
            summary: { ...WORKSPACE.summary, name: "Bruno Lima" },
            recommendations: [],
          }),
        };
      }
      if (url.includes("/execute")) {
        // Deliberately never resolves -- the test navigates away while this
        // is still in flight, which is exactly the scenario the fix guards.
        return new Promise(() => {});
      }
      throw new Error(`Unexpected fetch call: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const { rerender } = render(<ContactWorkspacePage />);
    await screen.findByText("Ana Souza");

    const executeButton = screen.getByRole("button", { name: "Executar" });
    fireEvent.click(executeButton);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Executando…" })).toBeInTheDocument()
    );

    // Simulate client-side navigation to a different contact, whether or
    // not Next.js actually remounts the component -- the fix must not rely
    // on that being true either way.
    mockUseParams.mockReturnValue({ id: "2" });
    rerender(<ContactWorkspacePage />);

    await screen.findByText("Bruno Lima");
    expect(screen.queryByRole("button", { name: "Executando…" })).not.toBeInTheDocument();
    expect(screen.queryByText(/Falha ao executar/)).not.toBeInTheDocument();
    expect(screen.getByText("Nenhuma recomendação disponível ainda.")).toBeInTheDocument();
  });

  it("does not show an execute button for a recommendation with no executable action", async () => {
    const RECOMMENDATION = {
      id: "1-check_pending_tasks",
      type: "check_pending_tasks" as const,
      priority: "attention" as const,
      confidence: 65,
      explanation: "1 overdue commitment.",
      reasoning: ["1 overdue commitment."],
      supporting_signals: ["overdue_commitment"],
      confirmation_required: false,
      execution_target: null,
      execution_payload: null,
      created_at: "2026-01-15T10:00:00Z",
      expires_at: null,
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ ...WORKSPACE, recommendations: [RECOMMENDATION] }),
      })
    );
    render(<ContactWorkspacePage />);

    expect(await screen.findByText(RECOMMENDATION.explanation)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Executar" })).not.toBeInTheDocument();
  });

  it("renders a healthy tier with no signal list when nothing fired", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          ...WORKSPACE,
          summary: {
            ...WORKSPACE.summary,
            relationship_status: { tier: "healthy", score: 0, signals: [] },
            suggested_next_action:
              "No action needed right now -- this relationship looks healthy.",
          },
        }),
      })
    );
    render(<ContactWorkspacePage />);

    await screen.findByText("Ana Souza");
    expect(screen.getByText(/Saudável/)).toBeInTheDocument();
    expect(
      screen.getByText(/Próxima ação sugerida: No action needed/)
    ).toBeInTheDocument();
  });
});
