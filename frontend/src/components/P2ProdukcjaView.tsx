import React, { useEffect, useState } from "react";
import { apiFetch, UserInfo } from "../api/client";

export const P2ProdukcjaView: React.FC<{ user: UserInfo }> = ({ user }) => {
  const [boms, setBoms] = useState<any[]>([]);
  const [orders, setOrders] = useState<any[]>([]);
  const [rawLots, setRawLots] = useState<any[]>([]);
  const [wgLocs, setWgLocs] = useState<any[]>([]);
  const [items, setItems] = useState<any[]>([]);
  const [yieldReport, setYieldReport] = useState<any[]>([]);

  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  // Nowy BOM
  const [showNewBom, setShowNewBom] = useState(false);
  const [bomKod, setBomKod] = useState("BOM-M500");
  const [bomNazwa, setBomNazwa] = useState("Przemiał pszenicy typ 500 v2");
  const [bomTargetId, setBomTargetId] = useState("");
  const [bomRawId, setBomRawId] = useState("");
  const [bomLossPct, setBomLossPct] = useState("2.0");

  // Nowe zlecenie
  const [selectedBomId, setSelectedBomId] = useState("");
  const [selectedLotId, setSelectedLotId] = useState("");
  const [zasypKg, setZasypKg] = useState("5000");
  const [linia, setLinia] = useState("Linia Młynarska L1");

  // Rozliczenie PW
  const [settleOrderId, setSettleOrderId] = useState<string | null>(null);
  const [mainYieldKg, setMainYieldKg] = useState("3750");
  const [branYieldKg, setBranYieldKg] = useState("1150");
  const [odsiewKg, setOdsiewKg] = useState("60");
  const [wilgLossKg, setWilgLossKg] = useState("40");
  const [targetLocId, setTargetLocId] = useState("");
  const [expDate, setExpDate] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() + 180);
    return d.toISOString().slice(0, 10);
  });
  const [powodStraty, setPowodStraty] = useState("");
  const [kierKomentarz, setKierKomentarz] = useState("Akceptacja technologiczna straty");

  const canProduce = ["INZ_PROD", "KIER_MAG"].includes(user.rola);
  const isEngineer = user.rola === "INZ_PROD";
  const isManager = user.rola === "KIER_MAG";

  async function loadAll() {
    try {
      const [bomList, ordList, lotRes, locList, itemList, repList] = await Promise.all([
        apiFetch<any[]>("/api/p2/receptury"),
        apiFetch<any[]>("/api/p2/zlecenia"),
        apiFetch<{ partie: any[] }>("/api/p4/stany?strefa=SUROWCE&tylko_dostepne=true"),
        apiFetch<any[]>("/api/lokalizacje?strefa=WYROBY_GOTOWE"),
        apiFetch<any[]>("/api/asortyment"),
        apiFetch<any[]>("/api/p2/raport-wydajnosci"),
      ]);
      setBoms(bomList);
      setOrders(ordList);
      setRawLots(lotRes.partie.filter((l) => l.status === "DOSTEPNA"));
      setWgLocs(locList);
      setItems(itemList);
      setYieldReport(repList);

      const activeBom = bomList.find((b) => b.status === "AKTYWNA");
      if (!selectedBomId && activeBom) setSelectedBomId(activeBom.id);
      if (!selectedLotId && lotRes.partie[0]) setSelectedLotId(lotRes.partie[0].id);
      if (!targetLocId && locList[0]) setTargetLocId(locList[0].id);
      const wgItem = itemList.find((i) => i.kategoria === "WYROB_GOTOWY");
      const rawItem = itemList.find((i) => i.kategoria === "SUROWIEC");
      if (!bomTargetId && wgItem) setBomTargetId(wgItem.id);
      if (!bomRawId && rawItem) setBomRawId(rawItem.id);
    } catch (e: any) {
      setErr(e.message);
    }
  }

  useEffect(() => {
    loadAll();
  }, []);

  async function createBom(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setMsg(null);
    try {
      const res = await apiFetch<any>("/api/p2/receptury", {
        method: "POST",
        body: JSON.stringify({
          kod: bomKod,
          nazwa: bomNazwa,
          wyrob_docelowy_id: bomTargetId,
          normatyw_strat_pct: bomLossPct,
          skladniki: [{ asortyment_id: bomRawId, typ_skladnika: "SUROWIEC", udzial_procentowy: "100.000" }],
        }),
      });
      setMsg(`Utworzono recepturę ${res.kod} wersja v${res.wersja} (poprzednie aktywne wersje zarchiwizowano).`);
      setShowNewBom(false);
      await loadAll();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function createOrder(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setMsg(null);
    try {
      const res = await apiFetch<any>("/api/p2/zlecenia", {
        method: "POST",
        body: JSON.stringify({
          receptura_id: selectedBomId,
          linia_przemialowa: linia,
          planowany_zasyp_kg: zasypKg,
          partia_surowca_id: selectedLotId,
        }),
      });
      setMsg(`Utworzono zlecenie ${res.numer} i automatycznie zatwierdzono rozchód RW (${res.ilosc_rw_kg} kg).`);
      setSettleOrderId(res.id);
      await loadAll();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function settleOrder(e: React.FormEvent) {
    e.preventDefault();
    if (!settleOrderId) return;
    setErr(null);
    setMsg(null);
    const branItem = items.find((i) => i.kategoria === "PRODUKT_UBOCZNY");
    try {
      const byProducts =
        branItem && parseFloat(branYieldKg) > 0
          ? [{ asortyment_id: branItem.id, lokalizacja_id: targetLocId, ilosc_kg: branYieldKg, data_waznosci: expDate }]
          : [];
      const res = await apiFetch<any>(`/api/p2/zlecenia/${settleOrderId}/rozlicz-pw`, {
        method: "POST",
        body: JSON.stringify({
          wyrob_glowny_kg: mainYieldKg,
          lokalizacja_docelowa_id: targetLocId,
          data_waznosci_wyrobu: expDate,
          produkty_uboczne: byProducts,
          strata_odsiew_kg: odsiewKg,
          strata_wilgotnosc_kg: wilgLossKg,
          powod_straty: powodStraty || null,
        }),
      });
      if (res.status === "WSTRZYMANE_DO_AKCEPTACJI") {
        setMsg(`Zlecenie ${res.numer} ma stratę >3% i zostało wstrzymane do akceptacji KIER_MAG.`);
      } else {
        setMsg(`Zlecenie ${res.numer} rozliczone! Wystawiono dokument PW i utworzono nowe partie wyrobów.`);
      }
      setSettleOrderId(null);
      await loadAll();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function managerLossDecision(id: string, accept: boolean) {
    setErr(null);
    setMsg(null);
    try {
      await apiFetch(`/api/p2/zlecenia/${id}/akceptuj-strate`, {
        method: "POST",
        body: JSON.stringify({ akceptuj: accept, komentarz: kierKomentarz }),
      });
      setMsg(accept ? "Kierownik zaakceptował stratę i zatwierdził PW." : "Kierownik zwrócił zlecenie do weryfikacji mas.");
      await loadAll();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  const settleOrderObj = orders.find((o) => o.id === settleOrderId) || null;
  const activeBoms = boms.filter((b) => b.status === "AKTYWNA");

  // Podgląd bilansu w czasie rzeczywistym przed wysłaniem
  let previewDiffInfo = "";
  if (settleOrderObj) {
    const rw = parseFloat(settleOrderObj.ilosc_rw_kg || "0");
    const out =
      (parseFloat(mainYieldKg || "0") || 0) +
      (parseFloat(branYieldKg || "0") || 0) +
      (parseFloat(odsiewKg || "0") || 0) +
      (parseFloat(wilgLossKg || "0") || 0);
    const diff = Math.abs(rw - out);
    const pct = rw > 0 ? (diff / rw) * 100 : 0;
    previewDiffInfo = `RW: ${rw.toFixed(3)} kg | Suma (PW + uboczne + strata): ${out.toFixed(3)} kg | Różnica: ${diff.toFixed(3)} kg (${pct.toFixed(3)}%)`;
  }

  return (
    <div>
      {err && <div className="alert alert-error">{err}</div>}
      {msg && <div className="alert alert-success">{msg}</div>}

      {isEngineer && (
        <div className="card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
            <h2 style={{ margin: 0 }}>Receptury przemiałowe BOM</h2>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => setShowNewBom((v) => !v)}>
              {showNewBom ? "Zamknij" : "+ Nowa wersja BOM"}
            </button>
          </div>
          {showNewBom && (
            <form onSubmit={createBom} style={{ marginTop: 14 }}>
              <div className="grid-3">
                <div className="form-row">
                  <label>Kod receptury</label>
                  <input type="text" value={bomKod} onChange={(e) => setBomKod(e.target.value)} required />
                </div>
                <div className="form-row">
                  <label>Nazwa receptury</label>
                  <input type="text" value={bomNazwa} onChange={(e) => setBomNazwa(e.target.value)} required />
                </div>
                <div className="form-row">
                  <label>Normatyw strat [%]</label>
                  <input type="number" step="0.1" value={bomLossPct} onChange={(e) => setBomLossPct(e.target.value)} required />
                </div>
                <div className="form-row">
                  <label>Wyrób docelowy</label>
                  <select value={bomTargetId} onChange={(e) => setBomTargetId(e.target.value)}>
                    {items
                      .filter((i) => i.kategoria === "WYROB_GOTOWY")
                      .map((i) => (
                        <option key={i.id} value={i.id}>
                          {i.nazwa}
                        </option>
                      ))}
                  </select>
                </div>
                <div className="form-row">
                  <label>Surowiec główny (100%)</label>
                  <select value={bomRawId} onChange={(e) => setBomRawId(e.target.value)}>
                    {items
                      .filter((i) => i.kategoria === "SUROWIEC")
                      .map((i) => (
                        <option key={i.id} value={i.id}>
                          {i.nazwa}
                        </option>
                      ))}
                  </select>
                </div>
              </div>
              <button type="submit" className="btn btn-primary btn-sm">
                Zapisz i aktywuj nową wersję BOM
              </button>
            </form>
          )}
        </div>
      )}

      {canProduce && (
        <div className="card">
          <h2>Nowe zlecenie produkcyjne i rozchód RW (UC-02.2)</h2>
          <form onSubmit={createOrder}>
            <div className="grid-2">
              <div className="form-row">
                <label>Aktywna receptura BOM</label>
                <select value={selectedBomId} onChange={(e) => setSelectedBomId(e.target.value)} required>
                  {activeBoms.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.kod} v{b.wersja} — {b.wyrob_docelowy_nazwa} (norma strat: {b.normatyw_strat_pct}%)
                    </option>
                  ))}
                </select>
              </div>
              <div className="form-row">
                <label>Partia surowca (silos)</label>
                <select value={selectedLotId} onChange={(e) => setSelectedLotId(e.target.value)} required>
                  {rawLots.map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.kod_partii} | {l.lokalizacja_kod} | dostępne: {l.masa_dostepna_kg} kg (wilg: {l.wilgotnosc_pct}%)
                    </option>
                  ))}
                </select>
              </div>
              <div className="form-row">
                <label>Planowana wielkość zasypu [kg]</label>
                <input type="number" step="0.001" value={zasypKg} onChange={(e) => setZasypKg(e.target.value)} required />
              </div>
              <div className="form-row">
                <label>Linia przemiałowa</label>
                <input type="text" value={linia} onChange={(e) => setLinia(e.target.value)} required />
              </div>
            </div>
            <button type="submit" className="btn btn-primary" disabled={!selectedBomId || !selectedLotId}>
              Utwórz zlecenie i zatwierdź RW
            </button>
          </form>
        </div>
      )}

      {settleOrderObj && canProduce && (
        <div className="card" style={{ borderColor: "#17365d", borderWidth: 2 }}>
          <h3>Rozliczenie uzysku PW i bilansu masowego — {settleOrderObj.numer}</h3>
          <div className="alert alert-info">{previewDiffInfo}</div>
          <form onSubmit={settleOrder}>
            <div className="grid-3">
              <div className="form-row">
                <label>Wyrób główny ({settleOrderObj.wyrob_docelowy_nazwa}) [kg]</label>
                <input type="number" step="0.001" value={mainYieldKg} onChange={(e) => setMainYieldKg(e.target.value)} required />
              </div>
              <div className="form-row">
                <label>Produkt uboczny (Otręby pszenne) [kg]</label>
                <input type="number" step="0.001" value={branYieldKg} onChange={(e) => setBranYieldKg(e.target.value)} required />
              </div>
              <div className="form-row">
                <label>Lokalizacja docelowa PW</label>
                <select value={targetLocId} onChange={(e) => setTargetLocId(e.target.value)}>
                  {wgLocs.map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.kod} — {l.nazwa}
                    </option>
                  ))}
                </select>
              </div>
              <div className="form-row">
                <label>Strata: zważony odsiew/zanieczyszczenia [kg]</label>
                <input type="number" step="0.001" value={odsiewKg} onChange={(e) => setOdsiewKg(e.target.value)} required />
              </div>
              <div className="form-row">
                <label>Strata: ubytek wilgotności [kg]</label>
                <input type="number" step="0.001" value={wilgLossKg} onChange={(e) => setWilgLossKg(e.target.value)} required />
              </div>
              <div className="form-row">
                <label>Termin przydatności partii wyrobu</label>
                <input type="date" value={expDate} onChange={(e) => setExpDate(e.target.value)} required />
              </div>
            </div>
            <div className="form-row">
              <label>Przyczyna technologiczna (wymagana, gdy strata &gt; 3%)</label>
              <input
                type="text"
                value={powodStraty}
                onChange={(e) => setPowodStraty(e.target.value)}
                placeholder="Opcjonalnie, jeśli strata <= 3%"
              />
            </div>
            <div className="tabs">
              <button type="submit" className="btn btn-primary">
                Uzgodnij bilans (tol. 0,5%) i zatwierdź PW
              </button>
              <button type="button" className="btn btn-secondary" onClick={() => setSettleOrderId(null)}>
                Anuluj
              </button>
            </div>
          </form>
        </div>
      )}

      <div className="card">
        <h3>Zlecenia produkcyjne</h3>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Numer</th>
                <th>Receptura</th>
                <th>Surowiec RW</th>
                <th>Uzysk (główny + uboczne)</th>
                <th>Strata / Różnica bilansu</th>
                <th>Status</th>
                <th>Akcja</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o) => (
                <tr key={o.id}>
                  <td>
                    <strong>{o.numer}</strong>
                    <br />
                    <small>{o.linia_przemialowa}</small>
                  </td>
                  <td>{o.receptura_nazwa}</td>
                  <td>
                    {o.partia_surowca_kod}
                    <br />
                    <strong>{o.ilosc_rw_kg} kg</strong>
                  </td>
                  <td>
                    {o.ilosc_pw_glowny_kg} + {o.ilosc_pw_uboczne_kg} kg
                  </td>
                  <td>
                    Strata: {o.strata_calkowita_kg} kg
                    <br />
                    <small>
                      Różnica: {o.roznica_bilansowa_kg} kg ({o.roznica_bilansowa_pct}%)
                    </small>
                  </td>
                  <td>
                    <span
                      className={`badge ${
                        o.status === "ZAKONCZONE"
                          ? "badge-ok"
                          : o.status === "WSTRZYMANE_DO_AKCEPTACJI"
                          ? "badge-warn"
                          : "badge-info"
                      }`}
                    >
                      {o.status}
                    </span>
                  </td>
                  <td>
                    {o.status === "W_REALIZACJI" && canProduce && (
                      <button type="button" className="btn btn-primary btn-sm" onClick={() => setSettleOrderId(o.id)}>
                        Rozlicz PW
                      </button>
                    )}
                    {o.status === "WSTRZYMANE_DO_AKCEPTACJI" && isManager && (
                      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                        <input
                          type="text"
                          value={kierKomentarz}
                          onChange={(e) => setKierKomentarz(e.target.value)}
                          placeholder="Decyzja kierownika"
                        />
                        <div style={{ display: "flex", gap: 6 }}>
                          <button type="button" className="btn btn-primary btn-sm" onClick={() => managerLossDecision(o.id, true)}>
                            Akceptuj
                          </button>
                          <button type="button" className="btn btn-danger btn-sm" onClick={() => managerLossDecision(o.id, false)}>
                            Zwróć
                          </button>
                        </div>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <h3>Raport wydajności technologicznej przemiału (UC-02.6)</h3>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Zlecenie</th>
                <th>Wyrób</th>
                <th>Partia surowca (wilg./zan.)</th>
                <th>RW [kg]</th>
                <th>Uzysk główny [%]</th>
                <th>Produkty uboczne [%]</th>
                <th>Strata [%] vs normatyw</th>
              </tr>
            </thead>
            <tbody>
              {yieldReport.length === 0 ? (
                <tr>
                  <td colSpan={7}>Brak zakończonych zleceń produkcyjnych.</td>
                </tr>
              ) : (
                yieldReport.map((r) => (
                  <tr key={r.zlecenie_id}>
                    <td>{r.numer}</td>
                    <td>{r.wyrob_nazwa}</td>
                    <td>
                      {r.partia_surowca_kod} ({r.wilgotnosc_surowca_pct || "-"}% / {r.zanieczyszczenia_surowca_pct || "-"}%)
                    </td>
                    <td>{r.ilosc_rw_kg}</td>
                    <td>
                      <strong>{r.uzysk_glowny_pct}%</strong>
                    </td>
                    <td>{r.uzysk_uboczne_pct}%</td>
                    <td>
                      {r.strata_rzeczywista_pct}% (norma {r.normatyw_strat_pct}%)
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
