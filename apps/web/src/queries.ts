import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import type { Profile } from "./types";

export function useProfile() {
  return useQuery({ queryKey: ["profile"], queryFn: () => api.get("/profile") as Promise<Profile> });
}
