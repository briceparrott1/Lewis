import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import type { Profile, RankedJob } from "./types";

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
