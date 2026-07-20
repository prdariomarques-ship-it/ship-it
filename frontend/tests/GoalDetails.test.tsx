import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import GoalDetails from "@/components/goals/GoalDetails";

const GOAL = { id: 1, title: "Meta principal", status: "pending", progress_percent: 30 };
const OTHER_GOAL = { id: 2, title: "Outra meta", status: "pending" };

function mockFetchByPath(byPath: Record<string, unknown>) {
  return vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
    const url = String(input);
    const match = Object.keys(byPath).find((path) => url.includes(path));
    if (!match) throw new Error(`Unexpected fetch to ${url}`);
    return { ok: true, status: 200, json: async () => byPath[match] };
  });
}

describe("GoalDetails", () => {
  it("shows the current progress and saves an update", async () => {
    const fetchMock = mockFetchByPath({
      "/dependencies": [],
      "/history": [],
      "/progress": {},
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<GoalDetails goal={GOAL} otherGoals={[OTHER_GOAL]} onChanged={vi.fn()} />);

    const progressInput = await screen.findByLabelText("Progresso");
    expect(progressInput).toHaveValue(30);

    await userEvent.clear(progressInput);
    await userEvent.type(progressInput, "75");
    await userEvent.click(screen.getByRole("button", { name: "Salvar progresso" }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/goals/1/progress"),
        expect.objectContaining({ method: "PATCH" })
      )
    );
  });

  it("shows a cancel button for a cancellable goal and calls the status endpoint", async () => {
    const fetchMock = mockFetchByPath({
      "/dependencies": [],
      "/history": [],
      "/status": {},
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<GoalDetails goal={GOAL} otherGoals={[]} onChanged={vi.fn()} />);

    await userEvent.click(await screen.findByRole("button", { name: "Cancelar meta" }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/goals/1/status"),
        expect.objectContaining({ method: "PATCH" })
      )
    );
    const call = fetchMock.mock.calls.find(([url]) => String(url).includes("/status"));
    expect(JSON.parse((call as [unknown, RequestInit])[1].body as string)).toEqual({
      status: "cancelled",
    });
  });

  it("hides the cancel button for a completed goal", async () => {
    vi.stubGlobal("fetch", mockFetchByPath({ "/dependencies": [], "/history": [] }));
    render(
      <GoalDetails
        goal={{ ...GOAL, status: "completed" }}
        otherGoals={[]}
        onChanged={vi.fn()}
      />
    );

    await screen.findByLabelText("Progresso");
    expect(screen.queryByRole("button", { name: "Cancelar meta" })).not.toBeInTheDocument();
  });

  it("lists existing dependencies and removes one", async () => {
    const fetchMock = mockFetchByPath({
      "/dependencies": [OTHER_GOAL],
      "/history": [],
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<GoalDetails goal={GOAL} otherGoals={[OTHER_GOAL]} onChanged={vi.fn()} />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(await screen.findByText("Outra meta")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Remover" }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/goals/1/dependencies/2"),
        expect.objectContaining({ method: "DELETE" })
      )
    );
  });

  it("adds a new dependency from the candidate list", async () => {
    const fetchMock = mockFetchByPath({ "/dependencies": [], "/history": [] });
    vi.stubGlobal("fetch", fetchMock);
    render(<GoalDetails goal={GOAL} otherGoals={[OTHER_GOAL]} onChanged={vi.fn()} />);

    await screen.findByLabelText("Progresso");
    await userEvent.selectOptions(screen.getByLabelText("Nova dependência"), "2");
    await userEvent.click(screen.getByRole("button", { name: "Adicionar dependência" }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/goals/1/dependencies"),
        expect.objectContaining({ method: "POST" })
      )
    );
    const call = fetchMock.mock.calls.find(
      ([url, options]) =>
        String(url).includes("/goals/1/dependencies") &&
        (options as RequestInit | undefined)?.method === "POST"
    );
    expect(JSON.parse((call as [unknown, RequestInit])[1].body as string)).toEqual({
      depends_on_id: 2,
    });
  });

  it("renders history entries", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetchByPath({
        "/dependencies": [],
        "/history": [{ id: 1, message: "Goal 1 created", created_at: "2026-01-01T00:00:00Z" }],
      })
    );
    render(<GoalDetails goal={GOAL} otherGoals={[]} onChanged={vi.fn()} />);

    expect(await screen.findByText(/Goal 1 created/)).toBeInTheDocument();
  });
});
