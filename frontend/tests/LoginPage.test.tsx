import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import LoginPage from "@/app/login/page";

describe("LoginPage", () => {
  it("links to the forgot-password page", () => {
    render(<LoginPage />);
    const link = screen.getByRole("link", { name: "Esqueci minha senha" });
    expect(link).toHaveAttribute("href", "/esqueci-senha");
  });
});
