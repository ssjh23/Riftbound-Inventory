import { useState } from "react";
import { login, register } from "../auth";

export default function Login({ onLogin }: { onLogin: (username: string) => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (mode === "register") {
      if (password.length < 6) {
        setError("Password must be at least 6 characters.");
        return;
      }
      if (password !== confirm) {
        setError("Passwords do not match.");
        return;
      }
    }

    setLoading(true);
    try {
      if (mode === "register") {
        await register(username, password);
        // Auto-login after registration
        const data = await login(username, password);
        onLogin(data.username);
      } else {
        const data = await login(username, password);
        onLogin(data.username);
      }
    } catch (err) {
      setError(String(err instanceof Error ? err.message : err));
    } finally {
      setLoading(false);
    }
  }

  function switchMode(next: "login" | "register") {
    setMode(next);
    setError(null);
    setConfirm("");
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <h1>Riftbound Inventory</h1>

        <div className="login-tabs">
          <button
            className={`tab${mode === "login" ? " active" : ""}`}
            onClick={() => switchMode("login")}
            type="button"
          >
            Log in
          </button>
          <button
            className={`tab${mode === "register" ? " active" : ""}`}
            onClick={() => switchMode("register")}
            type="button"
          >
            Register
          </button>
        </div>

        <form onSubmit={handleSubmit} className="login-form">
          <label>
            Username
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              required
              autoFocus
            />
          </label>

          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === "register" ? "new-password" : "current-password"}
              required
            />
          </label>

          {mode === "register" && (
            <label>
              Confirm password
              <input
                type="password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                autoComplete="new-password"
                required
              />
            </label>
          )}

          {error && <p className="login-error">{error}</p>}

          <button type="submit" className="login-submit" disabled={loading}>
            {loading ? "…" : mode === "login" ? "Log in" : "Create account"}
          </button>
        </form>
      </div>
    </div>
  );
}
