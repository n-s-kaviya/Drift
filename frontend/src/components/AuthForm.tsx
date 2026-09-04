import { useState } from "react";
import { login, register } from "../lib/api";
import { setToken } from "../lib/auth";

export function AuthForm({ onSuccess }: { onSuccess: () => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      if (mode === "register") await register(email, password);
      const token = await login(email, password);
      setToken(token);
      onSuccess();
    } catch {
      setError(mode === "login" ? "Invalid email or password." : "Could not create account.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="w-full max-w-md rounded-xl border border-[var(--border)] bg-[var(--card)] p-6 shadow-lg">
      <h1 className="text-2xl font-semibold">Smart Market Watchlist</h1>
      <p className="mt-1 text-sm text-[var(--muted-foreground)]">
        Track stocks and see what meaningfully changed since your last visit.
      </p>

      <div className="mt-4 flex gap-2">
        <button
          type="button"
          className={`flex-1 rounded-lg px-3 py-2 text-sm ${mode === "login" ? "bg-[var(--primary)] text-white" : "bg-[var(--muted)]"}`}
          onClick={() => setMode("login")}
        >
          Sign in
        </button>
        <button
          type="button"
          className={`flex-1 rounded-lg px-3 py-2 text-sm ${mode === "register" ? "bg-[var(--primary)] text-white" : "bg-[var(--muted)]"}`}
          onClick={() => setMode("register")}
        >
          Create account
        </button>
      </div>

      {error && <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm text-[var(--destructive)]">{error}</p>}

      <form onSubmit={handleSubmit} className="mt-4 space-y-3">
        <div>
          <label className="text-sm font-medium">Email</label>
          <input
            type="email"
            className="mt-1 w-full rounded-lg border border-[var(--border)] px-3 py-2"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>
        <div>
          <label className="text-sm font-medium">Password</label>
          <input
            type="password"
            className="mt-1 w-full rounded-lg border border-[var(--border)] px-3 py-2"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={6}
          />
        </div>
        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-lg bg-[var(--primary)] py-2.5 text-sm font-medium text-white disabled:opacity-50"
        >
          {loading ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
        </button>
      </form>
    </div>
  );
}
