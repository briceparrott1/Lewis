import { describe, expect, it } from "vitest";
import { parseSSEChunk } from "./sse";

describe("parseSSEChunk", () => {
  it("parses complete frames and returns leftover partial", () => {
    const buf =
      'event: status\ndata: {"type":"status","text":"hi"}\n\n' +
      'event: result\ndata: {"type":"result","job":{"title":"FDE","url":"u"}}\n\n' +
      "event: done\ndata: {"; // partial
    const { events, rest } = parseSSEChunk(buf);
    expect(events.length).toBe(2);
    expect(events[0]).toMatchObject({ type: "status", text: "hi" });
    expect(events[1]).toMatchObject({ type: "result" });
    expect(rest).toBe("event: done\ndata: {");
  });

  it("returns no events when no complete frame yet", () => {
    const { events, rest } = parseSSEChunk("event: status\ndata: {");
    expect(events).toEqual([]);
    expect(rest).toContain("event: status");
  });
});
