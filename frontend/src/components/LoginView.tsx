import React, { useEffect, useState } from "react";
import { apiFetch, setTokens, UserInfo } from "../api/client";

interface DemoAccountInfo {
  login: string;
  nazwa: string;
  rola: string;
  wymaga_2fa_docelowo: boolean;
}

interface DemoPayload {
  tryb_demo: boolean;
  ostrzezenie: string;
  haslo_demo: string;
  kod_awarii_wagi_demo: string;
  konta: DemoAccountInfo[];
}

export const LoginView: React.FC<{ onSuccess: (user: UserInfo) => void }> = ({ onSuccess }) => {
  const [login, setLogin] = useState("op_wag");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [demo, setDemo] = useState<DemoPayload | null>(null);

  useEffect(() => {
    apiFetch<DemoPayload>("/api/auth/demo-accounts")
      .then((d) => setDemo(d))
      .catch(() => setDemo(null));
  }, []);

  async function doLogin(uLogin: string, uPass: string) {
    setError(null);
    setLoading(true);
    try {
      const res = await apiFetch<{ access_token: string; refresh_token: string; user: UserInfo }>(
        "/api/auth/login",
        {
          method: "POST",
          body: JSON.stringify({ login: uLogin, password: uPass }),
        }
      );
      setTokens(res.access_token, res.refresh_token);
      onSuccess(res.user);
    } catch (e: any) {
      setError(e.message || "Nie udało się zalogować.");
    } finally {
      setLoading(false);
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    doLogin(login, password);
  }

  return (
    <div className="login-wrapper">
      <div className="login-card">
        <h1 style={{ marginTop: 0, color: "#17365d" }}>E-Magazyn ERP / WMS — Prototyp MVP</h1>
        <p style={{ color: "#475569", marginTop: 0 }}>
          Zintegrowane zarządzanie skupem zbóż, magazynem silosowym, produkcją przemiałową, wydaniami FEFO oraz fakturowaniem.
        </p>

        {error && <div className="alert alert-error">{error}</div>}

        <form onSubmit={handleSubmit}>
          <div className="grid-2">
            <div className="form-row">
              <label htmlFor="login-input">Login użytkownika</label>
              <input
                id="login-input"
                type="text"
                value={login}
                onChange={(e) => setLogin(e.target.value)}
                required
                autoComplete="username"
              />
            </div>
            <div className="form-row">
              <label htmlFor="password-input">Hasło</label>
              <input
                id="password-input"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
              />
            </div>
          </div>
          <button className="btn btn-primary" type="submit" disabled={loading}>
            {loading ? "Logowanie..." : "Zaloguj się"}
          </button>
        </form>

        {demo && (
          <div style={{ marginTop: 22, paddingTop: 16, borderTop: "1px solid #cbd5e1" }}>
            <div className="alert alert-warn" style={{ marginBottom: 10 }}>
              <strong>TRYB DEMONSTRACYJNY:</strong> {demo.ostrzezenie} Hasło demo: <code>{demo.haslo_demo}</code> |
              Kod awarii wagi: <code>{demo.kod_awarii_wagi_demo}</code>
            </div>
            <div style={{ fontWeight: 600, marginBottom: 6 }}>Szybkie logowanie według ról (RBAC):</div>
            <div className="demo-role-grid">
              {demo.konta.map((acc) => (
                <button
                  key={acc.login}
                  type="button"
                  className="btn btn-secondary"
                  style={{ justifyContent: "space-between", fontSize: "0.86rem", padding: "8px 12px" }}
                  onClick={() => {
                    setLogin(acc.login);
                    setPassword(demo.haslo_demo);
                    doLogin(acc.login, demo.haslo_demo);
                  }}
                >
                  <span>
                    <strong>{acc.rola}</strong> ({acc.login})
                  </span>
                  {acc.wymaga_2fa_docelowo && <span className="badge badge-info">2FA docel.</span>}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
