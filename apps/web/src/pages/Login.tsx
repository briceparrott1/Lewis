import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";

export function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const nav = useNavigate();
  const { refresh } = useAuth();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api.post("/auth/login", { email, password });
      await refresh(); // wait for the "me" query to refetch before routing (guards read it)
      nav("/");
    } catch {
      setError("Invalid email or password");
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-page px-6">
      <form onSubmit={submit} className="flex w-full max-w-sm flex-col gap-3 rounded-bubble bg-surface p-8 shadow-soft">
        <h1 className="text-2xl font-semibold text-fg">Log in to Lewis</h1>
        <input aria-label="email" className="rounded-lg border border-border p-2 text-fg" placeholder="Email"
          value={email} onChange={(e) => setEmail(e.target.value)} />
        <input aria-label="password" type="password" className="rounded-lg border border-border p-2 text-fg"
          placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} />
        {error && <p className="text-sm text-error">{error}</p>}
        <button className="rounded-lg bg-accent p-2 text-accent-foreground" type="submit">Log in</button>
        <Link className="text-sm text-accent" to="/signup">Need an account? Sign up</Link>
      </form>
    </div>
  );
}
