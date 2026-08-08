import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../api";

export function Onboarding() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [name, setName] = useState("");
  const nav = useNavigate();
  const qc = useQueryClient();

  const [fileName, setFileName] = useState("");

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileName(file.name);
    setBusy(true);
    setError("");
    try {
      await api.uploadFile("/profile/resume", file);
    } catch {
      setError("Upload failed — please use a PDF or DOCX.");
      setBusy(false);
      return;
    }
    if (name.trim()) {
      try {
        await api.put("/profile/name", { name: name.trim() });
      } catch {
        // Name personalization is a nice-to-have — don't block onboarding
        // completion or show the resume-specific error for a name-PUT failure.
        console.error("Failed to save name during onboarding");
      }
    }
    await qc.invalidateQueries({ queryKey: ["profile"] });
    nav("/");
    setBusy(false);
  }

  return (
    <div className="mx-auto mt-16 max-w-md p-6">
      <h1 className="text-2xl font-semibold text-fg">Upload your resume</h1>
      <p className="mt-2 text-muted">
        PDF or DOCX. We use it to match roles to you.
      </p>

      <label className="mt-6 block text-sm font-medium text-fg">
        What should we call you?
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Your first name"
          disabled={busy}
          className="mt-1 w-full rounded-lg border border-border bg-surface p-2 font-normal text-fg"
        />
      </label>

      <label
        className={`mt-6 flex cursor-pointer flex-col items-center justify-center rounded-bubble border-2 border-dashed border-border bg-surface px-6 py-10 text-center shadow-soft transition hover:border-accent ${
          busy ? "pointer-events-none opacity-60" : ""
        }`}
      >
        <span className="text-lg font-medium text-fg">
          {busy ? "Uploading…" : "Choose a PDF or DOCX file"}
        </span>
        <span className="mt-1 text-sm text-muted">
          {fileName || "Click here to browse"}
        </span>
        <input
          aria-label="resume"
          type="file"
          accept=".pdf,.docx"
          onChange={onFile}
          disabled={busy}
          className="hidden"
        />
      </label>

      {error && <p className="mt-3 text-error">{error}</p>}
    </div>
  );
}
