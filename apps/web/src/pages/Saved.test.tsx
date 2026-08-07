import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { Saved } from "./Saved";

function wrap(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Saved", () => {
  it("renders saved jobs and removes one on click", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify([
          {
            id: "j1",
            source: "ashby",
            company: "Ramp",
            title: "FDE",
            location: "SF",
            url: "https://x",
            score: 90,
            reason: "great",
            saved_at: "2026-08-06T00:00:00Z",
          },
        ]),
        { headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    wrap(<Saved />);

    await waitFor(() => expect(screen.getByText("FDE")).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: /remove/i }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/jobs/j1",
        expect.objectContaining({ method: "DELETE" }),
      ),
    );

    vi.unstubAllGlobals();
  });
});
