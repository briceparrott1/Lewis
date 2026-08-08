import { JobCard } from "../components/JobCard";
import { useJobs, useUnsaveJob } from "../queries";

export function Saved() {
  const { data, isLoading } = useJobs();
  const unsave = useUnsaveJob();
  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-3 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-fg">Saved jobs</h1>
      </div>
      {isLoading && <p className="text-muted">Loading…</p>}
      {data && data.length === 0 && <p className="text-muted">No saved jobs yet.</p>}
      {data?.map((job) => (
        <JobCard
          key={job.id}
          job={job}
          action="unsave"
          busy={unsave.isPending}
          onAction={() => unsave.mutate(job.id)}
        />
      ))}
    </div>
  );
}
