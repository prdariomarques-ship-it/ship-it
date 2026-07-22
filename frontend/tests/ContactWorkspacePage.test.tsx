import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "1" }),
}));

import ContactWorkspacePage from "@/app/(dashboard)/contatos/[id]/page";

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
