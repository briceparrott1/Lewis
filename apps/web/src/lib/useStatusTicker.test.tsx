import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useStatusTicker } from "./useStatusTicker";

describe("useStatusTicker", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows real status text immediately when it arrives", () => {
    const { result, rerender } = renderHook(
      ({ active, realText }) => useStatusTicker(active, realText),
      { initialProps: { active: true, realText: null as string | null } },
    );
    expect(result.current).toBeNull();
    act(() => {
      rerender({ active: true, realText: "Scanning 40 companies…" });
    });
    expect(result.current).toBe("Scanning 40 companies…");
  });

  it("swaps to a filler phrase after the swap window if no new real text arrives", () => {
    const { result } = renderHook(
      ({ active, realText }) =>
        useStatusTicker(active, realText, { random: () => 0 }),
      { initialProps: { active: true, realText: "Scanning…" as string | null } },
    );
    expect(result.current).toBe("Scanning…");
    act(() => {
      vi.advanceTimersByTime(3100);
    });
    expect(result.current).not.toBe("Scanning…");
    expect(result.current).not.toBeNull();
  });

  it("does not swap to filler within the cooldown after a fresh real event", () => {
    const { result, rerender } = renderHook(
      ({ active, realText }) =>
        useStatusTicker(active, realText, { random: () => 0 }),
      { initialProps: { active: true, realText: "A" as string | null } },
    );
    act(() => {
      vi.advanceTimersByTime(2500);
    });
    act(() => {
      rerender({ active: true, realText: "B" });
    });
    act(() => {
      vi.advanceTimersByTime(900); // well under the 1.75s minimum-visible floor
    });
    expect(result.current).toBe("B");
  });

  it("stops and resets when active becomes false", () => {
    const { result, rerender } = renderHook(
      ({ active, realText }) => useStatusTicker(active, realText),
      { initialProps: { active: true, realText: "Scanning…" as string | null } },
    );
    act(() => {
      rerender({ active: false, realText: "Scanning…" });
    });
    expect(result.current).toBeNull();
  });
});
