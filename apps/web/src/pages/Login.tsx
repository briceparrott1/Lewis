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
    <form onSubmit={submit} className="mx-auto mt-24 flex max-w-sm flex-col gap-3 p-6">
      <h1 className="text-2xl font-semibold">Log in to Lewis</h1>
      <input aria-label="email" className="rounded border p-2" placeholder="Email"
        value={email} onChange={(e) => setEmail(e.target.value)} />
      <input aria-label="password" type="password" className="rounded border p-2"
        placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} />
      {error && <p className="text-sm text-red-600">{error}</p>}
      <button className="rounded bg-black p-2 text-white" type="submit">Log in</button>
      <Link className="text-sm text-blue-600" to="/signup">Need an account? Sign up</Link>
    </form>
  );
}
