import React, { useEffect, useState } from "react";
import { apiFetch, UserInfo } from "../api/client";

export const AdminView: React.FC<{ user: UserInfo; onConfigChanged: () => void }> = ({ user, onConfigChanged }) => {
  const [users, setUsers] = useState<any[]>([]);
  const [configs, setConfigs] = useState<any[]>([]);
  const [audit, setAudit] = useState<any[]>([]);
  const [authCodes, setAuthCodes] = useState<any[]>([]);

  const [newLogin, setNewLogin] = useState("");
  const [newName, setNewName] = useState("");
  const [newPass, setNewPass] = useState("HasloDemo!2026");
  const [newRole, setNewRole] = useState("OP_WAG");
  const [cfgEdit, setCfgEdit] = useState<Record<string, string>>({});

  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const isAdmin = user.rola === "ADMIN";
  const isManager = user.rola === "KIER_MAG";

  async function loadAll() {
    try {
      const cfgList = await apiFetch<any[]>("/api/admin/konfiguracja");
      setConfigs(cfgList);
      const map: Record<string, string> = {};
      cfgList.forEach((c) => {
        map[c.klucz] = c.wartosc;
      });
      setCfgEdit(map);

      if (isAdmin) {
        const [uList, aList] = await Promise.all([
          apiFetch<any[]>("/api/admin/uzytkownicy"),
          apiFetch<any[]>("/api/admin/audyt?limit=100"),
        ]);
        setUsers(uList);
        setAudit(aList);
      }
      if (isManager) {
        const codes = await apiFetch<any[]>("/api/admin/kody-autoryzacyjne");
        setAuthCodes(codes);
      }
    } catch (e: any) {
      setErr(e.message);
    }
  }

  useEffect(() => {
    loadAll();
  }, []);

  async function createUser(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setMsg(null);
    try {
      const res = await apiFetch<any>("/api/admin/uzytkownicy", {
        method: "POST",
        body: JSON.stringify({
          login: newLogin,
          imie_nazwisko: newName,
          password: newPass,
          rola: newRole,
        }),
      });
      setMsg(`Utworzono konto ${res.login} (${res.rola}).`);
      setNewLogin("");
      setNewName("");
      await loadAll();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function toggleActive(u: any) {
    setErr(null);
    try {
      await apiFetch(`/api/admin/uzytkownicy/${u.id}`, {
        method: "PATCH",
        body: JSON.stringify({ czy_aktywny: !u.czy_aktywny }),
      });
      await loadAll();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function saveConfig(klucz: string) {
    setErr(null);
    setMsg(null);
    try {
      await apiFetch(`/api/admin/konfiguracja/${klucz}`, {
        method: "PATCH",
        body: JSON.stringify({ wartosc: cfgEdit[klucz] }),
      });
      setMsg(`Zaktualizowano parametr ${klucz} na ${cfgEdit[klucz]} (zapisano w audycie).`);
      onConfigChanged();
      await loadAll();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function generateCode() {
    setErr(null);
    setMsg(null);
    try {
      const res = await apiFetch<any>("/api/admin/kody-autoryzacyjne", {
        method: "POST",
        body: JSON.stringify({ cel: "AWARIA_WAGI", waznosc_minuty: 120 }),
      });
      setMsg(`Wygenerowano jednorazowy kod autoryzacyjny dla OP_WAG: ${res.kod}`);
      await loadAll();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  return (
    <div>
      {err && <div className="alert alert-error">{err}</div>}
      {msg && <div className="alert alert-success">{msg}</div>}

      {isManager && (
        <div className="card">
          <h2>Kody autoryzacyjne KIER_MAG na awarię wagi (UC-01.5)</h2>
          <button type="button" className="btn btn-primary" onClick={generateCode}>
            + Wygeneruj nowy jednorazowy kod awarii wagi
          </button>
          <div className="table-wrap" style={{ marginTop: 12 }}>
            <table>
              <thead>
                <tr>
                  <th>Kod</th>
                  <th>Cel</th>
                  <th>Status</th>
                  <th>Wygasa (UTC)</th>
                </tr>
              </thead>
              <tbody>
                {authCodes.map((c) => (
                  <tr key={c.id}>
                    <td><code>{c.kod}</code></td>
                    <td>{c.cel}</td>
                    <td>{c.czy_uzyty ? <span className="badge badge-warn">UŻYTY</span> : <span className="badge badge-ok">AKTYWNY</span>}</td>
                    <td>{c.wygasa_utc}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="card">
        <h2>Konfiguracja progów i parametrów systemu</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Klucz</th>
                <th>Wartość</th>
                <th>Opis</th>
                {isAdmin && <th>Zapisz</th>}
              </tr>
            </thead>
            <tbody>
              {configs.map((c) => (
                <tr key={c.klucz}>
                  <td><code>{c.klucz}</code></td>
                  <td>
                    {isAdmin ? (
                      <input
                        type="text"
                        style={{ width: 130, minHeight: 38 }}
                        value={cfgEdit[c.klucz] ?? c.wartosc}
                        onChange={(e) => setCfgEdit((prev) => ({ ...prev, [c.klucz]: e.target.value }))}
                      />
                    ) : (
                      <strong>
                        {c.wartosc} {c.jednostka || ""}
                      </strong>
                    )}
                  </td>
                  <td>{c.opis}</td>
                  {isAdmin && (
                    <td>
                      <button type="button" className="btn btn-primary btn-sm" onClick={() => saveConfig(c.klucz)}>
                        Zapisz
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {isAdmin && (
        <>
          <div className="card">
            <h2>Zarządzanie kontami i rolami RBAC (UC-06.1)</h2>
            <form onSubmit={createUser} style={{ marginBottom: 16 }}>
              <div className="grid-3">
                <div className="form-row">
                  <label>Login</label>
                  <input type="text" value={newLogin} onChange={(e) => setNewLogin(e.target.value)} required />
                </div>
                <div className="form-row">
                  <label>Imię i nazwisko</label>
                  <input type="text" value={newName} onChange={(e) => setNewName(e.target.value)} required />
                </div>
                <div className="form-row">
                  <label>Rola</label>
                  <select value={newRole} onChange={(e) => setNewRole(e.target.value)}>
                    <option value="OP_WAG">OP_WAG</option>
                    <option value="INZ_PROD">INZ_PROD</option>
                    <option value="MAG_WG">MAG_WG</option>
                    <option value="FAKT_KS">FAKT_KS</option>
                    <option value="KIER_MAG">KIER_MAG</option>
                    <option value="ADMIN">ADMIN</option>
                  </select>
                </div>
                <div className="form-row">
                  <label>Hasło początkowe (min. 8 znaków)</label>
                  <input type="password" value={newPass} onChange={(e) => setNewPass(e.target.value)} required />
                </div>
              </div>
              <button type="submit" className="btn btn-primary btn-sm">
                Utwórz konto
              </button>
            </form>

            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Login</th>
                    <th>Imię i nazwisko</th>
                    <th>Rola</th>
                    <th>2FA docelowo</th>
                    <th>Status</th>
                    <th>Akcja</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => (
                    <tr key={u.id}>
                      <td><strong>{u.login}</strong></td>
                      <td>{u.imie_nazwisko}</td>
                      <td><span className="badge badge-info">{u.rola}</span></td>
                      <td>{u.czy_2fa_wymagane ? "Wymagane w prod." : "Nie"}</td>
                      <td>{u.czy_aktywny ? <span className="badge badge-ok">Aktywne</span> : <span className="badge badge-danger">Zablokowane</span>}</td>
                      <td>
                        <button type="button" className="btn btn-secondary btn-sm" onClick={() => toggleActive(u)}>
                          {u.czy_aktywny ? "Zablokuj" : "Odblokuj"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="card">
            <h3>Dziennik audytowy Append-Only (ostatnie 100 zdarzeń)</h3>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Czas UTC</th>
                    <th>Użytkownik (rola)</th>
                    <th>Akcja</th>
                    <th>Zasób</th>
                    <th>Szczegóły JSON</th>
                  </tr>
                </thead>
                <tbody>
                  {audit.map((a) => (
                    <tr key={a.id}>
                      <td><small>{a.znacznik_utc}</small></td>
                      <td>
                        {a.login || "-"} ({a.rola || "-"})
                      </td>
                      <td><strong>{a.akcja}</strong></td>
                      <td>{a.zasob}</td>
                      <td>
                        <code style={{ fontSize: "0.78rem" }}>{JSON.stringify(a.zmiana_stanu)}</code>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
};
