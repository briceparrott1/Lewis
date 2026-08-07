import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import type { Profile, RankedJob, SavedJob } from "./types";

export function useProfile() {
  return useQuery({ queryKey: ["profile"], queryFn: () => api.get("/profile") as Promise<Profile> });
}

export function useSaveJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (job: RankedJob) => api.post("/jobs", job),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
  });
}

export function useJobs() {
  return useQuery({ queryKey: ["jobs"], queryFn: () => api.get("/jobs") as Promise<SavedJob[]> });
}

export function useUnsaveJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.del(`/jobs/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
  });
}
