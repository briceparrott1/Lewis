import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { Onboarding } from "./Onboarding";

it("uploads a resume file to the API", async () => {
  const fetchMock = vi.fn(async () =>
    new Response(JSON.stringify({ resume_text: "x" }), {
      headers: { "content-type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter><Onboarding /></MemoryRouter>
    </QueryClientProvider>,
  );
  const file = new File(["hi"], "resume.pdf", { type: "application/pdf" });
  await userEvent.upload(screen.getByLabelText("resume"), file);
  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/profile/resume",
      expect.objectContaining({ method: "POST" }),
    ),
  );
  vi.unstubAllGlobals();
});

it("also submits the name when provided", async () => {
  const fetchMock = vi.fn(async () =>
    new Response(JSON.stringify({ resume_text: "x", name: "Brice" }), {
      headers: { "content-type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter><Onboarding /></MemoryRouter>
    </QueryClientProvider>,
  );
  await userEvent.type(screen.getByPlaceholderText(/your first name/i), "Brice");
  const file = new File(["hi"], "resume.pdf", { type: "application/pdf" });
  await userEvent.upload(screen.getByLabelText("resume"), file);
  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/profile/name",
      expect.objectContaining({ method: "PUT", body: JSON.stringify({ name: "Brice" }) }),
    ),
  );
  vi.unstubAllGlobals();
});
