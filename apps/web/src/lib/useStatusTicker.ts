import { useEffect, useRef, useState } from "react";

export interface StatusTickerOptions {
  fillers?: string[];
  minVisibleMs?: number;
  swapMinMs?: number;
  swapMaxMs?: number;
  realCooldownMs?: number;
  random?: () => number;
}

const DEFAULT_FILLERS = [
  "Sifting through job boards…",
  "Reticulating listings…",
  "Cross-referencing your resume…",
  "Weighing the tradeoffs…",
  "Double-checking the fine print…",
  "Consulting the job-search oracle…",
  "Untangling job titles…",
  "Making sure nothing's missed…",
];

const POLL_MS = 250;

// Timing is research-backed, not arbitrary: NN/g response-time thresholds put
// this kind of wait past the 10s "needs active feedback" mark, and Buell &
// Norton's "labor illusion" findings show specific, real activity text reads
// as more trustworthy than a generic spinner — so real status always wins,
// and filler only fills genuine gaps between real updates.
export function useStatusTicker(
  active: boolean,
  realText: string | null,
  options: StatusTickerOptions = {},
): string | null {
  const {
    fillers = DEFAULT_FILLERS,
    minVisibleMs = 1750,
    swapMinMs = 2000,
    swapMaxMs = 3000,
    realCooldownMs = 1000,
    random = Math.random,
  } = options;

  const [displayText, setDisplayText] = useState<string | null>(null);
  const lastChangeAt = useRef(0);
  const lastRealAt = useRef(0);

  useEffect(() => {
    if (!active || realText === null) return;
    setDisplayText(realText);
    const now = Date.now();
    lastChangeAt.current = now;
    lastRealAt.current = now;
  }, [realText, active]);

  useEffect(() => {
    if (!active) {
      setDisplayText(null);
      return;
    }
    const id = setInterval(() => {
      const now = Date.now();
      const sinceChange = now - lastChangeAt.current;
      const sinceReal = now - lastRealAt.current;
      const swapWindow = swapMinMs + random() * (swapMaxMs - swapMinMs);
      if (sinceChange < minVisibleMs) return;
      if (sinceChange < swapWindow) return;
      if (sinceReal < realCooldownMs) return;
      setDisplayText((current) => {
        const pool = fillers.filter((f) => f !== current);
        const next = pool[Math.floor(random() * pool.length)];
        lastChangeAt.current = now;
        return next;
      });
    }, POLL_MS);
    return () => clearInterval(id);
  }, [active, fillers, minVisibleMs, swapMinMs, swapMaxMs, realCooldownMs, random]);

  return displayText;
}
