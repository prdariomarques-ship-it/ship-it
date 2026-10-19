import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/hooks/useApi", () => ({ apiFetch: vi.fn() }));

import { DariusPanel } from "@/components/darius/DariusPanel";
import { TelegramTab } from "@/components/darius/TelegramTab";
import { renderWithQueryClient } from "./test-utils";
import { apiError, serve } from "./darius-test-utils";

const INVENTORY = {
  as_of: "2026-10-19",
  live_state_available: false,
  live_state_note: "Inventário auditado e estático. O Dario OS não guarda credenciais do Telegram.",
  counts_by_runtime_status: { ativo_evidenciado: 1, nao_verificado: 1, inconclusivo: 1 },
  bots: [
    {
      id: "market-command-poller",
      name: "Bot de comandos de mercado",
      scope: "ship-it",
      repository: "https://github.com/x/ship-it",
      source_files: ["work/market_command_bot.py"],
      kind: "command_poller",
      purpose: "Responde comandos no chat autorizado.",
      commands: ["/help", "/cambio"],
      data_sources: ["AwesomeAPI Economia (somente /cambio)"],
      credentials: ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"],
      triggers: [{ kind: "schedule", expression: "3/5 * * * *", host: "GitHub Actions" }],
      runtime: {
        status: "ativo_evidenciado",
        detail: "Execuções agendadas concluídas com sucesso.",
        evidence: "https://github.com/x/ship-it/actions (página pública)",
        as_of: "2026-10-19",
      },
      risks: ["Um único consumidor de getUpdates por token."],
    },
    {
      id: "dmarques-gateway",
      name: "@Dmarques_bot (gateway para o Hermes)",
      scope: "externo",
      repository: "https://github.com/x/agente-dmn",
      source_files: ["README.md (repositório externo)"],
      kind: "gateway",
      purpose: "Gateway por long polling.",
      commands: ["/start", "/help"],
      data_sources: [],
      credentials: ["TELEGRAM_TOKEN"],
      triggers: [{ kind: "continuous", expression: null, host: "processo Node.js" }],
      runtime: { status: "nao_verificado", detail: "Só o README foi lido.", evidence: null, as_of: "2026-10-19" },
      risks: [],
    },
    {
      id: "monitor-spcx",
      name: "Monitor SCPX",
      scope: "externo",
      repository: null,
      source_files: [],
      kind: "unknown",
      purpose: "Citado, mas nenhum código foi localizado.",
      commands: [],
      data_sources: [],
      credentials: [],
      triggers: [],
      runtime: { status: "inconclusivo", detail: "Sem código nos repositórios inspecionados.", evidence: null, as_of: "2026-10-19" },
      risks: ["Não tratar como existente."],
    },
  ],
};

describe("Telegram tab", () => {
  it("states that the inventory is static and that live state is unavailable", async () => {
    serve({ "/admin/telegram/bots": INVENTORY });
    renderWithQueryClient(<TelegramTab />);
    expect(await screen.findByText(/não é estado em tempo real/)).toBeInTheDocument();
    expect(screen.getByText("Estado em tempo real: indisponível.")).toBeInTheDocument();
  });

  it("shows each bot with its real status, commands, triggers and credential NAMES", async () => {
    serve({ "/admin/telegram/bots": INVENTORY });
    renderWithQueryClient(<TelegramTab />);
    const poller = await screen.findByRole("group", { name: "Bot de comandos de mercado" });
    expect(within(poller).getByText("ativo (evidenciado)")).toBeInTheDocument();
    expect(within(poller).getByText("/help /cambio")).toBeInTheDocument();
    expect(within(poller).getByText(/3\/5 \* \* \* \*/)).toBeInTheDocument();
    expect(within(poller).getByText("TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID")).toBeInTheDocument();
    expect(within(poller).getByText(/Evidência \(2026-10-19\)/)).toBeInTheDocument();
    expect(within(poller).getByText("neste repositório")).toBeInTheDocument();

    const external = screen.getByRole("group", { name: /Dmarques_bot/ });
    expect(within(external).getByText("não verificado")).toBeInTheDocument();
    expect(within(external).getByText("repositório externo")).toBeInTheDocument();
    expect(within(external).queryByText(/Evidência/)).not.toBeInTheDocument();   // no evidence, none invented
  });

  it("keeps the SCPX monitor INCONCLUSIVO, without commands or triggers", async () => {
    serve({ "/admin/telegram/bots": INVENTORY });
    renderWithQueryClient(<TelegramTab />);
    const spcx = await screen.findByRole("group", { name: "Monitor SCPX" });
    expect(within(spcx).getByText("INCONCLUSIVO")).toBeInTheDocument();
    expect(within(spcx).queryByText("Comandos")).not.toBeInTheDocument();
    expect(within(spcx).queryByText("Disparo")).not.toBeInTheDocument();
  });

  it("renders the per-status summary from the API figures only", async () => {
    serve({ "/admin/telegram/bots": INVENTORY });
    renderWithQueryClient(<TelegramTab />);
    const summary = await screen.findByLabelText("Resumo por situação");
    expect(within(summary).getByText("ativo (evidenciado): 1")).toBeInTheDocument();
    expect(within(summary).getByText("INCONCLUSIVO: 1")).toBeInTheDocument();
    expect(within(summary).queryByText(/sem agendamento/)).not.toBeInTheDocument();   // absent status is not shown as 0
  });

  it("is read-only: it issues a single GET and offers no action button", async () => {
    const api = serve({ "/admin/telegram/bots": INVENTORY });
    renderWithQueryClient(<TelegramTab />);
    await screen.findByRole("group", { name: "Monitor SCPX" });
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(api.paths()).toEqual(["/admin/telegram/bots"]);
    expect(api.posts()).toEqual([]);
  });

  it("shows the backend error instead of an empty list", async () => {
    serve({ "/admin/telegram/bots": apiError("Forbidden", 403) });
    renderWithQueryClient(<TelegramTab />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Forbidden");
  });

  it("explains an empty inventory", async () => {
    serve({ "/admin/telegram/bots": { ...INVENTORY, bots: [], counts_by_runtime_status: {} } });
    renderWithQueryClient(<TelegramTab />);
    expect(await screen.findByText("Nenhum bot inventariado")).toBeInTheDocument();
  });

  it("is reachable as a tab of the DARIUS panel", async () => {
    serve({ "/admin/telegram/bots": INVENTORY, "/admin/darius/status": apiError("x", 500) });
    renderWithQueryClient(<DariusPanel initialTab="whatsapp" />);
    await userEvent.click(screen.getByRole("tab", { name: "Telegram" }));
    expect(await screen.findByRole("group", { name: "Monitor SCPX" })).toBeInTheDocument();
  });
});
