import React, { useEffect, useState } from "react";
import { apiFetch, openAuthenticatedPdf, UserInfo } from "../api/client";

export const P3SprzedazView: React.FC<{ user: UserInfo }> = ({ user }) => {
  const [orders, setOrders] = useState<any[]>([]);
  const [wzs, setWzs] = useState<any[]>([]);
  const [buyers, setBuyers] = useState<any[]>([]);
  const [wgItems, setWgItems] = useState<any[]>([]);

  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  // Nowe zamówienie
  const [buyerId, setBuyerId] = useState("");
  const [itemId, setItemId] = useState("");
  const [qtyKg, setQtyKg] = useState("1000");
  const [shipDate, setShipDate] = useState(() => new Date().toISOString().slice(0, 10));

  // Kompletacja FEFO
  const [activeOrder, setActiveOrder] = useState<any | null>(null);
  const [fefo, setFefo] = useState<any | null>(null);
  const [scanCode, setScanCode] = useState("");
  const [pickedLines, setPickedLines] = useState<Array<{ asortyment_id: string; partia_id: string; kod_partii: string; ilosc_kg: string }>>([]);
  const [nrRej, setNrRej] = useState("DW 5500P");

  const canPick = ["MAG_WG", "KIER_MAG"].includes(user.rola);
  const canCreateOrder = ["FAKT_KS", "KIER_MAG", "MAG_WG"].includes(user.rola);

  async function loadAll() {
    try {
      const [oList, wList, bList, iList] = await Promise.all([
        apiFetch<any[]>("/api/p3/zamowienia"),
        apiFetch<any[]>("/api/p3/wz"),
        apiFetch<any[]>("/api/kontrahenci?typ=ODBIORCA"),
        apiFetch<any[]>("/api/asortyment"),
      ]);
      setOrders(oList);
      setWzs(wList);
      setBuyers(bList);
      const wg = iList.filter((i) => i.kategoria === "WYROB_GOTOWY" || i.kategoria === "PRODUKT_UBOCZNY");
      setWgItems(wg);
      if (!buyerId && bList[0]) setBuyerId(bList[0].id);
      if (!itemId && wg[0]) setItemId(wg[0].id);
    } catch (e: any) {
      setErr(e.message);
    }
  }

  useEffect(() => {
    loadAll();
  }, []);

  async function createOrder(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setMsg(null);
    try {
      const res = await apiFetch<any>("/api/p3/zamowienia", {
        method: "POST",
        body: JSON.stringify({
          odbiorca_id: buyerId,
          data_wydania: shipDate,
          pozycje: [{ asortyment_id: itemId, ilosc_zamowiona_kg: qtyKg }],
        }),
      });
      setMsg(`Utworzono zamówienie ${res.numer} z ceną z cennika odbiorcy.`);
      await loadAll();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function openPicking(order: any) {
    setErr(null);
    setMsg(null);
    setActiveOrder(order);
    setPickedLines([]);
    try {
      const f = await apiFetch<any>(`/api/p3/zamowienia/${order.id}/podpowiedz-fefo`);
      setFefo(f);
    } catch (e: any) {
      setErr(e.message);
    }
  }

  function addPick(asortymentId: string, lot: any, qtyStr?: string) {
    setErr(null);
    const qty = qtyStr || lot.sugerowana_ilosc_kg || lot.masa_dostepna_kg;
    if (parseFloat(qty) <= 0) return;
    setPickedLines((prev) => [
      ...prev.filter((p) => p.partia_id !== lot.partia_id),
      { asortyment_id: asortymentId, partia_id: lot.partia_id, kod_partii: lot.kod_partii, ilosc_kg: qty },
    ]);
  }

  // Obsługa skanera kodów kreskowych (klawiatura emulowana + Enter)
  function handleBarcodeScan(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key !== "Enter") return;
    e.preventDefault();
    if (!fefo || !scanCode.trim()) return;
    const code = scanCode.trim();
    for (const pos of fefo.pozycje) {
      const matchOk = pos.dostepne_fefo.find((l: any) => l.kod_partii === code);
      if (matchOk) {
        addPick(pos.asortyment_id, matchOk);
        setMsg(`Zeskanowano partię FEFO: ${code}`);
        setScanCode("");
        return;
      }
      const matchBlocked = pos.zablokowane_partie.find((l: any) => l.kod_partii === code);
      if (matchBlocked) {
        addPick(pos.asortyment_id, matchBlocked, "100.000");
        setErr(`UWAGA: Partia ${code} jest oznaczona jako zablokowana/przeterminowana — zatwierdzenie WZ zostanie odrzucone przez serwer.`);
        setScanCode("");
        return;
      }
    }
    setErr(`Nie znaleziono partii o kodzie '${code}' dla tego zamówienia.`);
  }

  async function submitWz() {
    if (!activeOrder || pickedLines.length === 0) return;
    setErr(null);
    setMsg(null);
    try {
      const res = await apiFetch<any>("/api/p3/wz/kompletuj-i-zatwierdz", {
        method: "POST",
        body: JSON.stringify({
          zamowienie_id: activeOrder.id,
          data_wydania: activeOrder.data_wydania,
          nr_rejestracyjny: nrRej,
          pozycje: pickedLines.map((p) => ({
            asortyment_id: p.asortyment_id,
            partia_id: p.partia_id,
            ilosc_kg: p.ilosc_kg,
          })),
        }),
      });
      setMsg(`Wystawiono i zatwierdzono dokument ${res.numer}. Stany magazynowe zaktualizowane atomowo.`);
      setActiveOrder(null);
      setFefo(null);
      setPickedLines([]);
      await loadAll();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  return (
    <div>
      {err && <div className="alert alert-error">{err}</div>}
      {msg && <div className="alert alert-success">{msg}</div>}

      {canCreateOrder && (
        <div className="card">
          <h2>Nowe zamówienie sprzedaży</h2>
          <form onSubmit={createOrder}>
            <div className="grid-3">
              <div className="form-row">
                <label>Odbiorca</label>
                <select value={buyerId} onChange={(e) => setBuyerId(e.target.value)}>
                  {buyers.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.nazwa}
                    </option>
                  ))}
                </select>
              </div>
              <div className="form-row">
                <label>Wyrób gotowy</label>
                <select value={itemId} onChange={(e) => setItemId(e.target.value)}>
                  {wgItems.map((i) => (
                    <option key={i.id} value={i.id}>
                      {i.nazwa}
                    </option>
                  ))}
                </select>
              </div>
              <div className="form-row">
                <label>Ilość [kg]</label>
                <input type="number" step="0.001" value={qtyKg} onChange={(e) => setQtyKg(e.target.value)} required />
              </div>
              <div className="form-row">
                <label>Planowana data wydania</label>
                <input type="date" value={shipDate} onChange={(e) => setShipDate(e.target.value)} required />
              </div>
            </div>
            <button type="submit" className="btn btn-primary btn-sm">
              Utwórz zamówienie (cena z cennika)
            </button>
          </form>
        </div>
      )}

      {activeOrder && fefo && canPick && (
        <div className="card" style={{ borderColor: "#17365d", borderWidth: 2 }}>
          <h3>Kompletacja FEFO i WZ dla zamówienia {activeOrder.numer} ({activeOrder.odbiorca_nazwa})</h3>
          <div className="grid-2">
            <div className="form-row">
              <label>Skaner kodów kreskowych (wpisz kod partii i naciśnij Enter)</label>
              <input
                type="text"
                value={scanCode}
                onChange={(e) => setScanCode(e.target.value)}
                onKeyDown={handleBarcodeScan}
                placeholder="np. LOT-WG-2026-0001 lub LOT-WG-2026-EXP1"
              />
            </div>
            <div className="form-row">
              <label>Nr rejestracyjny pojazdu odbiorcy</label>
              <input type="text" value={nrRej} onChange={(e) => setNrRej(e.target.value)} />
            </div>
          </div>

          {fefo.pozycje.map((pos: any) => (
            <div key={pos.asortyment_id} className="card" style={{ background: "#f8fafc" }}>
              <h4>
                {pos.asortyment_nazwa} — pozostało do wydania: <strong>{pos.pozostalo_do_wydania_kg} kg</strong>
              </h4>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>Dostępne partie wg kolejności FEFO:</div>
              <div className="tabs">
                {pos.dostepne_fefo.map((lot: any, idx: number) => (
                  <button
                    key={lot.partia_id}
                    type="button"
                    className={`btn btn-sm ${idx === 0 ? "btn-primary" : "btn-secondary"}`}
                    onClick={() => addPick(pos.asortyment_id, lot)}
                  >
                    + {lot.kod_partii} ({lot.lokalizacja_kod}, ważna do: {lot.data_waznosci}, stan: {lot.masa_dostepna_kg} kg)
                  </button>
                ))}
              </div>

              {pos.zablokowane_partie.length > 0 && (
                <div style={{ marginTop: 10 }}>
                  <div style={{ fontWeight: 600, color: "#991b1b", marginBottom: 6 }}>
                    Partie przeterminowane / zablokowane (RF-03.3 — twarda blokada po stronie serwera):
                  </div>
                  <div className="tabs">
                    {pos.zablokowane_partie.map((lot: any) => (
                      <button
                        key={lot.partia_id}
                        type="button"
                        className="btn btn-danger btn-sm"
                        onClick={() => addPick(pos.asortyment_id, lot, "100.000")}
                        title={lot.powod_blokady}
                      >
                        Testuj blokadę: {lot.kod_partii} (ważna do: {lot.data_waznosci})
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}

          {pickedLines.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <strong>Wybrane partie do WZ:</strong>
              <ul>
                {pickedLines.map((pl) => (
                  <li key={pl.partia_id}>
                    {pl.kod_partii}:{" "}
                    <input
                      type="number"
                      step="0.001"
                      style={{ width: 140, display: "inline-block", minHeight: 36 }}
                      value={pl.ilosc_kg}
                      onChange={(e) =>
                        setPickedLines((prev) =>
                          prev.map((x) => (x.partia_id === pl.partia_id ? { ...x, ilosc_kg: e.target.value } : x))
                        )
                      }
                    />{" "}
                    kg
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="tabs">
            <button type="button" className="btn btn-primary" disabled={pickedLines.length === 0} onClick={submitWz}>
              Zatwierdź kompletację i wystaw WZ
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => setActiveOrder(null)}>
              Zamknij
            </button>
          </div>
        </div>
      )}

      <div className="card">
        <h3>Zamówienia sprzedaży</h3>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Numer</th>
                <th>Odbiorca</th>
                <th>Data wydania</th>
                <th>Pozycje i ceny (cennik)</th>
                <th>Status</th>
                <th>Akcja</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o) => (
                <tr key={o.id}>
                  <td><strong>{o.numer}</strong></td>
                  <td>{o.odbiorca_nazwa}</td>
                  <td>{o.data_wydania}</td>
                  <td>
                    {o.pozycje.map((p: any) => (
                      <div key={p.id}>
                        {p.asortyment_nazwa}: {p.ilosc_wydana_kg}/{p.ilosc_zamowiona_kg} kg ({p.cena_netto} PLN/kg{" "}
                        {p.cena_z_cennika ? "cennik" : "bazowa"})
                      </div>
                    ))}
                  </td>
                  <td>
                    <span className={`badge ${o.status === "ZREALIZOWANE" ? "badge-ok" : "badge-info"}`}>{o.status}</span>
                  </td>
                  <td>
                    {o.status !== "ZREALIZOWANE" && canPick ? (
                      <button type="button" className="btn btn-primary btn-sm" onClick={() => openPicking(o)}>
                        Kompletuj FEFO / WZ
                      </button>
                    ) : (
                      "-"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <h3>Dokumenty Wydania Zewnętrznego (WZ)</h3>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Numer WZ</th>
                <th>Odbiorca</th>
                <th>Data wydania</th>
                <th>Partie i ilości</th>
                <th>Zafakturowany</th>
                <th>Wydruk</th>
              </tr>
            </thead>
            <tbody>
              {wzs.map((w) => (
                <tr key={w.id}>
                  <td><strong>{w.numer}</strong></td>
                  <td>{w.kontrahent_nazwa}</td>
                  <td>{w.data_wydania || "-"}</td>
                  <td>
                    {w.pozycje.map((p: any) => (
                      <div key={p.id}>
                        {p.asortyment_nazwa} — {p.kod_partii} ({p.ilosc_kg} kg)
                      </div>
                    ))}
                  </td>
                  <td>{w.czy_zafakturowany ? <span className="badge badge-ok">TAK</span> : <span className="badge badge-warn">NIE</span>}</td>
                  <td>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => openAuthenticatedPdf(`/api/dokumenty/${w.id}/pdf`, `${w.numer}.pdf`)}
                    >
                      PDF WZ
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
