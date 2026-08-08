import type { Profile } from "../types";

function asStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((v): v is string => typeof v === "string")
    : [];
}

export function greetingText(profile: Profile): string {
  const who = profile.name ? `, ${profile.name}` : "";
  const roles = asStringArray(profile.structured_prefs.role_keywords);
  const locations = asStringArray(profile.structured_prefs.locations);
  if (roles.length > 0) {
    const where = locations.length > 0 ? ` in ${locations.join(", ")}` : "";
    return (
      `Hey${who}! Last time you were looking for ${roles.join(", ")}${where} — ` +
      `still the plan, or has something changed?`
    );
  }
  return (
    `Hey${who}! Tell me what kind of role you're looking for — location, ` +
    `seniority, anything that matters to you — and I'll start searching.`
  );
}
