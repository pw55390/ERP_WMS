import React, { useEffect, useState } from "react";
import { apiFetch, clearTokens, getToken, SystemStatus, UserInfo } from "./api/client";
import { AdminView } from "./components/AdminView";
import { DashboardView } from "./components/DashboardView";
import { FakturyView } from "./components/FakturyView";
import { LoginView } from "./components/LoginView";
import { P1SkupView } from "./components/P1SkupView";
import { P2ProdukcjaView } from "./components/P2ProdukcjaView";
import { P3SprzedazView } from "./components/P3SprzedazView";
import { P4MagazynView } from "./components/P4MagazynView";

export const App: React.FC = () => {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [activeTab, setActiveTab] = useState("pulpit");
  const [booting, setBooting] = useState(true);

  function loadStatus() {
    apiFetch<SystemStatus>("/api/system/status").then(setStatus).catch(() => {});
  }

  useEffect(() => {
    loadStatus();
    if (!getToken()) {
      setBooting(false);
      return;
    }
    apiFetch<UserInfo>("/api/auth/me")
      .then((u) => setUser(u))
      .catch(() => clearTokens())
      .finally(() => setBooting(false));
  }, []);

  function logout() {
    clearTokens();
    setUser(null);
    setActiveTab("pulpit");
  }

  if (booting) {
    return <div style={{ padding: 40, textAlign: "center" }}>Ładowanie E-Magazyn ERP / WMS...</div>;
  }

  if (!user) {
    return (
      <LoginView
        onSuccess={(u) => {
          setUser(u);
          setActiveTab("pulpit");
        }}
      />
    );
  }

  const navItems: Array<{ id: string; label: string; roles: string[] }> = [
    { id: "pulpit", label: "Pulpit i Scenariusz", roles: ["OP_WAG", "MAG_WG", "INZ_PROD", "KIER_MAG", "FAKT_KS", "ADMIN"] },
    { id: "p1", label: "P1: Skup i PZ", roles: ["OP_WAG", "KIER_MAG", "FAKT_KS", "ADMIN"] },
    { id: "p2", label: "P2: Produkcja i BOM", roles: ["INZ_PROD", "KIER_MAG", "ADMIN"] },
    { id: "p3", label: "P3: Sprzedaż i WZ", roles: ["MAG_WG", "KIER_MAG", "FAKT_KS", "ADMIN"] },
    { id: "faktury", label: "Faktury FS / Cenniki", roles: ["FAKT_KS", "KIER_MAG", "ADMIN"] },
    { id: "p4", label: "P4: Magazyn i Spis", roles: ["OP_WAG", "MAG_WG", "INZ_PROD", "KIER_MAG", "FAKT_KS", "ADMIN"] },
    { id: "admin", label: "Administracja / Audyt", roles: ["KIER_MAG", "ADMIN"] },
  ].filter((item) => item.roles.includes(user.rola));

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <h1>E-Magazyn ERP/WMS</h1>
          <small>Prototyp MVP • Młyn i Elewator</small>
        </div>

        <nav className="nav-list" aria-label="Nawigacja główna">
          {navItems.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`nav-btn ${activeTab === item.id ? "active" : ""}`}
              onClick={() => setActiveTab(item.id)}
            >
              <span>{item.label}</span>
            </button>
          ))}
        </nav>

        <div style={{ borderTop: "1px solid rgba(255,255,255,0.2)", paddingTop: 12 }}>
          <div style={{ fontSize: "0.85rem", marginBottom: 8 }}>
            <strong>{user.imie_nazwisko}</strong>
            <br />
            Rola: <code>{user.rola}</code>
          </div>
          <button type="button" className="btn btn-secondary btn-sm" style={{ width: "100%" }} onClick={logout}>
            Wyloguj / Zmień rolę
          </button>
        </div>
      </aside>

      <div className="main-area">
        {status && (
          <div className="demo-banner">
            <span>
              PROTOTYP MVP — {status.tryb_demo ? "DANE DEMONSTRACYJNE" : "TRYB STANDARD"} | Baza: {status.baza_danych}
            </span>
            <span>
              Waga: {status.integracje.waga_najazdowa} | API GUS: {status.integracje.api_gus} | Próg wilgotności:{" "}
              {status.reguly_konfigurowalne.prog_wilgotnosci_pct}%
            </span>
          </div>
        )}

        <header className="topbar">
          <strong>{navItems.find((n) => n.id === activeTab)?.label || "E-Magazyn ERP / WMS"}</strong>
          <span style={{ color: "#475569", fontSize: "0.88rem" }}>
            Zalogowany: <strong>{user.login}</strong> ({user.rola})
          </span>
        </header>

        <main className="content">
          {activeTab === "pulpit" && <DashboardView user={user} status={status} onNavigate={setActiveTab} />}
          {activeTab === "p1" && <P1SkupView user={user} status={status} />}
          {activeTab === "p2" && <P2ProdukcjaView user={user} />}
          {activeTab === "p3" && <P3SprzedazView user={user} />}
          {activeTab === "faktury" && <FakturyView user={user} />}
          {activeTab === "p4" && <P4MagazynView user={user} />}
          {activeTab === "admin" && <AdminView user={user} onConfigChanged={loadStatus} />}
        </main>
      </div>
    </div>
  );
};
