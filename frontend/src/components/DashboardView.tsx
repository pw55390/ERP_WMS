import React, { useEffect, useState } from "react";
import { apiFetch, SystemStatus, UserInfo } from "../api/client";

export const DashboardView: React.FC<{
  user: UserInfo;
  status: SystemStatus | null;
  onNavigate: (tab: string) => void;
}> = ({ user, status, onNavigate }) => {
  const [stany, setStany] = useState<any[]>([]);
  const [lokalizacje, setLokalizacje] = useState<any[]>([]);
  const [przyjecia, setPrzyjecia] = useState<any[]>([]);
  const [zlecenia, setZlecenia] = useState<any[]>([]);

  useEffect(() => {
    apiFetch<{ partie: any[] }>("/api/p4/stany?tylko_dostepne=true")
      .then((d) => setStany(d.partie))
      .catch(() => {});
    apiFetch<any[]>("/api/lokalizacje")
      .then(setLokalizacje)
      .catch(() => {});
    if (["OP_WAG", "KIER_MAG", "FAKT_KS", "ADMIN"].includes(user.rola)) {
      apiFetch<any[]>("/api/p1/przyjecia").then(setPrzyjecia).catch(() => {});
    }
    if (["INZ_PROD", "KIER_MAG", "ADMIN"].includes(user.rola)) {
      apiFetch<any[]>("/api/p2/zlecenia").then(setZlecenia).catch(() => {});
    }
  }, [user.rola]);

  const totalKg = stany.reduce((acc, p) => acc + parseFloat(p.masa_dostepna_kg || "0"), 0);
  const expiredCount = stany.filter((p) => p.czy_przeterminowana).length;
  const lockedLocs = lokalizacje.filter((l) => l.czy_zablokowana).length;
  const pendingQuality = przyjecia.filter((p) => p.status === "OCZEKUJE_KIEROWNIKA").length;
  const heldOrders = zlecenia.filter((z) => z.status === "WSTRZYMANE_DO_AKCEPTACJI").length;

  return (
    <div>
      <div className="card">
        <h2>Pulpit operacyjny — {user.imie_nazwisko}</h2>
        <p style={{ marginTop: 0, color: "#475569" }}>
          Rola aktywna: <span className="badge badge-info">{user.rola}</span>. Uprawnienia egzekwowane są po stronie API (RBAC).
        </p>

        <div className="grid-3">
          <div className="kpi-box">
            <div className="label">Łączny stan dostępny</div>
            <div className="value">{totalKg.toLocaleString("pl-PL", { maximumFractionDigits: 1 })} kg</div>
          </div>
          <div className="kpi-box">
            <div className="label">Aktywne partie magazynowe</div>
            <div className="value">{stany.length}</div>
          </div>
          <div className="kpi-box">
            <div className="label">Partie przeterminowane (blokada WZ)</div>
            <div className="value" style={{ color: expiredCount > 0 ? "#b91c1c" : "#166534" }}>
              {expiredCount}
            </div>
          </div>
          <div className="kpi-box">
            <div className="label">Lokalizacje zablokowane (inwentaryzacja)</div>
            <div className="value" style={{ color: lockedLocs > 0 ? "#b45309" : "#17365d" }}>
              {lockedLocs}
            </div>
          </div>
          <div className="kpi-box">
            <div className="label">Przyjęcia czekające na kierownika</div>
            <div className="value">{pendingQuality}</div>
          </div>
          <div className="kpi-box">
            <div className="label">Zlecenia wstrzymane (strata &gt; 3%)</div>
            <div className="value">{heldOrders}</div>
          </div>
        </div>
      </div>

      <div className="card">
        <h3>Scenariusz demonstracyjny P1 → P4 (przepływ end-to-end)</h3>
        <div className="grid-2">
          <div>
            <ol style={{ paddingLeft: 20, margin: 0 }}>
              <li>
                <strong>P1 (OP_WAG / KIER_MAG):</strong> Pobierz brutto z symulatora wagi (lub przetestuj awarię z kodem{" "}
                <code>KIER-AWARIA-2026</code>), wpisz jakość (&gt;15% eskaluje do kierownika), zarejestruj tarę i wystaw PZ.
              </li>
              <li>
                <strong>P2 (INZ_PROD / KIER_MAG):</strong> Utwórz zlecenie z aktywnej receptury BOM (auto RW), rozlicz mąkę, otręby i stratę; sprawdź blokadę bilansu &gt;0,5%.
              </li>
              <li>
                <strong>P3 (MAG_WG / FAKT_KS):</strong> Otwórz zamówienie <code>ZS/2026/0001</code>, sprawdź podpowiedź FEFO, przetestuj twardą blokadę partii przeterminowanej <code>LOT-WG-2026-EXP1</code>, wystaw WZ, a następnie fakturę FS i PDF.
              </li>
              <li>
                <strong>P4 (KIER_MAG / MAG_WG):</strong> Wykonaj przesunięcie MM, otwórz inwentaryzację z blokadą strefy, wpisz spis i rozlicz różnice dokumentami PW-kor / RW-kor.
              </li>
            </ol>
          </div>
          <div>
            <div className="tabs">
              <button className="btn btn-primary" onClick={() => onNavigate("p1")}>
                Przejdź do P1: Skup i PZ
              </button>
              <button className="btn btn-primary" onClick={() => onNavigate("p2")}>
                Przejdź do P2: Produkcja
              </button>
              <button className="btn btn-primary" onClick={() => onNavigate("p3")}>
                Przejdź do P3: Wydania FEFO
              </button>
              <button className="btn btn-secondary" onClick={() => onNavigate("faktury")}>
                Faktury FS / PDF
              </button>
              <button className="btn btn-secondary" onClick={() => onNavigate("p4")}>
                P4: Magazyn i Inwentaryzacja
              </button>
            </div>
          </div>
        </div>
      </div>

      {status && (
        <div className="card">
          <h3>Aktywne progi domenowe i status prototypu MVP</h3>
          <div className="alert alert-info">
            <strong>Próg wilgotności:</strong> {status.reguly_konfigurowalne.prog_wilgotnosci_pct}% |{" "}
            <strong>Tolerancja bilansu P2:</strong> {status.reguly_konfigurowalne.tolerancja_bilansu_pct}% |{" "}
            <strong>Próg straty P2:</strong> {status.reguly_konfigurowalne.prog_straty_procesowej_pct}%
            <div style={{ marginTop: 6, fontWeight: 400 }}>{status.reguly_konfigurowalne.uwaga_prog_wilgotnosci}</div>
          </div>
          <ul style={{ margin: 0, paddingLeft: 20, color: "#475569" }}>
            {status.ograniczenia_prototypu.map((item, idx) => (
              <li key={idx}>{item}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};
