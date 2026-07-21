import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import EsqueciSenhaPage from "@/app/esqueci-senha/page";

function stubFetch(response: { ok: boolean; status?: number; json: () => Promise<unknown> }) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
}

describe("EsqueciSenhaPage", () => {
  it("submits the email and shows the confirmation message", async () => {
    stubFetch({ ok: true, status: 204, json: async () => ({}) });
    render(<EsqueciSenhaPage />);

    await userEvent.type(screen.getByPlaceholderText("E-mail"), "dario@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Solicitar redefinição" }));

    expect(
      await screen.findByText(/sua solicitação foi registrada/)
    ).toBeInTheDocument();

    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain("/auth/forgot-password");
    expect(options.method).toBe("POST");
    expect(JSON.parse(options.body)).toEqual({ email: "dario@example.com" });
  });

  it("shows an error message when the request fails", async () => {
    stubFetch({ ok: false, status: 500, json: async () => ({ detail: "Erro interno" }) });
    render(<EsqueciSenhaPage />);

    await userEvent.type(screen.getByPlaceholderText("E-mail"), "dario@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Solicitar redefinição" }));

    expect(await screen.findByText("Erro interno")).toBeInTheDocument();
  });
});
