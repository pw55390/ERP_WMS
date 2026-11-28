# E-Magazyn ERP / WMS

## Zintegrowane zarządzanie skupem, magazynem, produkcją i sprzedażą

E-Magazyn ERP / WMS to projekt aplikacji webowej dla przedsiębiorstw rolno-spożywczych, które skupują zboże, przechowują je w silosach, przetwarzają według receptur i sprzedają wyroby gotowe. System ma połączyć operacje magazynowe, produkcyjne i handlowe w jednym środowisku dostępnym z poziomu przeglądarki.

Docelowym użytkownikiem jest średnie przedsiębiorstwo młynarsko-zbożowe, w którym dostawa surowca, kontrola jakości, ruchy magazynowe, rozliczenie przemiału i wydanie produktów muszą zachować wspólną historię oraz spójne stany. Projekt uwzględnia również obsługę pracy na terminalach magazynowych i stanowiskach dotykowych.

## Wartość dla przedsiębiorstwa

System ma zastąpić rozproszoną ewidencję papierową spójnym obiegiem informacji i dokumentów. Umożliwia powiązanie przyjętej partii z dostawcą, pomiarem wagi i wynikami jakości, a następnie śledzenie jej wykorzystania w produkcji i pochodzenia wyrobów wydanych odbiorcom.

Projektowane rozwiązanie wspiera:

* bieżącą kontrolę przyjęć, jakości surowca i rozliczanej masy dostawy;
* kontrolę ilości i lokalizacji zapasów w silosach, magazynie buforowym i magazynie wyrobów gotowych;
* rozliczanie produkcji na podstawie receptur i dokumentów magazynowych;
* ograniczanie strat oraz wykrywanie rozbieżności bilansowych;
* kompletację wydań według terminów przydatności i blokadę niedopuszczonych partii;
* powiązanie zatwierdzonego wydania z fakturą sprzedaży;
* identyfikowalność partii w całym przepływie od dostawcy do odbiorcy.

## Główne obszary funkcjonalne

### Skup i przyjęcie surowca

Operator rejestruje dostawcę i transport, pomiar masy brutto oraz tary, wyniki kwalifikacji jakościowej i przypisanie dostawy do silosu. System wylicza masę netto i rozliczeniową, tworzy partię oraz dokument PZ. Obsługiwane parametry jakościowe obejmują m.in. wilgotność i zanieczyszczenia. Przekroczenie dopuszczalnego progu, np. wilgotności powyżej 15%, wymaga decyzji kierownika przed zatwierdzeniem przyjęcia.

W przypadku awarii wagi ręczne podanie masy jest operacją wyjątkową: wymaga autoryzacji kierownika, jest oznaczane i podlega audytowi. Projekt przewiduje współpracę z miernikami wagi przez RS-232/Modbus lub TCP/IP oraz pobieranie danych kontrahenta z API GUS.

### Magazynowanie i identyfikowalność

System ewidencjonuje partie, silosy, komórki, strefy oraz lokalizacje magazynowe. Każdy istotny ruch jest powiązany z dokumentem i użytkownikiem. Podgląd stanów uwzględnia zatwierdzone operacje, rezerwacje i blokady. Inwentaryzacja obejmuje blokadę wskazanego zakresu, porównanie spisu ze stanem ewidencyjnym oraz zatwierdzenie rozbieżności. Przesunięcia MM zachowują identyfikację partii.

### Produkcja i rozliczenie przemiału

Technolog definiuje receptury BOM i zlecenia produkcyjne. Pobranie surowca zmniejsza stan w ramach RW, a przyjęcie mąk i produktów ubocznych zwiększa stan poprzez PW. System wiąże uzysk z partią surowca i parametrami jakościowymi.

Bilans produkcji porównuje masę wejściową RW z masą produktów i niezależnie ustaloną stratą. Dopuszczalna tolerancja wynosi 0,5%. Różnica bilansowa nie jest automatycznie uznawana za stratę.

### Sprzedaż, kompletacja i fakturowanie

System obsługuje zamówienie, dobór partii, kompletację, wydanie WZ oraz fakturę VAT sprzedaży FS. Strategia FIFO/FEFO podpowiada partie do wydania, z uwzględnieniem terminu przydatności. Zatwierdzenie partii przeterminowanej lub niedopuszczonej na datę wydania jest zablokowane i nie może być ominięte przez magazyniera.

Ceny mogą być pobierane z cennika kontrahenta. Uprawniony fakturzysta może zmienić cenę, a zmiana jest odnotowana w audycie. Dla zatwierdzonych dokumentów handlowych przewidziane jest generowanie podglądu i pliku PDF.

## Dokumenty i procesy

|Dokument|Zastosowanie|
|-|-|
|**PZ**|Rejestracja przyjęcia zewnętrznego surowca lub towaru.|
|**RW**|Rozchód wewnętrzny, w tym pobranie surowca do produkcji; także korekta niedoboru, jeśli dotyczy.|
|**PW**|Przychód wewnętrzny produktów produkcji; także korekta nadwyżki, jeśli dotyczy.|
|**WZ**|Wydanie zewnętrzne produktów odbiorcy.|
|**MM**|Przesunięcie pomiędzy lokalizacjami magazynowymi.|
|**FS**|Faktura VAT sprzedaży powiązana z zatwierdzonym WZ.|
|**FZ i korekty**|Operacje ewidencyjne i uprawnienia fakturzysty uwzględnione w modelu ról projektu.|

Główne procesy przedsiębiorstwa to: **P1** skup i przyjęcie z kwalifikacją laboratoryjną, **P2** przetwarzanie produkcyjne i rozliczenie przemiału, **P3** sprzedaż i wydanie zewnętrzne wyrobów oraz **P4** inwentaryzacja i bilansowanie stanów.

## Użytkownicy i kontrola dostępu

System rozdziela obowiązki za pomocą modelu RBAC. Projekt przewiduje sześć ról:

|Rola|Zakres odpowiedzialności|
|-|-|
|**OP\_WAG**|Ważenie, dane jakościowe, kwalifikacja dostawy, partia i PZ.|
|**MAG\_WG**|Kompletacja, alokacja palet, skanowanie i dokument WZ.|
|**INZ\_PROD**|Receptury BOM, zlecenia produkcyjne, RW i uzysk PW.|
|**KIER\_MAG**|Nadzór nad stanami, inwentaryzacja, różnice i operacje wyjątkowe.|
|**FAKT\_KS**|Kontrahenci, cenniki, faktury, rozliczenia i korekty w zakresie projektu.|
|**ADMIN**|Konta, role, konfiguracja, kopie zapasowe i przegląd audytu.|

Każda rola otrzymuje tylko uprawnienia potrzebne do wykonywania swoich zadań. System przewiduje 2FA dla KIER\_MAG, FAKT\_KS i ADMIN, haszowanie haseł Argon2id, krótkotrwałe tokeny JWT z mechanizmem Refresh Token oraz automatyczne wygaszanie sesji na terminalach po 5 minutach bezczynności.

Zmiany stanów, generowanie dokumentów formalnych i próby logowania są zapisywane w niemutowalnym dzienniku audytowym Append-Only. Zdarzenie obejmuje użytkownika, czas UTC, adres IP i zapis zmian w JSONB.

## Aplikacja webowa i wymagania jakościowe

Użytkownik korzysta z systemu przez przeglądarkę, bez konieczności instalowania natywnego klienta. Interfejs ma być responsywny i dostosowany do pracy biurowej oraz magazynowej: obsługi dotykowej, czytników kodów działających jak klawiatura i nawigacji klawiaturą. Projekt wymaga przycisków o minimalnej wysokości 48 px i czytelnego, kontrastowego układu.

Architektura zakłada klienta webowego, warstwę API i centralną bazę PostgreSQL. Operacje zmieniające dokumenty i stany muszą zachowywać ACID: dokument i odpowiadający mu ruch magazynowy są zatwierdzane atomowo. API weryfikuje uprawnienia przy każdym żądaniu.

Cele jakościowe określone w wymaganiach projektu obejmują:

* odczyt i filtrowanie kartotek do 500 ms przy 50 równoczesnych użytkownikach;
* zatwierdzenie wielopozycyjnego dokumentu magazynowego do 1 s;
* obsługę co najmniej 100 równoczesnych użytkowników, przy odczycie poniżej 1 s;
* dostępność 99,5% w skali roku, z wyłączeniem planowanych okien serwisowych;
* pełną kopię bazy co 24 godziny i archiwizację WAL co 15 minut;
* szyfrowanie ruchu TLS 1.3 oraz ochronę przed typowymi zagrożeniami aplikacji webowych, w tym CSRF, XSS i SQL Injection;
* przechowywanie dokumentów magazynowych, faktur i danych audytowych przez co najmniej 5 lat od końca roku obrotowego.

## Granice produktu

E-Magazyn ERP / WMS koncentruje się na gospodarce magazynowej i produkcyjnej oraz powiązanej obsłudze sprzedaży i fakturowania. Pełna księgowość przedsiębiorstwa, kadry i płace oraz bezpośrednie sterowanie sterownikami PLC maszyn nie należą do zakresu opisanego w projekcie. Integracja z urządzeniami przemysłowymi wymaga uzgodnionego interfejsu; projekt nie zakłada samodzielnego sterowania automatyką zakładu.

## Status projektu

Projekt definiuje wymagania i docelowy zakres produktu. Kolejne etapy obejmują projekt systemu, implementację bazy danych i aplikacji oraz weryfikację funkcji przed przygotowaniem wydania przeznaczonego dla przedsiębiorstw z branży.

W repozytorium znajduje się obecnie **uruchamialny prototyp MVP** realizujący uzgodnione przepływy P1–P4 oraz fakturowanie FS/PDF (nie jest to ukończony, certyfikowany ani gotowy do sprzedaży produkt komercyjny).

---

## Prototyp MVP — architektura, uruchomienie i ograniczenia

### Wybrany stos technologiczny

- **Backend i API:** Python 3.13+, FastAPI, SQLAlchemy 2.0, Alembic (migracje schematu), Pydantic v2, Argon2id (`argon2-cffi`), JWT + Refresh Token (`PyJWT`), ReportLab (natywne generowanie PDF dla PZ, WZ, FS).
- **Baza danych:** Docelowo **PostgreSQL 16** (z kolumnami `NUMERIC(12,3)`, `JSONB` dla dziennika audytu i blokadą wiersza `SELECT ... FOR UPDATE` w transakcjach ACID). W lokalnym trybie demonstracyjnym bez uruchomionego serwera PostgreSQL aplikacja może działać na bazie SQLite (`sqlite:///./emagazyn_demo.db`).
- **Frontend:** React 19 + TypeScript + Vite (interfejs responsywny, przyciski >= 48 px, wysoki kontrast, obsługa skanerów kodów emulujących klawiaturę).

### Wymagania wstępne

- **Lokalne uruchomienie bez kontenerów:** Python `>= 3.11`, menedżer pakietów `uv`, Node.js `>= 20` + `npm`.
- **Uruchomienie z PostgreSQL:** Docker + Docker Compose (`docker-compose.yml`).

### Szybkie uruchomienie lokalne (tryb demonstracyjny)

1. Skopiuj konfigurację przykładową (opcjonalnie; domyślne zmienne uruchomienia demo działają od razu):
   ```powershell
   copy .env.example .env
   ```
2. Zainstaluj zależności i zbuduj frontend:
   ```powershell
   cd frontend
   npm install
   npm run build
   cd ..
   ```
3. Uruchom migracje i serwer backendu (serwuje zarówno API `/api/*`, jak i zbudowany frontend pod `http://127.0.0.1:8000`):
   ```powershell
   cd backend
   uv sync
   uv run alembic upgrade head
   uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```
4. Tryb deweloperski frontendu (z hot-reload na `http://localhost:5173`):
   ```powershell
   cd frontend
   npm run dev
   ```
5. Testy automatyczne przepływów P1–P4 i RBAC:
   ```powershell
   cd backend
   uv run pytest -v
   ```

### Uruchomienie z PostgreSQL (Docker Compose)

Po zbudowaniu paczki `frontend/dist` (`cd frontend && npm run build`):
```powershell
docker compose up --build
```
Aplikacja będzie dostępna lokalnie pod `http://127.0.0.1:8000` z bazą PostgreSQL 16.

### Konta demonstracyjne (wyłącznie lokalne środowisko demo)

> **Uwaga bezpieczeństwa:** Poniższe poświadczenia służą **wyłącznie** do lokalnego uruchomienia demonstracyjnego prototypu (gdy `DEMO_MODE=true`). Nigdy nie używaj tych kont ani haseł w środowisku produkcyjnym.

| Login | Rola | Zakres w prototypie |
|---|---|---|
| `op_wag` | `OP_WAG` | P1: waga (symulator), jakość, partia surowca, PZ, nowi dostawcy (GUS symulacja) |
| `inz_prod` | `INZ_PROD` | P2: wersjonowane BOM, zlecenia produkcyjne, RW, PW, bilans 0,5%, raport wydajności |
| `mag_wg` | `MAG_WG` | P3: kompletacja FEFO, skanowanie, blokada przeterminowanych partii, WZ, spis z natury |
| `fakt_ks` | `FAKT_KS` | P3/Finanse: zamówienia, cenniki kontrahentów, FS z WZ, ręczna zmiana ceny (audyt), FS-KOR, FZ, PDF |
| `kier_mag` | `KIER_MAG` | P1–P4: kody awarii wagi, zgody jakościowe, akceptacja strat >3%, MM, inwentaryzacja z blokadą strefy, raport rotacji |
| `admin` | `ADMIN` | Konta, role RBAC, konfiguracja progów systemowych, podgląd dziennika audytu |

Hasło demo dla wszystkich kont w lokalnym trybie `DEMO_MODE=true`: `Demo!2026`.  
Przykładowy jednorazowy kod autoryzacji awarii wagi (UC-01.5): `KIER-AWARIA-2026` (kolejne kody generuje `KIER_MAG` w panelu administracyjnym).

### Niejednoznaczność progu wilgotności (15% vs 16,5%)

W materiałach projektowych występują dwie wartości dopuszczalnej wilgotności ziarna: **15%** (README oraz RF-01.2) oraz **16,5%** (diagramy UML/Lista 2). W prototypie wartość ta nie jest zaszyta na stałe — jest pobierana z tabeli `konfiguracja_systemowa` (klucz `prog_wilgotnosci_pct`, wartość domyślna **15.000%**) i może zostać zmieniona przez `ADMIN` bez zmiany kodu. Wartość docelowa wymaga formalnego zatwierdzenia przez właściciela procesu.

### Elementy symulowane oraz świadome ograniczenia prototypu

- **Waga najazdowa (`AdapterWagi`):** działa w jawnym trybie `SYMULACJA` (generuje realistyczne odczyty brutto/tary oraz pozwala przetestować scenariusz awarii z kodem `KIER_MAG`). Brak integracji ze sprzętem RS-232/Modbus.
- **API GUS (`AdapterGUS`):** działa w jawnym trybie `SYMULACJA` dla wybranych numerów NIP demo; brak połączenia produkcyjnego z usługą GUS BIR1.
- **2FA, TLS 1.3, kopie zapasowe WAL i wydajność NFR:** lokalny prototyp HTTP nie egzekwuje 2FA przy logowaniu, nie ma skonfigurowanego TLS 1.3, automatycznych kopii WAL co 15 min ani testów obciążeniowych dla 50/100 równoczesnych użytkowników.
- **Dziennik audytowy:** jest append-only na poziomie logiki aplikacji (w docelowym wdrożeniu PostgreSQL należy odebrać uprawnienia `UPDATE`/`DELETE` roli aplikacyjnej na tabeli `wpisy_audytowe`).

### Model wdrożenia za firmowym VPN (docelowa architektura produkcyjna)

Repozytorium GitHub służy wyłącznie do przechowywania kodu źródłowego, a nie jako hosting backendu i bazy danych. Docelowo:
1. Aplikacja (FastAPI + zbudowany frontend) oraz PostgreSQL działają na serwerze lub w prywatnej sieci zakładowej (VPC/VLAN) bez publicznego dostępu do portu bazy danych (`5432`).
2. Dostęp z internetu odbywa się wyłącznie po zestawieniu połączenia z **firmowym VPN**, poprzez reverse proxy (np. Nginx/Caddy/Traefik) wymuszające **HTTPS (TLS 1.3)** i nagłówki bezpieczeństwa.
3. Wdrożenie produkcyjne wymaga wyłączenia trybu demo (`DEMO_MODE=false`), ustawienia silnego `JWT_SECRET_KEY`, włączenia 2FA dla ról uprzywilejowanych (`KIER_MAG`, `FAKT_KS`, `ADMIN`), polityki kopii bazy 24h + WAL 15 min oraz konfiguracji prawdziwych adapterów wagi i GUS.


