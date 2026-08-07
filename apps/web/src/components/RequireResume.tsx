import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useProfile } from "../queries";

export function RequireResume({ children }: { children: ReactNode }) {
  const { data, isLoading } = useProfile();
  if (isLoading) return <div className="p-8">Loading…</div>;
  if (!data?.resume_text) return <Navigate to="/onboarding" replace />;
  return <>{children}</>;
}
