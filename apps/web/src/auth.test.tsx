import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth";
import { Login } from "./pages/Login";

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter><AuthProvider>{ui}</AuthProvider></MemoryRouter>
    </QueryClientProvider>,
  );
}

function Probe() {
  const { logout } = useAuth();
  return <button onClick={() => logout()}>do logout</button>;
}

describe("Login", () => {
  beforeEach(() => vi.unstubAllGlobals());

  it("shows an error on bad credentials", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("nope", { status: 401 })));
    wrap(<Login />);
    await userEvent.type(screen.getByLabelText("email"), "a@b.com");
    await userEvent.type(screen.getByLabelText("password"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: /log in/i }));
    await waitFor(() =>
      expect(screen.getByText(/invalid email or password/i)).toBeInTheDocument(),
    );
  });
});

describe("useAuth logout", () => {
  it("posts to /auth/logout and invalidates the me query", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url === "/api/auth/logout")
        return new Response("{}", { headers: { "content-type": "application/json" } });
      return new Response("null", { headers: { "content-type": "application/json" } });
    });
    vi.stubGlobal("fetch", fetchMock);
    wrap(<Probe />);
    await userEvent.click(screen.getByRole("button", { name: /do logout/i }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/auth/logout",
        expect.objectContaining({ method: "POST" }),
      ),
    );
    vi.unstubAllGlobals();
  });
});
