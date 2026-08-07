import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../api";

export function Onboarding() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const nav = useNavigate();
  const qc = useQueryClient();

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      await api.uploadFile("/profile/resume", file);
      await qc.invalidateQueries({ queryKey: ["profile"] });
      nav("/");
    } catch {
      setError("Upload failed — please use a PDF or DOCX.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto mt-24 max-w-md p-6">
      <h1 className="text-2xl font-semibold">Upload your resume</h1>
      <p className="mt-2 text-gray-600">PDF or DOCX. We use it to match roles to you.</p>
      <input aria-label="resume" type="file" accept=".pdf,.docx" onChange={onFile}
        disabled={busy} className="mt-4" />
      {busy && <p className="mt-2">Uploading…</p>}
      {error && <p className="mt-2 text-red-600">{error}</p>}
    </div>
  );
}
