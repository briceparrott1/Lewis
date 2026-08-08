import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AuthProvider } from "../auth";
import { AppLayout } from "./AppLayout";

function renderLayout() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/"]}>
        <AuthProvider>
          <Routes>
            <Route element={<AppLayout />}>
              <Route path="/" element={<div>chat page</div>} />
              <Route path="/login" element={<div>login page</div>} />
            </Route>
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AppLayout", () => {
  it("renders nav links to Chat, Saved, and Profile", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("null", { headers: { "content-type": "application/json" } })),
    );
    renderLayout();
    expect(screen.getByRole("link", { name: "Chat" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "Saved" })).toHaveAttribute("href", "/saved");
    expect(screen.getByRole("link", { name: "Profile" })).toHaveAttribute("href", "/onboarding");
    vi.unstubAllGlobals();
  });

  it("logs out and navigates to /login on Logout click", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url === "/api/auth/logout")
        return new Response("{}", { headers: { "content-type": "application/json" } });
      return new Response("null", { headers: { "content-type": "application/json" } });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderLayout();
    await userEvent.click(screen.getByRole("button", { name: /logout/i }));
    expect(await screen.findByText("login page")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/auth/logout",
      expect.objectContaining({ method: "POST" }),
    );
    vi.unstubAllGlobals();
  });
});
