import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../api";

export function Onboarding() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
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
      <p className="mt-2 text-gray-600">
        PDF or DOCX. We use it to match roles to you.
      </p>

      <label
        className={`mt-6 flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-gray-300 px-6 py-10 text-center transition hover:border-black hover:bg-gray-50 ${
          busy ? "pointer-events-none opacity-60" : ""
        }`}
      >
        <span className="text-lg font-medium">
          {busy ? "Uploading…" : "Choose a PDF or DOCX file"}
        </span>
        <span className="mt-1 text-sm text-gray-500">
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

      {error && <p className="mt-3 text-red-600">{error}</p>}
    </div>
  );
}
