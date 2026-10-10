import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import EconomicCalendarFilters from "@/components/economic-calendar/EconomicCalendarFilters";

const mockCountries = [
  { code: "US", name: "United States" },
  { code: "BR", name: "Brazil" },
  { code: "EU", name: "Eurozone" },
];

describe("EconomicCalendarFilters", () => {
  const defaultProps = {
    countries: mockCountries,
    selectedCountry: "",
    selectedVolatility: "",
    onCountryChange: vi.fn(),
    onVolatilityChange: vi.fn(),
    onRefresh: vi.fn(),
    loading: false,
  };

  it("renders country select with all countries", () => {
    render(<EconomicCalendarFilters {...defaultProps} />);
    expect(screen.getByText("US — United States")).toBeInTheDocument();
    expect(screen.getByText("BR — Brazil")).toBeInTheDocument();
    expect(screen.getByText("EU — Eurozone")).toBeInTheDocument();
  });

  it("renders volatility select with all options", () => {
    render(<EconomicCalendarFilters {...defaultProps} />);
    expect(screen.getByText("Todos")).toBeInTheDocument();
    expect(screen.getByText("Alto impacto")).toBeInTheDocument();
    expect(screen.getByText("Médio impacto")).toBeInTheDocument();
    expect(screen.getByText("Baixo impacto")).toBeInTheDocument();
  });

  it("calls onCountryChange when country is selected", () => {
    render(<EconomicCalendarFilters {...defaultProps} />);
    // The label "País" is rendered as text, then the select follows
    const selects = screen.getAllByRole("combobox");
    const countrySelect = selects[0];
    fireEvent.change(countrySelect, { target: { value: "US" } });
    expect(defaultProps.onCountryChange).toHaveBeenCalledWith("US");
  });

  it("calls onVolatilityChange when volatility is selected", () => {
    render(<EconomicCalendarFilters {...defaultProps} />);
    const selects = screen.getAllByRole("combobox");
    const volatilitySelect = selects[1];
    fireEvent.change(volatilitySelect, { target: { value: "HIGH" } });
    expect(defaultProps.onVolatilityChange).toHaveBeenCalledWith("HIGH");
  });

  it("calls onRefresh when update button is clicked", () => {
    render(<EconomicCalendarFilters {...defaultProps} />);
    fireEvent.click(screen.getByText("Atualizar"));
    expect(defaultProps.onRefresh).toHaveBeenCalled();
  });

  it("disables button when loading", () => {
    render(<EconomicCalendarFilters {...defaultProps} loading={true} />);
    expect(screen.getByText("Carregando…")).toBeDisabled();
  });

  it("renders with empty countries list", () => {
    render(<EconomicCalendarFilters {...defaultProps} countries={[]} />);
    expect(screen.getByText("Todos os países")).toBeInTheDocument();
  });
});
