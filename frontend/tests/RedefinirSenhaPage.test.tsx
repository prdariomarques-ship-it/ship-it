import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

const mockSearchParams = vi.fn();
vi.mock("next/navigation", () => ({
  useSearchParams: () => mockSearchParams(),
}));

import RedefinirSenhaPage from "@/app/redefinir-senha/page";

function stubFetch(response: { ok: boolean; status?: number; json: () => Promise<unknown> }) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
}

describe("RedefinirSenhaPage", () => {
  it("prefills the token from the ?token= query param", () => {
    mockSearchParams.mockReturnValue(new URLSearchParams("token=abc123"));
    render(<RedefinirSenhaPage />);

    expect(screen.getByPlaceholderText("Token de redefinição")).toHaveValue("abc123");
  });

  it("submits token and new password, shows success on completion", async () => {
    mockSearchParams.mockReturnValue(new URLSearchParams());
    stubFetch({ ok: true, status: 204, json: async () => ({}) });
    render(<RedefinirSenhaPage />);

    await userEvent.type(screen.getByPlaceholderText("Token de redefinição"), "mytoken");
    await userEvent.type(screen.getByPlaceholderText("Nova senha"), "newpassword1");
    await userEvent.type(screen.getByPlaceholderText("Confirmar nova senha"), "newpassword1");
    await userEvent.click(screen.getByRole("button", { name: "Redefinir senha" }));

    expect(await screen.findByText(/Senha redefinida com sucesso/)).toBeInTheDocument();

    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain("/auth/reset-password");
    expect(JSON.parse(options.body)).toEqual({
      token: "mytoken",
      new_password: "newpassword1",
    });
  });

  it("rejects mismatched passwords without calling the API", async () => {
    mockSearchParams.mockReturnValue(new URLSearchParams());
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<RedefinirSenhaPage />);

    await userEvent.type(screen.getByPlaceholderText("Token de redefinição"), "mytoken");
    await userEvent.type(screen.getByPlaceholderText("Nova senha"), "newpassword1");
    await userEvent.type(screen.getByPlaceholderText("Confirmar nova senha"), "different1");
    await userEvent.click(screen.getByRole("button", { name: "Redefinir senha" }));

    expect(await screen.findByText("As senhas não coincidem")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows an error for an invalid or expired token", async () => {
    mockSearchParams.mockReturnValue(new URLSearchParams());
    stubFetch({ ok: false, status: 401, json: async () => ({ detail: "Invalid or expired reset token" }) });
    render(<RedefinirSenhaPage />);

    await userEvent.type(screen.getByPlaceholderText("Token de redefinição"), "badtoken");
    await userEvent.type(screen.getByPlaceholderText("Nova senha"), "newpassword1");
    await userEvent.type(screen.getByPlaceholderText("Confirmar nova senha"), "newpassword1");
    await userEvent.click(screen.getByRole("button", { name: "Redefinir senha" }));

    expect(await screen.findByText("Invalid or expired reset token")).toBeInTheDocument();
  });
});
