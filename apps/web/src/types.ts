export interface User {
  id: string;
  email: string;
}

export interface Profile {
  name: string | null;
  resume_text: string | null;
  raw_prefs_text: string | null;
  structured_prefs: Record<string, unknown>;
}

export interface RankedJob {
  source: string;
  company: string;
  title: string;
  location: string | null;
  url: string;
  score?: number;
  reason?: string;
}

export interface SavedJob extends RankedJob {
  id: string;
  saved_at: string;
}

export type ChatEvent =
  | { type: "status"; text: string }
  | { type: "clarify"; question: string }
  | { type: "narrative"; text: string }
  | { type: "result"; job: RankedJob }
  | { type: "done"; count: number };
