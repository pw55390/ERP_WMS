import React, { useEffect, useState } from "react";
import { apiFetch, openAuthenticatedPdf, SystemStatus, UserInfo } from "../api/client";

export const P1SkupView: React.FC<{ user: UserInfo; status: SystemStatus | null }> = ({ user, status }) => {
  const [przyjecia, setPrzyjecia] = useState<any[]>([]);
  const [dostawcy, setDostawcy] = useState<any[]>([]);
  const [surowce, setSurowce] = useState<any[]>([]);
  const [silosy, setSilosy] = useState<any[]>([]);
  const [kontrolny, setKontrolny] = useState<any[]>([]);

  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  // Formularz nowego przyjęcia
  const [dostawcaId, setDostawcaId] = useState("");
  const [asortymentId, setAsortymentId] = useState("");
  const [silosId, setSilosId] = useState("");
  const [nrRej, setNrRej] = useState("DW 8842L");
  const [bruttoKg, setBruttoKg] = useState("");
  const [trybReczny, setTrybReczny] = useState(false);
  const [kodAutoryzacji, setKodAutoryzacji] = useState("");
  const [wagaInfo, setWagaInfo] = useState<string | null>(null);

  // Nowy dostawca + GUS
  const [showNewSup, setShowNewSup] = useState(false);
  const [newNip, setNewNip] = useState("");
  const [newNazwa, setNewNazwa] = useState("");
  const [newAdres, setNewAdres] = useState("");
  const [gusInfo, setGusInfo] = useState<string | null>(null);
  const [gusSource, setGusSource] = useState("RECZNE");

  // Jakość / Tara dla wybranego przyjęcia
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [wilg, setWilg] = useState("14.2");
  const [zan, setZan] = useState("1.5");
  const [gestosc, setGestosc] = useState("78.5");
  const [opadanie, setOpadanie] = useState("285");
  const [taraKg, setTaraKg] = useState("");
  const [taraReczna, setTaraReczna] = useState(false);
  const [taraKod, setTaraKod] = useState("");
  const [kierKomentarz, setKierKomentarz] = useState("Warunkowa zgoda — szybki przemiał");

  const canOperate = ["OP_WAG", "KIER_MAG"].includes(user.rola);
  const isManager = user.rola === "KIER_MAG";

  async function loadAll() {
    try {
      const [pList, supList, itemList, locList] = await Promise.all([
        apiFetch<any[]>("/api/p1/przyjecia"),
        apiFetch<any[]>("/api/kontrahenci?typ=DOSTAWCA"),
        apiFetch<any[]>("/api/asortyment?kategoria=SUROWIEC"),
        apiFetch<any[]>("/api/lokalizacje?typ=SILOS"),
      ]);
      setPrzyjecia(pList);
      setDostawcy(supList);
      setSurowce(itemList);
      setSilosy(locList);
      if (!dostawcaId && supList[0]) setDostawcaId(supList[0].id);
      if (!asortymentId && itemList[0]) setAsortymentId(itemList[0].id);
      if (!silosId && locList[0]) setSilosId(locList[0].id);
      if (["KIER_MAG", "ADMIN"].includes(user.rola)) {
        apiFetch<any[]>("/api/p1/raport-kontrolny").then(setKontrolny).catch(() => {});
      }
    } catch (e: any) {
      setErr(e.message);
    }
  }

  useEffect(() => {
    loadAll();
  }, []);

  async function readScaleGross(simulateFailure: boolean) {
    setErr(null);
    try {
      const res = await apiFetch<any>("/api/p1/waga/odczyt-brutto", {
        method: "POST",
        body: JSON.stringify({ symuluj_awarie: simulateFailure }),
      });
      setWagaInfo(`[${res.tryb} | ${res.protokol}] ${res.komunikat}`);
      if (res.status_urzadzenia === "AWARIA_ODCZYTU") {
        setTrybReczny(true);
        setBruttoKg("");
      } else {
        setTrybReczny(false);
        setBruttoKg(res.masa_kg);
      }
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function readScaleTare(brutto: string, simulateFailure: boolean) {
    setErr(null);
    try {
      const res = await apiFetch<any>("/api/p1/waga/odczyt-tara", {
        method: "POST",
        body: JSON.stringify({ symuluj_awarie: simulateFailure, masa_brutto_kg: brutto }),
      });
      setWagaInfo(`[${res.tryb}] ${res.komunikat}`);
      if (res.status_urzadzenia === "AWARIA_ODCZYTU") {
        setTaraReczna(true);
        setTaraKg("");
      } else {
        setTaraReczna(false);
        setTaraKg(res.masa_kg);
      }
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function lookupGus() {
    setErr(null);
    setGusInfo(null);
    try {
      const res = await apiFetch<any>(`/api/kontrahenci/gus/${encodeURIComponent(newNip)}`);
      setGusInfo(`[${res.tryb}] ${res.komunikat}`);
      if (res.nazwa) setNewNazwa(res.nazwa);
      if (res.adres) setNewAdres(res.adres);
      setGusSource(res.znaleziono_w_gus ? "GUS_SYMULACJA" : "RECZNE");
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function createSupplier(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    try {
      const created = await apiFetch<any>("/api/kontrahenci", {
        method: "POST",
        body: JSON.stringify({
          nip: newNip,
          nazwa: newNazwa,
          adres: newAdres,
          typ: "DOSTAWCA",
          zrodlo_danych: gusSource,
        }),
      });
      setMsg(`Dodano dostawcę: ${created.nazwa}`);
      setShowNewSup(false);
      await loadAll();
      setDostawcaId(created.id);
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function createIntake(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setMsg(null);
    try {
      const res = await apiFetch<any>("/api/p1/przyjecia", {
        method: "POST",
        body: JSON.stringify({
          dostawca_id: dostawcaId,
          asortyment_id: asortymentId,
          silos_docelowy_id: silosId,
          nr_rejestracyjny: nrRej,
          tryb_reczny: trybReczny,
          kod_autoryzacji: trybReczny ? kodAutoryzacji : null,
          masa_brutto_kg: bruttoKg,
        }),
      });
      setMsg(`Zarejestrowano wjazd ${res.numer_roboczy} (brutto ${res.masa_brutto_kg} kg). Wprowadź parametry jakościowe.`);
      setSelectedId(res.id);
      setKodAutoryzacji("");
      await loadAll();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function submitQuality(id: string) {
    setErr(null);
    setMsg(null);
    try {
      const res = await apiFetch<any>(`/api/p1/przyjecia/${id}/jakosc`, {
        method: "POST",
        body: JSON.stringify({
          wilgotnosc_pct: wilg,
          zanieczyszczenia_pct: zan,
          gestosc_ziarna: gestosc || null,
          liczba_opadania: opadanie ? parseInt(opadanie, 10) : null,
        }),
      });
      if (res.przyjecie.status === "OCZEKUJE_KIEROWNIKA") {
        setMsg("Przekroczono dopuszczalny próg jakościowy! Przyjęcie wstrzymane do decyzji KIER_MAG.");
      } else {
        setMsg("Metryka jakościowa w normie. Przejdź do ważenia tary i wystawienia PZ.");
      }
      await loadAll();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function managerDecision(id: string, approve: boolean) {
    setErr(null);
    setMsg(null);
    try {
      await apiFetch(`/api/p1/przyjecia/${id}/decyzja-kierownika`, {
        method: "POST",
        body: JSON.stringify({ zatwierdz: approve, komentarz: kierKomentarz }),
      });
      setMsg(approve ? "Kierownik wyraził zgodę warunkową na przyjęcie." : "Kierownik odrzucił dostawę.");
      await loadAll();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function finalizePz(id: string) {
    setErr(null);
    setMsg(null);
    try {
      const res = await apiFetch<any>(`/api/p1/przyjecia/${id}/tara-i-pz`, {
        method: "POST",
        body: JSON.stringify({
          tryb_reczny: taraReczna,
          kod_autoryzacji: taraReczna ? taraKod : null,
          masa_tara_kg: taraKg,
        }),
      });
      setMsg(`Zatwierdzono dokument ${res.dokument_pz_numer} oraz utworzono partię ${res.kod_partii} (${res.masa_netto_kg} kg netto).`);
      setSelectedId(null);
      setTaraKg("");
      await loadAll();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  const selected = przyjecia.find((p) => p.id === selectedId) || null;
  const progWilg = status?.reguly_konfigurowalne.prog_wilgotnosci_pct || "15.000";

  return (
    <div>
      {err && <div className="alert alert-error">{err}</div>}
      {msg && <div className="alert alert-success">{msg}</div>}

      <div className="alert alert-info">
        <strong>Próg wilgotności P1: {progWilg}%</strong> — wartość konfigurowalna przez ADMIN (zapis 15% wg README/RF-01.2;
        materiały UML/Lista 2 zawierają także próg 16,5% do zatwierdzenia przez właściciela procesu).
      </div>

      {canOperate && (
        <div className="card">
          <h2>P1: Nowe przyjęcie skupowe (ważenie brutto)</h2>
          <div className="tabs">
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => setShowNewSup((v) => !v)}>
              {showNewSup ? "Ukryj formularz dostawcy" : "+ Nowy dostawca (GUS Symulacja)"}
            </button>
          </div>

          {showNewSup && (
            <form onSubmit={createSupplier} className="card" style={{ background: "#f8fafc" }}>
              <h3>Rejestracja dostawcy (UC-01.4)</h3>
              {gusInfo && <div className="alert alert-warn">{gusInfo}</div>}
              <div className="grid-3">
                <div className="form-row">
                  <label>NIP (10 cyfr, np. 5250001122)</label>
                  <div style={{ display: "flex", gap: 8 }}>
                    <input type="text" value={newNip} onChange={(e) => setNewNip(e.target.value)} required />
                    <button type="button" className="btn btn-secondary btn-sm" onClick={lookupGus}>
                      Pobierz GUS
                    </button>
                  </div>
                </div>
                <div className="form-row">
                  <label>Nazwa dostawcy</label>
                  <input type="text" value={newNazwa} onChange={(e) => setNewNazwa(e.target.value)} required />
                </div>
                <div className="form-row">
                  <label>Adres</label>
                  <input type="text" value={newAdres} onChange={(e) => setNewAdres(e.target.value)} required />
                </div>
              </div>
              <button type="submit" className="btn btn-primary btn-sm">
                Zapisz dostawcę
              </button>
            </form>
          )}

          <form onSubmit={createIntake}>
            <div className="grid-2">
              <div className="form-row">
                <label>Dostawca</label>
                <select value={dostawcaId} onChange={(e) => setDostawcaId(e.target.value)} required>
                  {dostawcy.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.nazwa} (NIP: {d.nip})
                    </option>
                  ))}
                </select>
              </div>
              <div className="form-row">
                <label>Surowiec</label>
                <select value={asortymentId} onChange={(e) => setAsortymentId(e.target.value)} required>
                  {surowce.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.nazwa} ({s.kod_wewnetrzny})
                    </option>
                  ))}
                </select>
              </div>
              <div className="form-row">
                <label>Silos docelowy</label>
                <select value={silosId} onChange={(e) => setSilosId(e.target.value)} required>
                  {silosy.map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.kod} — {l.nazwa} (wolne: {l.wolne_miejsce_kg} kg{l.czy_zablokowana ? " [ZABLOKOWANY]" : ""})
                    </option>
                  ))}
                </select>
              </div>
              <div className="form-row">
                <label>Nr rejestracyjny pojazdu</label>
                <input type="text" value={nrRej} onChange={(e) => setNrRej(e.target.value)} required />
              </div>
            </div>

            <div className="tabs" style={{ marginTop: 8 }}>
              <button type="button" className="btn btn-secondary" onClick={() => readScaleGross(false)}>
                Pobierz brutto z wagi [SYMULACJA]
              </button>
              <button type="button" className="btn btn-warn" onClick={() => readScaleGross(true)}>
                Symuluj awarię wagi (UC-01.5)
              </button>
            </div>
            {wagaInfo && <div className="alert alert-warn">{wagaInfo}</div>}

            <div className="grid-2">
              <div className="form-row">
                <label>Masa brutto [kg] {trybReczny ? "(WPIS RĘCZNY — AWARIA WAGI)" : "(odczyt z symulatora)"}</label>
                <input
                  type="number"
                  step="0.001"
                  value={bruttoKg}
                  onChange={(e) => setBruttoKg(e.target.value)}
                  readOnly={!trybReczny}
                  required
                />
              </div>
              {trybReczny && (
                <div className="form-row">
                  <label>Kod autoryzacyjny KIER_MAG (demo: KIER-AWARIA-2026)</label>
                  <input
                    type="text"
                    value={kodAutoryzacji}
                    onChange={(e) => setKodAutoryzacji(e.target.value)}
                    placeholder="Wpisz kod od kierownika"
                    required
                  />
                </div>
              )}
            </div>

            <button type="submit" className="btn btn-primary" disabled={!bruttoKg}>
              Zarejestruj wjazd i masę brutto
            </button>
          </form>
        </div>
      )}

      {selected && (
        <div className="card" style={{ borderColor: "#17365d", borderWidth: 2 }}>
          <h3>Obsługa przyjęcia: {selected.numer_roboczy} — {selected.dostawca_nazwa}</h3>
          <p>
            Status: <span className="badge badge-info">{selected.status}</span> | Brutto:{" "}
            <strong>{selected.masa_brutto_kg} kg</strong> | Silos: <strong>{selected.silos_kod}</strong>
            {selected.flaga_awarii_wagi && <span className="badge badge-danger" style={{ marginLeft: 8 }}>AWARIA WAGI (AUDYT)</span>}
          </p>

          {selected.status === "W_TOKU" && canOperate && (
            <div className="grid-2">
              <div className="card" style={{ background: "#f8fafc" }}>
                <h4>Krok 2: Metryka jakościowa (UC-01.2)</h4>
                <div className="grid-2">
                  <div className="form-row">
                    <label>Wilgotność [%] (próg {progWilg}%)</label>
                    <input type="number" step="0.1" value={wilg} onChange={(e) => setWilg(e.target.value)} />
                  </div>
                  <div className="form-row">
                    <label>Zanieczyszczenia [%] (próg 4%)</label>
                    <input type="number" step="0.1" value={zan} onChange={(e) => setZan(e.target.value)} />
                  </div>
                  <div className="form-row">
                    <label>Gęstość ziarna [kg/hl]</label>
                    <input type="number" step="0.1" value={gestosc} onChange={(e) => setGestosc(e.target.value)} />
                  </div>
                  <div className="form-row">
                    <label>Liczba opadania [s]</label>
                    <input type="number" value={opadanie} onChange={(e) => setOpadanie(e.target.value)} />
                  </div>
                </div>
                <button type="button" className="btn btn-primary" onClick={() => submitQuality(selected.id)}>
                  Zapisz i waliduj jakość
                </button>
              </div>

              <div className="card" style={{ background: "#f8fafc" }}>
                <h4>Krok 3: Ważenie tary i wystawienie PZ (UC-01.3)</h4>
                <div className="tabs">
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => readScaleTare(selected.masa_brutto_kg || "38000", false)}
                  >
                    Pobierz tarę [SYMULACJA]
                  </button>
                  <button
                    type="button"
                    className="btn btn-warn btn-sm"
                    onClick={() => readScaleTare(selected.masa_brutto_kg || "38000", true)}
                  >
                    Awaria wagi przy tarze
                  </button>
                </div>
                <div className="form-row">
                  <label>Masa tary [kg]</label>
                  <input
                    type="number"
                    step="0.001"
                    value={taraKg}
                    onChange={(e) => setTaraKg(e.target.value)}
                    readOnly={!taraReczna}
                  />
                </div>
                {taraReczna && (
                  <div className="form-row">
                    <label>Kod autoryzacyjny KIER_MAG</label>
                    <input type="text" value={taraKod} onChange={(e) => setTaraKod(e.target.value)} />
                  </div>
                )}
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={!taraKg || selected.wilgotnosc_pct === null}
                  onClick={() => finalizePz(selected.id)}
                >
                  Zatwierdź tarę i wystaw PZ
                </button>
              </div>
            </div>
          )}

          {selected.status === "OCZEKUJE_KIEROWNIKA" && (
            <div className="alert alert-warn">
              <strong>Eskalacja jakościowa:</strong> Wilgotność {selected.wilgotnosc_pct}% / Zanieczyszczenia{" "}
              {selected.zanieczyszczenia_pct}% przekraczają próg! Wymagana decyzja KIER_MAG.
              {isManager && (
                <div style={{ marginTop: 10 }}>
                  <input
                    type="text"
                    value={kierKomentarz}
                    onChange={(e) => setKierKomentarz(e.target.value)}
                    placeholder="Uzasadnienie decyzji kierownika"
                    style={{ marginBottom: 8 }}
                  />
                  <div className="tabs">
                    <button type="button" className="btn btn-primary btn-sm" onClick={() => managerDecision(selected.id, true)}>
                      Wyraź zgodę warunkową
                    </button>
                    <button type="button" className="btn btn-danger btn-sm" onClick={() => managerDecision(selected.id, false)}>
                      Odrzuć dostawę
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      <div className="card">
        <h3>Rejestr przyjęć skupowych i dokumentów PZ</h3>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Nr skupu</th>
                <th>Dostawca / Pojazd</th>
                <th>Surowiec / Silos</th>
                <th>Brutto / Tara / Netto</th>
                <th>Rozliczeniowa</th>
                <th>Jakość</th>
                <th>Status</th>
                <th>Dokument PZ / Partia</th>
                <th>Akcja</th>
              </tr>
            </thead>
            <tbody>
              {przyjecia.length === 0 ? (
                <tr>
                  <td colSpan={9}>Brak zarejestrowanych przyjęć.</td>
                </tr>
              ) : (
                przyjecia.map((p) => (
                  <tr key={p.id}>
                    <td>
                      <strong>{p.numer_roboczy}</strong>
                      {p.flaga_awarii_wagi && <div className="badge badge-danger">AWARIA WAGI</div>}
                    </td>
                    <td>
                      {p.dostawca_nazwa}
                      <br />
                      <small>{p.nr_rejestracyjny}</small>
                    </td>
                    <td>
                      {p.asortyment_nazwa}
                      <br />
                      <small>{p.silos_kod}</small>
                    </td>
                    <td>
                      {p.masa_brutto_kg || "-"} / {p.masa_tara_kg || "-"} / <strong>{p.masa_netto_kg || "-"} kg</strong>
                    </td>
                    <td>{p.masa_rozliczeniowa_kg ? `${p.masa_rozliczeniowa_kg} kg` : "-"}</td>
                    <td>
                      {p.wilgotnosc_pct !== null ? `Wilg: ${p.wilgotnosc_pct}% | Zan: ${p.zanieczyszczenia_pct}%` : "Brak próby"}
                    </td>
                    <td>
                      <span
                        className={`badge ${
                          p.status === "ZATWIERDZONE"
                            ? "badge-ok"
                            : p.status === "OCZEKUJE_KIEROWNIKA"
                            ? "badge-warn"
                            : p.status === "ODRZUCONE"
                            ? "badge-danger"
                            : "badge-info"
                        }`}
                      >
                        {p.status}
                      </span>
                    </td>
                    <td>
                      {p.dokument_pz_numer ? (
                        <>
                          <strong>{p.dokument_pz_numer}</strong>
                          <br />
                          <small>{p.kod_partii}</small>
                        </>
                      ) : (
                        "-"
                      )}
                    </td>
                    <td>
                      {p.status === "W_TOKU" || p.status === "OCZEKUJE_KIEROWNIKA" ? (
                        <button type="button" className="btn btn-primary btn-sm" onClick={() => setSelectedId(p.id)}>
                          Obsłuż
                        </button>
                      ) : p.dokument_pz_id ? (
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          onClick={() => openAuthenticatedPdf(`/api/dokumenty/${p.dokument_pz_id}/pdf`, `${p.dokument_pz_numer}.pdf`)}
                        >
                          PDF PZ
                        </button>
                      ) : (
                        "-"
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {kontrolny.length > 0 && (
        <div className="card">
          <h3>Raport kontrolny wyjątków P1 (awarie wagi i przekroczenia jakości)</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Numer</th>
                  <th>Dostawca</th>
                  <th>Źródło pomiaru</th>
                  <th>Wilgotność / Zanieczyszczenia</th>
                  <th>Komentarz kierownika</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {kontrolny.map((k) => (
                  <tr key={k.id}>
                    <td>{k.numer_roboczy}</td>
                    <td>{k.dostawca_nazwa}</td>
                    <td>{k.zrodlo_pomiaru}</td>
                    <td>
                      {k.wilgotnosc_pct}% / {k.zanieczyszczenia_pct}%
                    </td>
                    <td>{k.decyzja_komentarz || "-"}</td>
                    <td>{k.status}</td>
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
