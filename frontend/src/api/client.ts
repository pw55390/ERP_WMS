export type UserRole = "OP_WAG" | "MAG_WG" | "INZ_PROD" | "KIER_MAG" | "FAKT_KS" | "ADMIN";

export interface UserInfo {
  id: string;
  login: string;
  imie_nazwisko: string;
  rola: UserRole;
  czy_aktywny: boolean;
  czy_2fa_wymagane: boolean;
}

export interface SystemStatus {
  aplikacja: string;
  wersja: string;
  tryb_demo: boolean;
  baza_danych: string;
  integracje: {
    waga_najazdowa: string;
    api_gus: string;
  };
  reguly_konfigurowalne: {
    prog_wilgotnosci_pct: string;
    prog_zanieczyszczen_pct: string;
    tolerancja_bilansu_pct: string;
    prog_straty_procesowej_pct: string;
    uwaga_prog_wilgotnosci: string;
  };
  ograniczenia_prototypu: string[];
}

const TOKEN_KEY = "emagazyn_access_token";
const REFRESH_KEY = "emagazyn_refresh_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setTokens(access: string, refresh: string) {
  localStorage.setItem(TOKEN_KEY, access);
  localStorage.setItem(REFRESH_KEY, refresh);
}

export function clearTokens() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

async function tryRefresh(): Promise<boolean> {
  const rt = localStorage.getItem(REFRESH_KEY);
  if (!rt) return false;
  try {
    const res = await fetch("/api/auth/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: rt }),
    });
    if (!res.ok) return false;
    const data = await res.json();
    setTokens(data.access_token, data.refresh_token);
    return true;
  } catch {
    return false;
  }
}

export async function apiFetch<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> | undefined),
  };
  if (options.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  let res = await fetch(path, { ...options, headers });
  if (res.status === 401 && localStorage.getItem(REFRESH_KEY)) {
    const ok = await tryRefresh();
    if (ok) {
      headers["Authorization"] = `Bearer ${getToken()}`;
      res = await fetch(path, { ...options, headers });
    }
  }

  if (!res.ok) {
    let detail = `Błąd HTTP ${res.status}`;
    try {
      const err = await res.json();
      if (typeof err.detail === "string") detail = err.detail;
      else if (Array.isArray(err.detail)) detail = err.detail.map((e: any) => e.msg).join("; ");
    } catch {
      // ignore json parse failure
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export async function openAuthenticatedPdf(path: string, filename: string) {
  const token = getToken();
  const res = await fetch(path, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) {
    let msg = `Błąd pobierania PDF (${res.status})`;
    try {
      const err = await res.json();
      if (err.detail) msg = err.detail;
    } catch {
      // ignore
    }
    throw new Error(msg);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const win = window.open(url, "_blank");
  if (!win) {
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
  }
}
