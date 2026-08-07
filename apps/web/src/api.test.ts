import { describe, expect, it, vi } from "vitest";
import { api } from "./api";

describe("api", () => {
  it("GET parses json and includes credentials", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ ok: true }), {
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const out = await api.get("/health");
    expect(out).toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/health",
      expect.objectContaining({ credentials: "include" }),
    );
    vi.unstubAllGlobals();
  });
});
