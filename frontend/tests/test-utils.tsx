import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";

// Shared React Query wrapper for hooks/components that call
// lib/admin-api.ts's useQuery-based hooks — retries disabled so a mocked
// rejection surfaces immediately instead of retrying and timing out the test.
export function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
}

export function renderWithQueryClient(ui: ReactNode) {
  const client = createTestQueryClient();
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}
