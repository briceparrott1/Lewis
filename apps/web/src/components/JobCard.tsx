import type { RankedJob, SavedJob } from "../types";

export function JobCard({
  job, action, onAction, busy,
}: {
  job: RankedJob | SavedJob;
  action: "save" | "unsave";
  onAction: () => void;
  busy?: boolean;
}) {
  return (
    <div className="rounded-lg border p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <a href={job.url} target="_blank" rel="noreferrer"
            className="font-semibold text-blue-700 hover:underline">{job.title}</a>
          <p className="text-sm text-gray-600">
            {job.company}{job.location ? ` · ${job.location}` : ""}
          </p>
        </div>
        {typeof job.score === "number" && (
          <span className="rounded-full bg-green-100 px-2 py-1 text-xs font-medium text-green-800">
            {job.score}
          </span>
        )}
      </div>
      {job.reason && <p className="mt-2 text-sm text-gray-700">{job.reason}</p>}
      <button onClick={onAction} disabled={busy}
        className="mt-3 rounded border px-3 py-1 text-sm hover:bg-gray-50">
        {action === "save" ? "Save" : "Remove"}
      </button>
    </div>
  );
}
