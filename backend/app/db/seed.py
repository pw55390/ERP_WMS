from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.entities import (
    Asortyment,
    CennikKontrahenta,
    DokumentMagazynowy,
    KodAutoryzacyjny,
    KonfiguracjaSystemowa,
    Kontrahent,
    LokalizacjaMagazynowa,
    PartiaMagazynowa,
    PozycjaDokumentu,
    PozycjaZamowienia,
    RecepturaBOM,
    RuchMagazynowy,
    SkladnikReceptury,
    Uzytkownik,
    ZamowienieSprzedazy,
)
from app.services.audit import record_audit

DEMO_PASSWORD_PLAIN = "Demo!2026"

DEMO_USERS = [
    ("op_wag", "Dominika Moczydłowska (Operator Wagi [DEMO])", "OP_WAG", False),
    ("inz_prod", "Kacper Presia (Inżynier Produkcji [DEMO])", "INZ_PROD", False),
    ("mag_wg", "Jan Oszenda (Magazynier Ekspedycji [DEMO])", "MAG_WG", False),
    ("fakt_ks", "Alicja Kowal (Fakturzysta / Księgowość [DEMO])", "FAKT_KS", True),
    ("kier_mag", "Piotr Wolski (Kierownik Magazynu [DEMO])", "KIER_MAG", True),
    ("admin", "Administrator Systemu [DEMO]", "ADMIN", True),
]


def seed_demo_data(db: Session) -> None:
    """Inicjalizuje dane demonstracyjne (idempotentnie, tylko gdy brak użytkowników)."""
    existing_user = db.scalar(select(Uzytkownik).limit(1))
    if existing_user is not None:
        return

    now = datetime.now(timezone.utc)
    today = date.today()

    # 1. Konfiguracja systemowa (z jawną dokumentacją niejednoznaczności progu wilgotności 15% vs 16.5%)
    configs = [
        KonfiguracjaSystemowa(
            klucz="prog_wilgotnosci_pct",
            wartosc="15.000",
            jednostka="%",
            opis=(
                "Dopuszczalny próg wilgotności ziarna przy przyjęciu (wartość demo 15% wg README i RF-01.2; "
                "materiały UML/Lista 2 wskazują też 16,5% — wymaga zatwierdzenia właściciela procesu)."
            ),
        ),
        KonfiguracjaSystemowa(
            klucz="prog_zanieczyszczen_pct",
            wartosc="4.000",
            jednostka="%",
            opis="Maksymalne dopuszczalne zanieczyszczenie ziarna bez zgody KIER_MAG.",
        ),
        KonfiguracjaSystemowa(
            klucz="tolerancja_bilansu_pct",
            wartosc="0.500",
            jednostka="%",
            opis="Maksymalna dopuszczalna rozbieżność bilansu masowego produkcji |RW - (PW + strata)| (RF-02.4).",
        ),
        KonfiguracjaSystemowa(
            klucz="prog_straty_procesowej_pct",
            wartosc="3.000",
            jednostka="%",
            opis="Próg straty procesowej przemiału, powyżej którego PW wymaga akceptacji KIER_MAG.",
        ),
        KonfiguracjaSystemowa(
            klucz="max_czas_bezczynnosci_terminal_sek",
            wartosc="300",
            jednostka="s",
            opis="Docelowy limit bezczynności na terminalu magazynowym (5 minut).",
        ),
    ]
    db.add_all(configs)

    # 2. Użytkownicy demo
    users_by_login: dict[str, Uzytkownik] = {}
    pw_hash = hash_password(DEMO_PASSWORD_PLAIN)
    for login, full_name, role, req_2fa in DEMO_USERS:
        u = Uzytkownik(
            login=login,
            imie_nazwisko=full_name,
            haslo_hash=pw_hash,
            rola=role,
            czy_aktywny=True,
            czy_2fa_wymagane=req_2fa,
        )
        db.add(u)
        users_by_login[login] = u
    db.flush()

    kierownik = users_by_login["kier_mag"]
    op_wag = users_by_login["op_wag"]
    inz_prod = users_by_login["inz_prod"]
    admin = users_by_login["admin"]

    # Przykładowy kod autoryzacyjny kierownika na awarię wagi (UC-01.5)
    db.add(
        KodAutoryzacyjny(
            kod="KIER-AWARIA-2026",
            kierownik_id=kierownik.id,
            cel="AWARIA_WAGI",
            opis="Kod demonstracyjny KIER_MAG do testu ręcznego wpisu wagi przy awarii (UC-01.5)",
            czy_uzyty=False,
            wygasa_utc=now + timedelta(days=30),
        )
    )

    # 3. Kontrahenci [DEMO]
    sup1 = Kontrahent(
        nip="8991002030",
        nazwa="Gospodarstwo Rolne Kowalczyk [DEMO]",
        adres="ul. Polna 14, 55-080 Kąty Wrocławskie",
        typ="DOSTAWCA",
        termin_platnosci_dni=14,
        forma_platnosci="PRZELEW",
        zrodlo_danych="RECZNE",
    )
    sup2 = Kontrahent(
        nip="6112233445",
        nazwa="Spółdzielnia Rolnicza Odra [DEMO]",
        adres="ul. Główna 42, 49-300 Brzeg",
        typ="DOSTAWCA",
        termin_platnosci_dni=21,
        forma_platnosci="PRZELEW",
        zrodlo_danych="RECZNE",
    )
    buy1 = Kontrahent(
        nip="7771234567",
        nazwa="Piekarnia Rzemieślnicza Chlebex [DEMO]",
        adres="ul. Piekarzy 3, 59-220 Legnica",
        typ="ODBIORCA",
        termin_platnosci_dni=14,
        forma_platnosci="PRZELEW",
        zrodlo_danych="RECZNE",
    )
    buy2 = Kontrahent(
        nip="5250001122",
        nazwa="Hurtownia Spożywcza Centrum [DEMO]",
        adres="ul. Magazynowa 19, 50-410 Wrocław",
        typ="ODBIORCA",
        termin_platnosci_dni=30,
        forma_platnosci="PRZELEW",
        zrodlo_danych="RECZNE",
    )
    db.add_all([sup1, sup2, buy1, buy2])
    db.flush()

    # 4. Asortyment
    wheat = Asortyment(
        kod_ean="5901000000011",
        kod_wewnetrzny="PSZ-KONS",
        nazwa="Pszenica konsumpcyjna kl. A",
        kategoria="SUROWIEC",
        jednostka="kg",
        stawka_vat=Decimal("5.00"),
        wilgotnosc_max_pct=Decimal("15.000"),
        zanieczyszczenia_max_pct=Decimal("4.000"),
        cena_bazowa_netto=Decimal("0.980"),
    )
    corn = Asortyment(
        kod_ean="5901000000028",
        kod_wewnetrzny="KUK-PASZ",
        nazwa="Kukurydza paszowa",
        kategoria="SUROWIEC",
        jednostka="kg",
        stawka_vat=Decimal("5.00"),
        wilgotnosc_max_pct=Decimal("15.000"),
        zanieczyszczenia_max_pct=Decimal("4.000"),
        cena_bazowa_netto=Decimal("0.840"),
    )
    flour500 = Asortyment(
        kod_ean="5902000005004",
        kod_wewnetrzny="MAKA-500",
        nazwa="Mąka pszenna typ 500 (worki 25 kg)",
        kategoria="WYROB_GOTOWY",
        jednostka="kg",
        stawka_vat=Decimal("5.00"),
        typ_granulacji="Typ 500",
        okres_przydatnosci_dni=180,
        cena_bazowa_netto=Decimal("2.400"),
    )
    flour750 = Asortyment(
        kod_ean="5902000007503",
        kod_wewnetrzny="MAKA-750",
        nazwa="Mąka pszenna chlebowa typ 750",
        kategoria="WYROB_GOTOWY",
        jednostka="kg",
        stawka_vat=Decimal("5.00"),
        typ_granulacji="Typ 750",
        okres_przydatnosci_dni=180,
        cena_bazowa_netto=Decimal("2.550"),
    )
    bran = Asortyment(
        kod_ean="5903000000105",
        kod_wewnetrzny="OTREBY-PSZ",
        nazwa="Otręby pszenne paszowe",
        kategoria="PRODUKT_UBOCZNY",
        jednostka="kg",
        stawka_vat=Decimal("5.00"),
        typ_granulacji="Gruba frakcja",
        okres_przydatnosci_dni=90,
        cena_bazowa_netto=Decimal("0.950"),
    )
    db.add_all([wheat, corn, flour500, flour750, bran])
    db.flush()

    # 5. Cenniki kontrahentów
    db.add_all([
        CennikKontrahenta(kontrahent_id=buy1.id, asortyment_id=flour500.id, cena_netto=Decimal("2.250"), obowiazuje_od=today - timedelta(days=30)),
        CennikKontrahenta(kontrahent_id=buy1.id, asortyment_id=flour750.id, cena_netto=Decimal("2.420"), obowiazuje_od=today - timedelta(days=30)),
        CennikKontrahenta(kontrahent_id=buy2.id, asortyment_id=flour500.id, cena_netto=Decimal("2.300"), obowiazuje_od=today - timedelta(days=30)),
        CennikKontrahenta(kontrahent_id=buy2.id, asortyment_id=bran.id, cena_netto=Decimal("0.880"), obowiazuje_od=today - timedelta(days=30)),
    ])

    # 6. Lokalizacje magazynowe (silosy, bufor, regały wyrobów gotowych)
    sil1 = LokalizacjaMagazynowa(
        kod="SIL-01",
        nazwa="Silos Zbożowy nr 1 (Pszenica)",
        typ="SILOS",
        strefa="SUROWCE",
        pojemnosc_max_kg=Decimal("250000.000"),
        gestosc_usypowa=Decimal("0.7800"),
    )
    sil2 = LokalizacjaMagazynowa(
        kod="SIL-02",
        nazwa="Silos Zbożowy nr 2 (Zapasowy)",
        typ="SILOS",
        strefa="SUROWCE",
        pojemnosc_max_kg=Decimal("250000.000"),
        gestosc_usypowa=Decimal("0.7600"),
    )
    buf1 = LokalizacjaMagazynowa(
        kod="BUF-01",
        nazwa="Magazyn Buforowy Produkcji",
        typ="BUFOR",
        strefa="BUFOR",
        pojemnosc_max_kg=Decimal("50000.000"),
    )
    reg1 = LokalizacjaMagazynowa(
        kod="REG-A1",
        nazwa="Hala WG — Regał Paletowy A1",
        typ="REGAL_PALETOWY",
        strefa="WYROBY_GOTOWE",
        pojemnosc_max_kg=Decimal("80000.000"),
        liczba_miejsc_palet=80,
    )
    reg2 = LokalizacjaMagazynowa(
        kod="REG-A2",
        nazwa="Hala WG — Regał Paletowy A2",
        typ="REGAL_PALETOWY",
        strefa="WYROBY_GOTOWE",
        pojemnosc_max_kg=Decimal("80000.000"),
        liczba_miejsc_palet=80,
    )
    db.add_all([sil1, sil2, buf1, reg1, reg2])
    db.flush()

    # 7. Początkowe partie i dokument PZ dla spójności historii
    lot_wheat = PartiaMagazynowa(
        kod_partii="LOT-SUR-2026-0001",
        asortyment_id=wheat.id,
        lokalizacja_id=sil1.id,
        dostawca_id=sup1.id,
        masa_poczatkowa_kg=Decimal("24500.000"),
        masa_dostepna_kg=Decimal("24500.000"),
        wilgotnosc_pct=Decimal("13.800"),
        zanieczyszczenia_pct=Decimal("1.400"),
        gestosc_ziarna=Decimal("78.50"),
        liczba_opadania=290,
        data_przyjecia=now - timedelta(days=10),
        status="DOSTEPNA",
    )
    db.add(lot_wheat)
    db.flush()

    pz_init = DokumentMagazynowy(
        typ="PZ",
        numer="PZ/2026/0001",
        status="ZATWIERDZONY",
        kontrahent_id=sup1.id,
        lokalizacja_docelowa_id=sil1.id,
        nr_rejestracyjny="DW 4521K",
        utworzyl_id=op_wag.id,
        zatwierdzil_id=op_wag.id,
        zatwierdzono_utc=now - timedelta(days=10),
        uwagi="Przyjęcie początkowe [DEMO]",
    )
    db.add(pz_init)
    db.flush()

    db.add(
        PozycjaDokumentu(
            dokument_id=pz_init.id,
            lp=1,
            asortyment_id=wheat.id,
            partia_id=lot_wheat.id,
            lokalizacja_id=sil1.id,
            ilosc_fizyczna_kg=Decimal("24500.000"),
            ilosc_rozliczeniowa_kg=Decimal("24500.000"),
            cena_netto=Decimal("0.980"),
            stawka_vat=Decimal("5.00"),
        )
    )
    db.add(
        RuchMagazynowy(
            dokument_id=pz_init.id,
            typ_dokumentu="PZ",
            partia_id=lot_wheat.id,
            lokalizacja_docelowa_id=sil1.id,
            asortyment_id=wheat.id,
            ilosc_kg=Decimal("24500.000"),
            kierunek="PRZYCHOD",
            stan_po_ruchu_kg=Decimal("24500.000"),
            uzytkownik_id=op_wag.id,
        )
    )

    # 8. Receptura BOM (wersja 1 aktywna)
    bom1 = RecepturaBOM(
        kod="BOM-M500",
        nazwa="Przemiał pszenicy na Mąkę typ 500 + Otręby",
        wyrob_docelowy_id=flour500.id,
        wersja=1,
        normatyw_strat_pct=Decimal("2.000"),
        status="AKTYWNA",
        autor_id=inz_prod.id,
    )
    db.add(bom1)
    db.flush()
    db.add_all([
        SkladnikReceptury(
            receptura_id=bom1.id,
            asortyment_id=wheat.id,
            typ_skladnika="SUROWIEC",
            udzial_procentowy=Decimal("100.000"),
        ),
        SkladnikReceptury(
            receptura_id=bom1.id,
            asortyment_id=bran.id,
            typ_skladnika="PRODUKT_UBOCZNY",
            udzial_procentowy=Decimal("24.000"),
        ),
    ])

    # 9. Partie wyrobów gotowych (w tym partia ważna wg FEFO oraz celowo przeterminowana partia do testu blokady!)
    lot_expired = PartiaMagazynowa(
        kod_partii="LOT-WG-2026-EXP1",
        asortyment_id=flour500.id,
        lokalizacja_id=reg2.id,
        partia_zrodlowa_id=lot_wheat.id,
        masa_poczatkowa_kg=Decimal("500.000"),
        masa_dostepna_kg=Decimal("500.000"),
        data_przyjecia=now - timedelta(days=200),
        data_waznosci=today - timedelta(days=15),
        status="DOSTEPNA",
        powod_blokady="Partia przeterminowana (do weryfikacji twardej blokady WZ)",
    )
    lot_fefo1 = PartiaMagazynowa(
        kod_partii="LOT-WG-2026-0001",
        asortyment_id=flour500.id,
        lokalizacja_id=reg1.id,
        partia_zrodlowa_id=lot_wheat.id,
        masa_poczatkowa_kg=Decimal("2000.000"),
        masa_dostepna_kg=Decimal("2000.000"),
        data_przyjecia=now - timedelta(days=20),
        data_waznosci=today + timedelta(days=45),
        status="DOSTEPNA",
    )
    lot_fefo2 = PartiaMagazynowa(
        kod_partii="LOT-WG-2026-0002",
        asortyment_id=flour500.id,
        lokalizacja_id=reg1.id,
        partia_zrodlowa_id=lot_wheat.id,
        masa_poczatkowa_kg=Decimal("3500.000"),
        masa_dostepna_kg=Decimal("3500.000"),
        data_przyjecia=now - timedelta(days=5),
        data_waznosci=today + timedelta(days=150),
        status="DOSTEPNA",
    )
    lot_bran = PartiaMagazynowa(
        kod_partii="LOT-OTR-2026-0001",
        asortyment_id=bran.id,
        lokalizacja_id=reg2.id,
        partia_zrodlowa_id=lot_wheat.id,
        masa_poczatkowa_kg=Decimal("1200.000"),
        masa_dostepna_kg=Decimal("1200.000"),
        data_przyjecia=now - timedelta(days=5),
        data_waznosci=today + timedelta(days=75),
        status="DOSTEPNA",
    )
    db.add_all([lot_expired, lot_fefo1, lot_fefo2, lot_bran])
    db.flush()

    # 10. Otwarte zamówienie sprzedaży gotowe do kompletacji FEFO -> WZ -> FS
    order1 = ZamowienieSprzedazy(
        numer="ZS/2026/0001",
        odbiorca_id=buy1.id,
        data_zamowienia=today,
        data_wydania=today + timedelta(days=1),
        status="NOWE",
        uwagi="Zamówienie demonstracyjne do przejścia ścieżki P3 (FEFO -> WZ -> FS)",
        utworzono_przez_id=users_by_login["fakt_ks"].id,
    )
    db.add(order1)
    db.flush()
    db.add(
        PozycjaZamowienia(
            zamowienie_id=order1.id,
            lp=1,
            asortyment_id=flour500.id,
            ilosc_zamowiona_kg=Decimal("1500.000"),
            ilosc_wydana_kg=Decimal("0.000"),
            cena_netto=Decimal("2.250"),
            cena_z_cennika=True,
        )
    )

    record_audit(
        db,
        akcja="SEED_DEMO",
        zasob="SYSTEM",
        zmiana_stanu={"info": "Zainicjalizowano bezpieczne dane demonstracyjne E-Magazyn ERP/WMS"},
        user=admin,
        adres_ip="127.0.0.1",
        komentarz="Inicjalizacja danych demo",
    )
    db.commit()
