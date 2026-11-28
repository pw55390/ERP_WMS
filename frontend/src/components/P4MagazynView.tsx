import React, { useEffect, useState } from "react";
import { apiFetch, UserInfo } from "../api/client";

export const P4MagazynView: React.FC<{ user: UserInfo }> = ({ user }) => {
  const [stany, setStany] = useState<any[]>([]);
  const [lokalizacje, setLokalizacje] = useState<any[]>([]);
  const [inwentaryzacje, setInwentaryzacje] = useState<any[]>([]);
  const [rotacja, setRotacja] = useState<any | null>(null);
  const [trace, setTrace] = useState<any | null>(null);
  const [strefaFilter, setStrefaFilter] = useState("");
  const [searchQ, setSearchQ] = useState("");

  // Przesunięcie MM
  const [mmPartiaId, setMmPartiaId] = useState("");
  const [mmTargetLocId, setMmTargetLocId] = useState("");
  const [mmQty, setMmQty] = useState("100");
  const [mmUwagi, setMmUwagi] = useState("Przesunięcie między lokalizacjami");

  // Inwentaryzacja
  const [inwStrefa, setInwStrefa] = useState("WYROBY_GOTOWE");
  const [spisValues, setSpisValues] = useState<Record<string, string>>({});
  const [inwKom, setInwKom] = useState("Zatwierdzono spis z natury");

  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const isManager = user.rola === "KIER_MAG";
  const canCount = ["KIER_MAG", "MAG_WG"].includes(user.rola);

  async function loadAll() {
    try {
      const [sRes, lRes] = await Promise.all([
        apiFetch<{ partie: any[] }>("/api/p4/stany"),
        apiFetch<any[]>("/api/lokalizacje"),
      ]);
      setStany(sRes.partie);
      setLokalizacje(lRes);

      const availLots = sRes.partie.filter((p) => p.status === "DOSTEPNA" && parseFloat(p.masa_dostepna_kg) > 0);
      if (!mmPartiaId && availLots[0]) setMmPartiaId(availLots[0].id);
      if (!mmTargetLocId && lRes[1]) setMmTargetLocId(lRes[1].id);

      if (["KIER_MAG", "MAG_WG", "FAKT_KS", "ADMIN"].includes(user.rola)) {
        const iList = await apiFetch<any[]>("/api/p4/inwentaryzacje");
        setInwentaryzacje(iList);
        const initSpis: Record<string, string> = {};
        for (const sheet of iList) {
          for (const pos of sheet.pozycje) {
            initSpis[pos.id] = pos.stan_spisany_kg ?? pos.stan_ewidencyjny_kg;
          }
        }
        setSpisValues(initSpis);
      }
      if (["KIER_MAG", "ADMIN"].includes(user.rola)) {
        apiFetch<any>("/api/p4/raport-rotacji").then(setRotacja).catch(() => {});
      }
    } catch (e: any) {
      setErr(e.message);
    }
  }

  useEffect(() => {
    loadAll();
  }, []);

  async function showTraceability(lotId: string) {
    setErr(null);
    try {
      const t = await apiFetch<any>(`/api/p4/partia/${lotId}/traceability`);
      setTrace(t);
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function executeMm(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setMsg(null);
    try {
      const res = await apiFetch<any>("/api/p4/mm", {
        method: "POST",
        body: JSON.stringify({
          partia_id: mmPartiaId,
          lokalizacja_docelowa_id: mmTargetLocId,
          ilosc_kg: mmQty,
          uwagi: mmUwagi,
        }),
      });
      setMsg(`Wykonano przesunięcie ${res.numer} (partia docelowa: ${res.partia_docelowa_kod}).`);
      await loadAll();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function startInventory() {
    setErr(null);
    setMsg(null);
    try {
      const res = await apiFetch<any>("/api/p4/inwentaryzacje", {
        method: "POST",
        body: JSON.stringify({ zakres_strefa: inwStrefa, komentarz: "Inwentaryzacja okresowa" }),
      });
      setMsg(`Otwarto arkusz ${res.numer} i zablokowano ruchy w strefie ${res.zakres_strefa}.`);
      await loadAll();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function saveCounts(sheet: any) {
    setErr(null);
    setMsg(null);
    try {
      await apiFetch(`/api/p4/inwentaryzacje/${sheet.id}/spis`, {
        method: "POST",
        body: JSON.stringify({
          pozycje: sheet.pozycje.map((p: any) => ({
            pozycja_id: p.id,
            stan_spisany_kg: spisValues[p.id] ?? p.stan_ewidencyjny_kg,
            podstawa_pomiaru: p.podstawa_pomiaru,
          })),
        }),
      });
      setMsg(`Zapisano wyniki spisu dla arkusza ${sheet.numer}.`);
      await loadAll();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function reconcileSheet(sheetId: string) {
    setErr(null);
    setMsg(null);
    try {
      const res = await apiFetch<any>(`/api/p4/inwentaryzacje/${sheetId}/rozlicz`, {
        method: "POST",
        body: JSON.stringify({ komentarz: inwKom }),
      });
      setMsg(
        `Rozliczono arkusz ${res.arkusz.numer} i zwolniono blokadę strefy. Dokumenty korygujące: ${
          res.dokumenty_korygujace.join(", ") || "brak różnic"
        }.`
      );
      await loadAll();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  const filteredLots = stany.filter((l) => {
    if (strefaFilter && l.lokalizacja_strefa !== strefaFilter) return false;
    if (searchQ) {
      const q = searchQ.toLowerCase();
      return (
        l.kod_partii.toLowerCase().includes(q) ||
        l.asortyment_nazwa.toLowerCase().includes(q) ||
        l.lokalizacja_kod.toLowerCase().includes(q)
      );
    }
    return true;
  });

  return (
    <div>
      {err && <div className="alert alert-error">{err}</div>}
      {msg && <div className="alert alert-success">{msg}</div>}

      <div className="card">
        <h2>Stany silosów i lokalizacji magazynowych (UC-05.2)</h2>
        <div className="grid-3">
          {lokalizacje.map((l) => {
            const occ = parseFloat(l.stan_zajety_kg || "0");
            const cap = parseFloat(l.pojemnosc_max_kg || "1");
            const pct = Math.min(100, Math.round((occ / cap) * 100));
            return (
              <div key={l.id} className="kpi-box">
                <div className="label">
                  {l.kod} ({l.typ}) {l.czy_zablokowana && <span className="badge badge-danger">BLOKADA INW.</span>}
                </div>
                <div style={{ fontWeight: 600, fontSize: "0.95rem" }}>{l.nazwa}</div>
                <div className="value" style={{ fontSize: "1.15rem" }}>
                  {occ.toLocaleString("pl-PL")} / {cap.toLocaleString("pl-PL")} kg ({pct}%)
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="card">
        <h3>Stany według partii i lokalizacji (kliknij „Traceability” dla pełnej historii)</h3>
        <div className="grid-2" style={{ marginBottom: 12 }}>
          <div className="form-row">
            <label>Filtr strefy</label>
            <select value={strefaFilter} onChange={(e) => setStrefaFilter(e.target.value)}>
              <option value="">Wszystkie strefy</option>
              <option value="SUROWCE">SUROWCE (Silosy)</option>
              <option value="BUFOR">BUFOR</option>
              <option value="WYROBY_GOTOWE">WYROBY_GOTOWE</option>
            </select>
          </div>
          <div className="form-row">
            <label>Szukaj po kodzie partii, towarze lub lokalizacji</label>
            <input type="text" value={searchQ} onChange={(e) => setSearchQ(e.target.value)} placeholder="np. LOT-WG lub PSZ" />
          </div>
        </div>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Partia</th>
                <th>Asortyment</th>
                <th>Lokalizacja</th>
                <th>Dostępne / Początkowe [kg]</th>
                <th>Ważność / Jakość</th>
                <th>Status</th>
                <th>Śledzenie</th>
              </tr>
            </thead>
            <tbody>
              {filteredLots.map((l) => (
                <tr key={l.id}>
                  <td><strong>{l.kod_partii}</strong></td>
                  <td>{l.asortyment_nazwa}</td>
                  <td>
                    {l.lokalizacja_kod}{" "}
                    {l.lokalizacja_zablokowana && <span className="badge badge-danger">BLOKADA</span>}
                  </td>
                  <td>
                    <strong>{l.masa_dostepna_kg}</strong> / {l.masa_poczatkowa_kg}
                  </td>
                  <td>
                    {l.data_waznosci ? (
                      <span className={l.czy_przeterminowana ? "badge badge-danger" : ""}>{l.data_waznosci}</span>
                    ) : (
                      `Wilg: ${l.wilgotnosc_pct || "-"}%`
                    )}
                  </td>
                  <td>
                    <span className={`badge ${l.status === "DOSTEPNA" ? "badge-ok" : "badge-warn"}`}>{l.status}</span>
                  </td>
                  <td>
                    <button type="button" className="btn btn-secondary btn-sm" onClick={() => showTraceability(l.id)}>
                      Traceability
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {trace && (
        <div className="card" style={{ borderColor: "#17365d", borderWidth: 2 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h3>Pełna identyfikowalność (Traceability): {trace.partia.kod_partii}</h3>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => setTrace(null)}>
              Zamknij
            </button>
          </div>
          <p>
            <strong>Asortyment:</strong> {trace.partia.asortyment} | <strong>Partia źródłowa surowca:</strong>{" "}
            {trace.pochodzenie_surowca.partia_zrodlowa_kod} | <strong>Dostawca:</strong>{" "}
            {trace.pochodzenie_surowca.dostawca || "-"}
            {trace.zlecenie_produkcyjne && (
              <>
                {" "}
                | <strong>Zlecenie:</strong> {trace.zlecenie_produkcyjne.numer} ({trace.zlecenie_produkcyjne.linia})
              </>
            )}
          </p>
          <div>
            <strong>Powiązane dokumenty:</strong>{" "}
            {trace.dokumenty.map((d: any) => `${d.typ} ${d.numer}`).join(" → ") || "brak"}
          </div>
        </div>
      )}

      {isManager && (
        <div className="grid-2">
          <div className="card">
            <h3>Przesunięcie międzymagazynowe MM (UC-05.4)</h3>
            <form onSubmit={executeMm}>
              <div className="form-row">
                <label>Partia źródłowa</label>
                <select value={mmPartiaId} onChange={(e) => setMmPartiaId(e.target.value)}>
                  {stany
                    .filter((s) => s.status === "DOSTEPNA" && parseFloat(s.masa_dostepna_kg) > 0)
                    .map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.kod_partii} ({s.lokalizacja_kod}, {s.masa_dostepna_kg} kg)
                      </option>
                    ))}
                </select>
              </div>
              <div className="form-row">
                <label>Lokalizacja docelowa</label>
                <select value={mmTargetLocId} onChange={(e) => setMmTargetLocId(e.target.value)}>
                  {lokalizacje.map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.kod} — {l.nazwa}
                    </option>
                  ))}
                </select>
              </div>
              <div className="form-row">
                <label>Ilość do przesunięcia [kg]</label>
                <input type="number" step="0.001" value={mmQty} onChange={(e) => setMmQty(e.target.value)} required />
              </div>
              <div className="form-row">
                <label>Uwagi</label>
                <input type="text" value={mmUwagi} onChange={(e) => setMmUwagi(e.target.value)} />
              </div>
              <button type="submit" className="btn btn-primary btn-sm">
                Zatwierdź przesunięcie MM
              </button>
            </form>
          </div>

          <div className="card">
            <h3>Nowa inwentaryzacja z blokadą strefy (UC-05.3)</h3>
            <div className="form-row">
              <label>Zakres inwentaryzacji (strefa)</label>
              <select value={inwStrefa} onChange={(e) => setInwStrefa(e.target.value)}>
                <option value="WYROBY_GOTOWE">WYROBY_GOTOWE (Regały paletowe)</option>
                <option value="SUROWCE">SUROWCE (Silosy)</option>
                <option value="BUFOR">BUFOR</option>
              </select>
            </div>
            <button type="button" className="btn btn-warn" onClick={startInventory}>
              Rozpocznij inwentaryzację i zablokuj strefę
            </button>
          </div>
        </div>
      )}

      {inwentaryzacje.length > 0 && (
        <div className="card">
          <h3>Arkusze inwentaryzacyjne</h3>
          {inwentaryzacje.map((sheet) => (
            <div key={sheet.id} className="card" style={{ background: "#f8fafc" }}>
              <h4>
                {sheet.numer} — strefa {sheet.zakres_strefa}{" "}
                <span className={`badge ${sheet.status === "OTWARTA" ? "badge-warn" : "badge-ok"}`}>{sheet.status}</span>
              </h4>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Lokalizacja</th>
                      <th>Partia</th>
                      <th>Asortyment</th>
                      <th>Stan ewidencyjny [kg]</th>
                      <th>Spis z natury [kg]</th>
                      <th>Różnica [kg]</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sheet.pozycje.map((p: any) => (
                      <tr key={p.id}>
                        <td>{p.lokalizacja_kod}</td>
                        <td>{p.kod_partii}</td>
                        <td>{p.asortyment_nazwa}</td>
                        <td>{p.stan_ewidencyjny_kg}</td>
                        <td>
                          {sheet.status === "OTWARTA" && canCount ? (
                            <input
                              type="number"
                              step="0.001"
                              style={{ width: 140, minHeight: 38 }}
                              value={spisValues[p.id] ?? ""}
                              onChange={(e) => setSpisValues((prev) => ({ ...prev, [p.id]: e.target.value }))}
                            />
                          ) : (
                            p.stan_spisany_kg || "-"
                          )}
                        </td>
                        <td>{p.roznica_kg ?? "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {sheet.status === "OTWARTA" && (
                <div style={{ marginTop: 12 }}>
                  <div className="tabs">
                    {canCount && (
                      <button type="button" className="btn btn-secondary btn-sm" onClick={() => saveCounts(sheet)}>
                        Zapisz spis z natury
                      </button>
                    )}
                    {isManager && (
                      <>
                        <input
                          type="text"
                          style={{ maxWidth: 280, minHeight: 40 }}
                          value={inwKom}
                          onChange={(e) => setInwKom(e.target.value)}
                          placeholder="Komentarz rozliczenia"
                        />
                        <button type="button" className="btn btn-primary btn-sm" onClick={() => reconcileSheet(sheet.id)}>
                          Rozlicz różnice (PW-kor/RW-kor) i odblokuj
                        </button>
                      </>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {rotacja && (
        <div className="card">
          <h3>Raport stanów i rotacji zapasów (UC-05.1 — bez transferów MM)</h3>
          <p style={{ color: "#475569", marginTop: 0 }}>
            Stan na dzień: <strong>{rotacja.na_dzien}</strong> | Okres: <strong>{rotacja.okres_rotacji}</strong>
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Kod</th>
                  <th>Asortyment</th>
                  <th>Stan [kg]</th>
                  <th>Wartość netto</th>
                  <th>Rozchód w okresie [kg]</th>
                  <th>Rotacja</th>
                </tr>
              </thead>
              <tbody>
                {rotacja.pozycje.map((r: any) => (
                  <tr key={r.asortyment_id}>
                    <td>{r.kod}</td>
                    <td>{r.nazwa}</td>
                    <td>{r.stan_kg}</td>
                    <td>{r.wartosc_netto_pln} PLN</td>
                    <td>{r.rozchod_okres_kg}</td>
                    <td>{r.rotacja}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
