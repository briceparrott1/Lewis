import type { RankedJob } from "../types";

export function CompactJobRow({
  job, onSave, busy,
}: {
  job: RankedJob;
  onSave: () => void;
  busy?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-border py-2 text-sm last:border-b-0">
      <div className="min-w-0">
        <a href={job.url} target="_blank" rel="noreferrer"
          className="font-medium text-accent hover:underline">{job.title}</a>
        <p className="truncate text-muted">
          {job.company}{job.location ? ` · ${job.location}` : ""}
        </p>
      </div>
      <button onClick={onSave} disabled={busy}
        className="shrink-0 rounded-lg border border-border px-2 py-1 text-xs text-fg hover:bg-page">
        Save
      </button>
    </div>
  );
}
