import { describe, expect, it } from "vitest";
import { greetingText } from "./greeting";
import type { Profile } from "../types";

function profile(overrides: Partial<Profile> = {}): Profile {
  return {
    name: null,
    resume_text: "resume",
    raw_prefs_text: null,
    structured_prefs: {},
    ...overrides,
  };
}

describe("greetingText", () => {
  it("prompts a new user with no stored preferences", () => {
    const text = greetingText(profile());
    expect(text).toContain("Tell me what kind of role");
    expect(text).not.toContain("Last time");
  });

  it("greets by name when known", () => {
    const text = greetingText(profile({ name: "Brice" }));
    expect(text.startsWith("Hey, Brice!")).toBe(true);
  });

  it("summarizes stored role and location preferences for a returning user", () => {
    const text = greetingText(
      profile({
        name: "Brice",
        structured_prefs: { role_keywords: ["FDE", "SWE"], locations: ["SF", "NYC"] },
      }),
    );
    expect(text).toContain("Last time you were looking for FDE, SWE in SF, NYC");
  });

  it("summarizes a role preference with no location", () => {
    const text = greetingText(
      profile({ structured_prefs: { role_keywords: ["FDE"] } }),
    );
    expect(text).toContain("Last time you were looking for FDE");
    expect(text).not.toContain(" in ");
  });
});
