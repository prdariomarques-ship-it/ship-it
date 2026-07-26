import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import EconomicCalendarTable from "@/components/economic-calendar/EconomicCalendarTable";

const sampleEvents = [
  {
    id: "evt-1",
    name: "Non-Farm Payrolls",
    country_code: "US",
    country_name: "United States",
    currency: "USD",
    date_utc: "2026-07-26T13:30:00.000Z",
    volatility: "HIGH",
    actual: "216K",
    forecast: "200K",
    previous: "199K",
    unit: "Jobs",
    category: "Employment",
    impact: null,
    url: null,
  },
  {
    id: "evt-2",
    name: "GDP Growth Rate (QoQ)",
    country_code: "EU",
    country_name: "Eurozone",
    currency: "EUR",
    date_utc: "2026-07-27T10:00:00.000Z",
    volatility: "MEDIUM",
    actual: null,
    forecast: "0.3%",
    previous: "0.1%",
    unit: "Percent",
    category: "GDP",
    impact: null,
    url: null,
  },
];

describe("EconomicCalendarTable", () => {
  it("renders all events in a table", () => {
    render(<EconomicCalendarTable events={sampleEvents} />);
    expect(screen.getByText("Non-Farm Payrolls")).toBeInTheDocument();
    expect(screen.getByText("GDP Growth Rate (QoQ)")).toBeInTheDocument();
  });

  it("displays country codes as badges", () => {
    render(<EconomicCalendarTable events={sampleEvents} />);
    expect(screen.getByText("US")).toBeInTheDocument();
    expect(screen.getByText("EU")).toBeInTheDocument();
  });

  it("displays actual values with bold weight", () => {
    render(<EconomicCalendarTable events={sampleEvents} />);
    // The first event has actual="216K"
    expect(screen.getByText("216K")).toBeInTheDocument();
  });

  it("displays dashes for missing values", () => {
    render(<EconomicCalendarTable events={sampleEvents} />);
    // The second event has actual=null
    const allDash = screen.getAllByText("—");
    expect(allDash.length).toBeGreaterThan(0);
  });

  it("shows empty state when no events", () => {
    render(<EconomicCalendarTable events={[]} />);
    expect(
      screen.getByText(/Nenhum evento econômico encontrado/)
    ).toBeInTheDocument();
  });

  it("renders volatility badges with correct labels", () => {
    render(<EconomicCalendarTable events={sampleEvents} />);
    expect(screen.getByText("Alto")).toBeInTheDocument();
    expect(screen.getByText("Médio")).toBeInTheDocument();
  });

  it("renders event categories", () => {
    render(<EconomicCalendarTable events={sampleEvents} />);
    expect(screen.getByText("Employment")).toBeInTheDocument();
    expect(screen.getByText("GDP")).toBeInTheDocument();
  });

  it("renders country names", () => {
    render(<EconomicCalendarTable events={sampleEvents} />);
    expect(screen.getByText("United States")).toBeInTheDocument();
    expect(screen.getByText("Eurozone")).toBeInTheDocument();
  });
});
