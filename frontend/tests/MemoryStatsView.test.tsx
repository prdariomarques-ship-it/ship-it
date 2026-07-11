import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MemoryStatsView } from "@/components/admin/MemoryStatsView";
import type { MemoryStats } from "@/lib/admin-types";

const stats: MemoryStats = {
  collection: { name: "darioos_memory", points_count: 120, vectors_count: 120, status: "green" },
  embeddings_total: 3,
  embeddings_by_source: { whatsapp: 2, knowledge: 1 },
  drive_indexed_files: 5,
  drive_last_indexed_at: new Date().toISOString(),
  cache_backend: "redis",
};

describe("MemoryStatsView", () => {
  it("renders totals and the collection name", () => {
    render(<MemoryStatsView stats={stats} />);
    expect(screen.getByText("darioos_memory")).toBeInTheDocument();
    expect(screen.getByText("redis")).toBeInTheDocument();
  });

  it("renders one badge per embedding source with its count", () => {
    render(<MemoryStatsView stats={stats} />);
    expect(screen.getByText("whatsapp: 2")).toBeInTheDocument();
    expect(screen.getByText("knowledge: 1")).toBeInTheDocument();
  });

  it("shows 'não disponível' when the Qdrant collection could not be reached", () => {
    const unavailable = { ...stats, collection: { name: "darioos_memory", points_count: null, vectors_count: null, status: null } };
    render(<MemoryStatsView stats={unavailable} />);
    expect(screen.getAllByText("não disponível").length).toBeGreaterThan(0);
  });
});
