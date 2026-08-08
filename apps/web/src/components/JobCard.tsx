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
    <div className="rounded-bubble border border-border bg-surface p-4 shadow-soft">
      <div className="flex items-start justify-between gap-3">
        <div>
          <a href={job.url} target="_blank" rel="noreferrer"
            className="font-semibold text-accent hover:underline">{job.title}</a>
          <p className="text-sm text-muted">
            {job.company}{job.location ? ` · ${job.location}` : ""}
          </p>
        </div>
        {typeof job.score === "number" && (
          <span className="rounded-full bg-success-foreground px-2 py-1 text-xs font-medium text-success">
            {job.score}
          </span>
        )}
      </div>
      {job.reason && <p className="mt-2 text-sm text-fg">{job.reason}</p>}
      <button onClick={onAction} disabled={busy}
        className="mt-3 rounded-lg border border-border px-3 py-1 text-sm text-fg hover:bg-page">
        {action === "save" ? "Save" : "Remove"}
      </button>
    </div>
  );
}
