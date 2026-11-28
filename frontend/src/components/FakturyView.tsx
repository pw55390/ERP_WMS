import React, { useEffect, useState } from "react";
import { apiFetch, openAuthenticatedPdf, UserInfo } from "../api/client";

export const FakturyView: React.FC<{ user: UserInfo }> = ({ user }) => {
  const [faktury, setFaktury] = useState<any[]>([]);
  const [wzs, setWzs] = useState<any[]>([]);
  const [cenniki, setCenniki] = useState<any[]>([]);
  const [kontrahenci, setKontrahenci] = useState<any[]>([]);
  const [asortyment, setAsortyment] = useState<any[]>([]);

  const [selectedWzIds, setSelectedWzIds] = useState<string[]>([]);
  const [overridePrice, setOverridePrice] = useState("");
  const [overrideReason, setOverrideReason] = useState("");
  const [overrideItemId, setOverrideItemId] = useState("");

  // Cennik
  const [priceBuyerId, setPriceBuyerId] = useState("");
  const [priceItemId, setPriceItemId] = useState("");
  const [priceVal, setPriceVal] = useState("2.250");

  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const isFakt = user.rola === "FAKT_KS";

  async function loadAll() {
    try {
      const [fList, wList, cList, kList, aList] = await Promise.all([
        apiFetch<any[]>("/api/p3/faktury"),
        apiFetch<any[]>("/api/p3/wz"),
        apiFetch<any[]>("/api/cenniki"),
        apiFetch<any[]>("/api/kontrahenci"),
        apiFetch<any[]>("/api/asortyment"),
      ]);
      setFaktury(fList);
      setWzs(wList.filter((w) => w.status === "ZATWIERDZONY" && !w.czy_zafakturowany));
      setCenniki(cList);
      setKontrahenci(kList);
      setAsortyment(aList);
      const buyer = kList.find((k) => k.typ === "ODBIORCA" || k.typ === "OBA");
      const wg = aList.find((a) => a.kategoria === "WYROB_GOTOWY");
      if (!priceBuyerId && buyer) setPriceBuyerId(buyer.id);
      if (!priceItemId && wg) setPriceItemId(wg.id);
      if (!overrideItemId && wg) setOverrideItemId(wg.id);
    } catch (e: any) {
      setErr(e.message);
    }
  }

  useEffect(() => {
    loadAll();
  }, []);

  async function createFs(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setMsg(null);
    if (selectedWzIds.length === 0) {
      setErr("Wybierz co najmniej jeden niezafakturowany dokument WZ.");
      return;
    }
    const overrides =
      overridePrice && overrideReason
        ? [{ asortyment_id: overrideItemId, nowa_cena_netto: overridePrice, powod_zmiany: overrideReason }]
        : [];
    try {
      const res = await apiFetch<any>("/api/p3/faktury/z-wz", {
        method: "POST",
        body: JSON.stringify({
          wz_ids: selectedWzIds,
          nadpisania_cen: overrides,
        }),
      });
      setMsg(`Wystawiono fakturę ${res.numer} na kwotę brutto ${res.wartosc_brutto} PLN.`);
      setSelectedWzIds([]);
      setOverridePrice("");
      setOverrideReason("");
      await loadAll();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function updatePricelist(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setMsg(null);
    try {
      await apiFetch("/api/cenniki", {
        method: "POST",
        body: JSON.stringify({
          kontrahent_id: priceBuyerId,
          asortyment_id: priceItemId,
          cena_netto: priceVal,
        }),
      });
      setMsg("Zaktualizowano cennik kontrahenta (zapisano w audycie).");
      await loadAll();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  return (
    <div>
      {err && <div className="alert alert-error">{err}</div>}
      {msg && <div className="alert alert-success">{msg}</div>}

      {isFakt && (
        <div className="grid-2">
          <div className="card">
            <h2>Wystawienie faktury VAT (FS) z WZ (UC-04.1 / UC-04.2)</h2>
            <form onSubmit={createFs}>
              <div className="form-row">
                <label>Niezafakturowane zatwierdzone dokumenty WZ (wybierz jednego odbiorcę)</label>
                {wzs.length === 0 ? (
                  <div className="alert alert-info">Brak dokumentów WZ oczekujących na zafakturowanie.</div>
                ) : (
                  wzs.map((w) => (
                    <label key={w.id} style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 500 }}>
                      <input
                        type="checkbox"
                        style={{ width: 20, height: 20 }}
                        checked={selectedWzIds.includes(w.id)}
                        onChange={(e) =>
                          setSelectedWzIds((prev) =>
                            e.target.checked ? [...prev, w.id] : prev.filter((x) => x !== w.id)
                          )
                        }
                      />
                      {w.numer} — {w.kontrahent_nazwa} ({w.pozycje.map((p: any) => `${p.asortyment_nazwa}: ${p.ilosc_kg} kg`).join(", ")})
                    </label>
                  ))
                )}
              </div>

              <div className="card" style={{ background: "#f8fafc" }}>
                <h4>Opcjonalna ręczna zmiana ceny (tylko FAKT_KS, audytowana)</h4>
                <div className="grid-3">
                  <div className="form-row">
                    <label>Asortyment</label>
                    <select value={overrideItemId} onChange={(e) => setOverrideItemId(e.target.value)}>
                      {asortyment
                        .filter((a) => a.kategoria !== "SUROWIEC")
                        .map((a) => (
                          <option key={a.id} value={a.id}>
                            {a.nazwa}
                          </option>
                        ))}
                    </select>
                  </div>
                  <div className="form-row">
                    <label>Nowa cena netto [PLN/kg]</label>
                    <input
                      type="number"
                      step="0.001"
                      value={overridePrice}
                      onChange={(e) => setOverridePrice(e.target.value)}
                      placeholder="Pozostaw puste = cena z cennika"
                    />
                  </div>
                  <div className="form-row">
                    <label>Przyczyna zmiany ceny</label>
                    <input
                      type="text"
                      value={overrideReason}
                      onChange={(e) => setOverrideReason(e.target.value)}
                      placeholder="np. Rabat kontraktowy"
                    />
                  </div>
                </div>
              </div>

              <button type="submit" className="btn btn-primary" disabled={wzs.length === 0}>
                Wystaw i zatwierdź fakturę FS
              </button>
            </form>
          </div>

          <div className="card">
            <h2>Cenniki kontrahentów</h2>
            <form onSubmit={updatePricelist}>
              <div className="grid-3">
                <div className="form-row">
                  <label>Odbiorca</label>
                  <select value={priceBuyerId} onChange={(e) => setPriceBuyerId(e.target.value)}>
                    {kontrahenci
                      .filter((k) => k.typ === "ODBIORCA" || k.typ === "OBA")
                      .map((k) => (
                        <option key={k.id} value={k.id}>
                          {k.nazwa}
                        </option>
                      ))}
                  </select>
                </div>
                <div className="form-row">
                  <label>Wyrób</label>
                  <select value={priceItemId} onChange={(e) => setPriceItemId(e.target.value)}>
                    {asortyment
                      .filter((a) => a.kategoria !== "SUROWIEC")
                      .map((a) => (
                        <option key={a.id} value={a.id}>
                          {a.nazwa}
                        </option>
                      ))}
                  </select>
                </div>
                <div className="form-row">
                  <label>Cena netto [PLN/kg]</label>
                  <input type="number" step="0.001" value={priceVal} onChange={(e) => setPriceVal(e.target.value)} required />
                </div>
              </div>
              <button type="submit" className="btn btn-secondary btn-sm">
                Zapisz cenę w cenniku
              </button>
            </form>

            <div className="table-wrap" style={{ marginTop: 12 }}>
              <table>
                <thead>
                  <tr>
                    <th>Kontrahent</th>
                    <th>Asortyment</th>
                    <th>Cena netto</th>
                  </tr>
                </thead>
                <tbody>
                  {cenniki.map((c) => (
                    <tr key={c.id}>
                      <td>{c.kontrahent_nazwa}</td>
                      <td>{c.asortyment_nazwa}</td>
                      <td><strong>{c.cena_netto} {c.waluta}</strong></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      <div className="card">
        <h3>Rejestr faktur VAT (FS, FZ, FS-KOR)</h3>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Numer / Typ</th>
                <th>Kontrahent</th>
                <th>Data / Termin</th>
                <th>Netto</th>
                <th>VAT</th>
                <th>Brutto</th>
                <th>Wydruki</th>
                <th>PDF</th>
              </tr>
            </thead>
            <tbody>
              {faktury.length === 0 ? (
                <tr>
                  <td colSpan={8}>Brak wystawionych faktur.</td>
                </tr>
              ) : (
                faktury.map((f) => (
                  <tr key={f.id}>
                    <td>
                      <strong>{f.numer}</strong> <span className="badge badge-info">{f.typ}</span>
                    </td>
                    <td>
                      {f.kontrahent_nazwa}
                      <br />
                      <small>NIP: {f.kontrahent_nip}</small>
                    </td>
                    <td>
                      {f.data_wystawienia}
                      <br />
                      <small>Termin: {f.termin_platnosci}</small>
                    </td>
                    <td>{f.wartosc_netto} PLN</td>
                    <td>{f.wartosc_vat} PLN</td>
                    <td><strong>{f.wartosc_brutto} PLN</strong></td>
                    <td>{f.liczba_wydrukow}</td>
                    <td>
                      <button
                        type="button"
                        className="btn btn-primary btn-sm"
                        onClick={() => openAuthenticatedPdf(`/api/p3/faktury/${f.id}/pdf`, `${f.numer}.pdf`)}
                      >
                        Pobierz PDF
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
