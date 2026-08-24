import { useState } from "react";
import { login } from "../lib/auth";

export default function Login({ onSuccess }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(username, password);
      onSuccess();
    } catch {
      setError("Invalid username or password.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center px-6">
      <form onSubmit={handleSubmit} className="w-full max-w-sm rounded-lg border border-line bg-paper-raised p-8">
        <p className="font-mono text-xs uppercase tracking-widest text-accent-ink">RecoverAI</p>
        <h1 className="mt-1 font-serif text-2xl font-semibold text-ink">Recovery Room login</h1>
        <p className="mt-2 text-sm text-ink-faint">Operator access only — one seeded account per deployment.</p>

        <label className="mt-6 block font-mono text-[11px] uppercase tracking-wide text-ink-faint">Username</label>
        <input
          autoFocus
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          className="mt-1 w-full rounded-md border border-line bg-paper px-3 py-2 text-sm text-ink outline-none focus:border-accent"
        />

        <label className="mt-4 block font-mono text-[11px] uppercase tracking-wide text-ink-faint">Password</label>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="mt-1 w-full rounded-md border border-line bg-paper px-3 py-2 text-sm text-ink outline-none focus:border-accent"
        />

        {error && <p className="mt-3 font-mono text-xs text-danger">{error}</p>}

        <button
          type="submit"
          disabled={loading}
          className="mt-6 w-full rounded-md border border-accent bg-accent-soft px-4 py-2 font-sans text-sm font-medium text-accent-ink transition hover:bg-accent/20 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
