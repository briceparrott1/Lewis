import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";

export function Signup() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const nav = useNavigate();
  const { refresh } = useAuth();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api.post("/auth/signup", { email, password });
      await refresh(); // wait for the "me" query to refetch before routing (guards read it)
      nav("/");
    } catch {
      setError("Could not sign up — that email may already be registered.");
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-page px-6">
      <form onSubmit={submit} className="flex w-full max-w-sm flex-col gap-3 rounded-bubble bg-surface p-8 shadow-soft">
        <h1 className="text-2xl font-semibold text-fg">Create your Lewis account</h1>
        <input aria-label="email" className="rounded-lg border border-border p-2 text-fg" placeholder="Email"
          value={email} onChange={(e) => setEmail(e.target.value)} />
        <input aria-label="password" type="password" className="rounded-lg border border-border p-2 text-fg"
          placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} />
        {error && <p className="text-sm text-error">{error}</p>}
        <button className="rounded-lg bg-accent p-2 text-accent-foreground" type="submit">Sign up</button>
        <Link className="text-sm text-accent" to="/login">Already have an account? Log in</Link>
      </form>
    </div>
  );
}
