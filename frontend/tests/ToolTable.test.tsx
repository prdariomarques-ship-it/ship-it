import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { ToolTable } from "@/components/admin/ToolTable";
import type { ToolAdminInfo } from "@/lib/admin-types";

const tools: ToolAdminInfo[] = [
  {
    name: "send_whatsapp_message",
    description: "Envia uma mensagem de WhatsApp",
    category: "communication",
    agents: ["assistant"],
    parameters: { type: "object", properties: { to: { type: "string" } }, required: ["to"] },
    permissions: null,
    calls_total: 5,
    calls_ok: 4,
    calls_error: 1,
    last_call: null,
  },
];

describe("ToolTable", () => {
  it("shows an empty state when there are no tools", () => {
    render(<ToolTable tools={[]} />);
    expect(screen.getByText("Nenhuma tool registrada")).toBeInTheDocument();
  });

  it("lists every tool with its category and agents", () => {
    render(<ToolTable tools={tools} />);
    expect(screen.getByText("send_whatsapp_message")).toBeInTheDocument();
    expect(screen.getByText("communication")).toBeInTheDocument();
    expect(screen.getByText("assistant")).toBeInTheDocument();
  });

  it("shows 'não disponível' for permissions and last call, never a fabricated value", () => {
    render(<ToolTable tools={tools} />);
    expect(screen.getAllByText("não disponível").length).toBe(2); // permissions + última chamada
  });

  it("opens a detail dialog with the JSON schema when a row is clicked", async () => {
    render(<ToolTable tools={tools} />);
    await userEvent.click(screen.getByText("send_whatsapp_message"));
    expect(await screen.findByText("Schema JSON (input)")).toBeInTheDocument();
    expect(screen.getByText(/"to"/)).toBeInTheDocument();
    // Honest about the missing execution-audit data, not silently empty.
    expect(screen.getByText(/Não há exemplos de input\/output reais armazenados/)).toBeInTheDocument();
  });

  it("opens the detail dialog via keyboard (Enter) for accessibility", async () => {
    render(<ToolTable tools={tools} />);
    const row = screen.getByText("send_whatsapp_message").closest("tr")!;
    fireEvent.keyDown(row, { key: "Enter" });
    expect(await screen.findByText("Schema JSON (input)")).toBeInTheDocument();
  });

  it("closes the dialog when its close button is clicked", async () => {
    render(<ToolTable tools={tools} />);
    await userEvent.click(screen.getByText("send_whatsapp_message"));
    await screen.findByText("Schema JSON (input)");
    await userEvent.click(screen.getByRole("button", { name: /fechar/i }));
    expect(screen.queryByText("Schema JSON (input)")).not.toBeInTheDocument();
  });

  it("shows an em-dash when a tool has no agents using it", () => {
    render(<ToolTable tools={[{ ...tools[0], agents: [] }]} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});
