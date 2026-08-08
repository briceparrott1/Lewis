import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AuthProvider } from "./auth";
import { App } from "./App";

function renderApp(path: string, profileOverrides: Record<string, unknown> = {}) {
  const fetchMock = vi.fn(async (url: string) => {
    if (url === "/api/auth/me")
      return new Response(JSON.stringify({ id: "u1", email: "a@b.com" }), {
        headers: { "content-type": "application/json" },
      });
    if (url === "/api/profile")
      return new Response(
        JSON.stringify({
          name: null,
          resume_text: "resume",
          raw_prefs_text: null,
          structured_prefs: {},
          ...profileOverrides,
        }),
        { headers: { "content-type": "application/json" } },
      );
    return new Response("null", { headers: { "content-type": "application/json" } });
  });
  vi.stubGlobal("fetch", fetchMock);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <AuthProvider>
          <App />
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("App routing", () => {
  it("shows the shared header nav when visiting onboarding while authenticated", async () => {
    renderApp("/onboarding");
    expect(await screen.findByText("Upload your resume")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Chat" })).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("redirects an authenticated user with no resume from / to onboarding", async () => {
    renderApp("/", { resume_text: null });
    expect(await screen.findByText("Upload your resume")).toBeInTheDocument();
    vi.unstubAllGlobals();
  });
});
