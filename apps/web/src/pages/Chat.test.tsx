import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { Chat } from "./Chat";
import type { ChatEvent } from "../types";

vi.mock("../lib/sse", () => ({
  streamChat: vi.fn(),
}));

import { streamChat } from "../lib/sse";

function renderChat() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter><Chat /></MemoryRouter>
    </QueryClientProvider>,
  );
}

async function sendMessage(text: string) {
  await userEvent.type(screen.getByPlaceholderText(/new grad/i), text);
  await userEvent.click(screen.getByRole("button", { name: /send/i }));
}

describe("Chat", () => {
  it("shows a spinner and real status text while busy", async () => {
    let resolveStream!: () => void;
    vi.mocked(streamChat).mockImplementation(
      (_body: unknown, onEvent: (e: ChatEvent) => void) =>
        new Promise<void>((resolve) => {
          onEvent({ type: "status", text: "Reading your resume and preferences…" });
          resolveStream = resolve;
        }),
    );
    renderChat();
    await sendMessage("FDE in SF");
    expect(await screen.findByRole("status", { name: /loading/i })).toBeInTheDocument();
    expect(screen.getByText("Reading your resume and preferences…")).toBeInTheDocument();
    await act(async () => {
      resolveStream();
    });
  });

  it("renders the narrative paragraph and compact job list on results", async () => {
    vi.mocked(streamChat).mockImplementation(
      async (_body: unknown, onEvent: (e: ChatEvent) => void) => {
        onEvent({ type: "narrative", text: "Hey Brice, I found 1 great match." });
        onEvent({
          type: "result",
          job: {
            source: "ashby", company: "Ramp", title: "FDE", location: "SF",
            url: "https://x", score: 90, reason: "great",
          },
        });
        onEvent({ type: "done", count: 1 });
      },
    );
    renderChat();
    await sendMessage("FDE in SF");
    expect(await screen.findByText("Hey Brice, I found 1 great match.")).toBeInTheDocument();
    expect(screen.getByText("FDE")).toBeInTheDocument();
  });

  it("does not also show the synthesized fallback count when a real narrative arrived", async () => {
    vi.mocked(streamChat).mockImplementation(
      async (_body: unknown, onEvent: (e: ChatEvent) => void) => {
        onEvent({ type: "narrative", text: "Hey Brice, I found 1 great match." });
        onEvent({
          type: "result",
          job: {
            source: "ashby", company: "Ramp", title: "FDE", location: "SF",
            url: "https://x", score: 90, reason: "great",
          },
        });
        onEvent({ type: "done", count: 1 });
      },
    );
    renderChat();
    await sendMessage("FDE in SF");
    expect(await screen.findByText("Hey Brice, I found 1 great match.")).toBeInTheDocument();
    expect(screen.queryByText(/^Found \d+ role/)).not.toBeInTheDocument();
  });

  it("hides the spinner/ticker as soon as narrative arrives, before the stream resolves", async () => {
    let resolveStream!: () => void;
    vi.mocked(streamChat).mockImplementation(
      (_body: unknown, onEvent: (e: ChatEvent) => void) =>
        new Promise<void>((resolve) => {
          onEvent({ type: "narrative", text: "Hey, done already." });
          resolveStream = resolve;
        }),
    );
    renderChat();
    await sendMessage("FDE in SF");
    expect(await screen.findByText("Hey, done already.")).toBeInTheDocument();
    // streamChat's promise is still pending (busy is still true), but the
    // spinner/ticker must already be gone because narrative has landed.
    expect(screen.queryByRole("status", { name: /loading/i })).not.toBeInTheDocument();
    await act(async () => {
      resolveStream();
    });
  });

  it("falls back to a plain count if done arrives with no narrative", async () => {
    vi.mocked(streamChat).mockImplementation(
      async (_body: unknown, onEvent: (e: ChatEvent) => void) => {
        onEvent({ type: "done", count: 0 });
      },
    );
    renderChat();
    await sendMessage("anything");
    expect(await screen.findByText("Found 0 roles.")).toBeInTheDocument();
  });

  it("does not show a synthesized 'Found N roles' fallback after a clarify turn", async () => {
    vi.mocked(streamChat).mockImplementation(
      async (_body: unknown, onEvent: (e: ChatEvent) => void) => {
        onEvent({ type: "clarify", question: "What city are you looking in?" });
        onEvent({ type: "done", count: 0 });
      },
    );
    renderChat();
    await sendMessage("anything");
    expect(
      await screen.findByText("What city are you looking in?"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/^Found \d+ role/)).not.toBeInTheDocument();
  });

  it("shows the backend's no-results narrative when provided", async () => {
    vi.mocked(streamChat).mockImplementation(
      async (_body: unknown, onEvent: (e: ChatEvent) => void) => {
        onEvent({ type: "narrative", text: "I didn't find any roles matching that this time." });
        onEvent({ type: "done", count: 0 });
      },
    );
    renderChat();
    await sendMessage("anything");
    expect(
      await screen.findByText("I didn't find any roles matching that this time."),
    ).toBeInTheDocument();
  });
});
