import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { GoogleCard } from "@/components/admin/GoogleCard";
import type { GoogleDomainStatus } from "@/lib/admin-types";

const disconnected: GoogleDomainStatus = {
  domain: "mail",
  connected_accounts: 0,
  accounts: [],
  indexed_items: null,
  last_indexed_at: null,
};

describe("GoogleCard", () => {
  it("maps the domain key to its human label", () => {
    render(<GoogleCard domain={disconnected} />);
    expect(screen.getByText("Gmail")).toBeInTheDocument();
  });

  it("shows 'não disponível' for last sync when the domain doesn't track it (mail/calendar/contacts)", () => {
    render(<GoogleCard domain={disconnected} />);
    expect(screen.getByText("não disponível")).toBeInTheDocument();
  });

  it("shows indexed item counts for Drive, which does track them", () => {
    const drive: GoogleDomainStatus = {
      domain: "drive",
      connected_accounts: 1,
      accounts: [{ user_id: 1, label: "dario@gmail.com", scopes: ["drive.readonly"], connected_at: new Date().toISOString() }],
      indexed_items: 42,
      last_indexed_at: new Date().toISOString(),
    };
    render(<GoogleCard domain={drive} />);
    expect(screen.getByText("Google Drive")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("dario@gmail.com")).toBeInTheDocument();
  });

  it("never renders a token/secret field even if present on the object", () => {
    const withExtra = { ...disconnected, encrypted_refresh_token: "should-never-appear" } as unknown as GoogleDomainStatus;
    render(<GoogleCard domain={withExtra} />);
    expect(screen.queryByText(/should-never-appear/)).not.toBeInTheDocument();
  });
});
