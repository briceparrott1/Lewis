import { createContext, useContext, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import type { User } from "./types";

async function fetchMe(): Promise<User | null> {
  try {
    return (await api.get("/auth/me")) as User;
  } catch {
    return null;
  }
}

interface AuthValue { user: User | null; loading: boolean; refresh: () => void; }
const Ctx = createContext<AuthValue>({ user: null, loading: true, refresh: () => {} });

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["me"], queryFn: fetchMe });
  return (
    <Ctx.Provider
      value={{
        user: data ?? null,
        loading: isLoading,
        refresh: () => qc.invalidateQueries({ queryKey: ["me"] }),
      }}
    >
      {children}
    </Ctx.Provider>
  );
}

export const useAuth = () => useContext(Ctx);
