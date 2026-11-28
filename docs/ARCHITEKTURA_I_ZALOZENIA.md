# Podsumowanie architektury, założeń i zakresu MVP

## 1. Architektura warstwowa

Prototyp realizuje architekturę klient–serwer zgodną z dokumentacją projektu:

1. **Warstwa prezentacji (`frontend/`):** SPA w React + TypeScript, komunikujące się wyłącznie z REST API (`/api/*`). Interfejs wspiera stanowiska biurowe i dotykowe (przyciski `>= 48 px`), obsługę klawiaturą oraz skanery kodów kreskowych pracujące w trybie klawiatury emulowanej (`Enter`).
2. **Warstwa API i logiki biznesowej (`backend/app/api/`, `backend/app/services/`):** FastAPI z jawnym rozdzieleniem tras, schematów walidacji Pydantic v2, strażników RBAC (`require_roles`) oraz serwisów domenowych (`AdapterWagi`, `AdapterGUS`, `pdf_service`, `audit`).
3. **Warstwa trwałości (`backend/app/models/`, `backend/alembic/`):** SQLAlchemy 2.0 z migracjami Alembic i typem `Numeric(12, 3)` dla mas/cen, gwarantująca atomowe księgowanie dokumentów i ruchów magazynowych w jednej transakcji.

## 2. Podział odpowiedzialności względem harmonogramu zespołu

- **Skup, ważenie, jakość i PZ (`p1_skup.py`, `P1SkupView.tsx`):** zakres Dominiki Moczydłowskiej (`OP_WAG` / RF-01).
- **BOM, zlecenia, RW/PW i bilans 0,5% (`p2_produkcja.py`, `P2ProdukcjaView.tsx`):** zakres Kacpra Presi (`INZ_PROD` / RF-02).
- **Kompletacja FEFO, WZ, cenniki, FS i PDF (`p3_sprzedaz.py`, `P3SprzedazView.tsx`, `FakturyView.tsx`):** zakres Jana Oszendy (`MAG_WG` / RF-03, `FAKT_KS` / RF-04).
- **Architektura, stany, traceability, MM, inwentaryzacja, RBAC, audyt (`p4_magazyn.py`, `admin.py`, `deps.py`):** zakres Piotra Wolskiego (`KIER_MAG` / RF-05, `ADMIN` / RF-06).

## 3. Świadomie odłożone funkcje (kolejne etapy)

- Natywna komunikacja z fizyczną wagą przez port szeregowy RS-232/Modbus lub TCP/IP oraz produkcyjna integracja SOAP/REST z bazą GUS BIR1.
- Sprzętowe 2FA (TOTP/WebAuthn) dla ról `KIER_MAG`, `FAKT_KS`, `ADMIN`.
- Wymuszenie niemutowalności tabeli `wpisy_audytowe` uprawnieniami DDL/triggerami PostgreSQL oraz automatyczny backup/WAL co 15 min.
- Testy wydajnościowe i obciążeniowe dla 50 i 100 równoczesnych użytkowników oraz pełne środowisko VPN + TLS 1.3.

## 4. Zapisane założenia domenowe

- **Próg wilgotności:** `15.000%` (konfigurowalny w `konfiguracja_systemowa`) — odnotowano rozbieżność względem zapisu `16,5%` w materiałach UML/Lista 2 do rozstrzygnięcia przez właściciela procesu.
- **Tolerancja bilansu P2:** `0.500%` dla `|RW - (PW + produkty uboczne + strata)|`. Różnica nie jest nigdy automatycznie księgowana jako strata.
- **Próg straty procesowej P2:** `3.000%` — przekroczenie wymaga podania przyczyny technologicznej i akceptacji `KIER_MAG`.
- **Blokada partii przeterminowanych P3:** bezwzględna po stronie serwera względem `max(dzisiaj, data_wydania)` dla każdej roli bez wyjątku.
