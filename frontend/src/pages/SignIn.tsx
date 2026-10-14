import { useState, type FormEvent } from "react";
import { api, ApiError, type Me } from "../api";
import { useApp } from "../components/ui";

export function SignIn({ mode, next }: { mode: "login" | "register"; next?: string }) {
  const { setMe, go, toast } = useApp();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent, demo = false) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const me = mode === "register" && !demo
        ? await api<Me>("POST", "/api/auth/register", { name, email, password })
        : await api<Me>("POST", "/api/auth/login", demo
          ? { email: "jo@example.test", password: "Liming-2026-demo" } : { email, password });
      setMe(me);
      if (mode === "register" && !demo) toast(`Welcome, ${me.user.name}. Let's plan something.`);
      go(next && next !== "#/login" ? next : mode === "register" && !demo ? "#/new" : "#/trips");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page narrow">
      <form className="card" onSubmit={submit}>
        <h1>{mode === "login" ? "Welcome back" : "Start planning"}</h1>
        {mode === "register" && (
          <label className="field">Your name
            <input value={name} onChange={(e) => setName(e.target.value)} autoComplete="given-name" required maxLength={80} />
          </label>
        )}
        <label className="field">Email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" required />
        </label>
        <label className="field">Password
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required
                 autoComplete={mode === "login" ? "current-password" : "new-password"}
                 minLength={mode === "register" ? 10 : undefined} />
          {mode === "register" && <span className="hint">At least 10 characters. A short phrase works well.</span>}
        </label>
        {error && <p className="error" role="alert">{error}</p>}
        <div className="actions">
          <button className="btn primary" disabled={busy}>{mode === "login" ? "Log in" : "Create account"}</button>
          {mode === "login" ? <a href="#/register">New here? Create an account</a> : <a href="#/login">Already have one? Log in</a>}
        </div>
        <p className="demo">
          Just looking? <button type="button" className="link" disabled={busy} onClick={(e) => submit(e, true)}>
            Log in as Jo</button>, who already has a St Vincent trip planned.
        </p>
      </form>
    </div>
  );
}
