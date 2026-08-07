import { useEffect, useReducer, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { streamChat } from "../lib/sse";
import { CompactJobRow } from "../components/CompactJobRow";
import { Spinner } from "../components/Spinner";
import { useStatusTicker } from "../lib/useStatusTicker";
import { useSaveJob } from "../queries";
import type { ChatEvent, RankedJob } from "../types";

type Item =
  | { kind: "user"; text: string }
  | { kind: "clarify"; text: string }
  | { kind: "narrative"; text: string }
  | { kind: "result"; job: RankedJob };

function reducer(items: Item[], ev: Item | { kind: "reset" }): Item[] {
  if (ev.kind === "reset") return [];
  return [...items, ev];
}

export function Chat() {
  const [items, dispatch] = useReducer(reducer, []);
  const [input, setInput] = useState("");
  const [convo, setConvo] = useState(() => crypto.randomUUID());
  const [busy, setBusy] = useState(false);
  const [statusText, setStatusText] = useState<string | null>(null);
  const gotNarrative = useRef(false);
  const gotClarify = useRef(false);
  const abort = useRef<AbortController | null>(null);
  const save = useSaveJob();
  const tickerText = useStatusTicker(busy, statusText);

  useEffect(() => () => abort.current?.abort(), []);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim() || busy) return;
    const message = input.trim();
    setInput("");
    dispatch({ kind: "user", text: message });
    setBusy(true);
    setStatusText("Getting started…"); // neutral placeholder — never a filler phrase
    gotNarrative.current = false;
    gotClarify.current = false;
    abort.current = new AbortController();
    try {
      await streamChat({ message, conversation_id: convo }, (ev: ChatEvent) => {
        if (ev.type === "status") setStatusText(ev.text);
        else if (ev.type === "clarify") {
          gotClarify.current = true;
          dispatch({ kind: "clarify", text: ev.question });
        } else if (ev.type === "narrative") {
          gotNarrative.current = true;
          dispatch({ kind: "narrative", text: ev.text });
        } else if (ev.type === "result") dispatch({ kind: "result", job: ev.job });
        else if (ev.type === "done" && !gotNarrative.current && !gotClarify.current) {
          dispatch({
            kind: "narrative",
            text: `Found ${ev.count} role${ev.count === 1 ? "" : "s"}.`,
          });
        }
      }, abort.current.signal);
    } catch {
      dispatch({ kind: "narrative", text: "Something went wrong. Try again." });
    } finally {
      setBusy(false);
      setStatusText(null);
    }
  }

  function newChat() {
    dispatch({ kind: "reset" });
    setConvo(crypto.randomUUID());
  }

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-3 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Find roles</h1>
        <div className="flex gap-3 text-sm">
          <Link className="text-blue-600" to="/saved">Saved jobs</Link>
          <button className="text-gray-600" onClick={newChat}>New chat</button>
        </div>
      </div>
      <div className="flex flex-col gap-3">
        {items.map((it, i) => {
          if (it.kind === "user")
            return <div key={i} className="self-end rounded bg-black px-3 py-2 text-white">{it.text}</div>;
          if (it.kind === "clarify")
            return <div key={i} className="rounded bg-gray-100 px-3 py-2">{it.text}</div>;
          if (it.kind === "narrative")
            return <p key={i} className="rounded bg-gray-50 px-3 py-3 leading-relaxed">{it.text}</p>;
          return (
            <CompactJobRow key={i} job={it.job} busy={save.isPending}
              onSave={() => save.mutate(it.job)} />
          );
        })}
        {busy && !gotNarrative.current && (
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <Spinner />
            <span>{tickerText}</span>
          </div>
        )}
      </div>
      <form onSubmit={send} className="sticky bottom-4 mt-4 flex gap-2">
        <input className="flex-1 rounded border p-2" placeholder="e.g. new grad FDE roles in SF"
          value={input} onChange={(e) => setInput(e.target.value)} disabled={busy} />
        <button className="rounded bg-black px-4 text-white" disabled={busy}>Send</button>
      </form>
    </div>
  );
}
