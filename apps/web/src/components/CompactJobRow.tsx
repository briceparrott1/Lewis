import type { RankedJob } from "../types";

export function CompactJobRow({
  job, onSave, busy,
}: {
  job: RankedJob;
  onSave: () => void;
  busy?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-3 border-b py-2 text-sm last:border-b-0">
      <div className="min-w-0">
        <a href={job.url} target="_blank" rel="noreferrer"
          className="font-medium text-blue-700 hover:underline">{job.title}</a>
        <p className="truncate text-gray-500">
          {job.company}{job.location ? ` · ${job.location}` : ""}
        </p>
      </div>
      <button onClick={onSave} disabled={busy}
        className="shrink-0 rounded border px-2 py-1 text-xs hover:bg-gray-50">
        Save
      </button>
    </div>
  );
}
