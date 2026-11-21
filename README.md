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

