from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    login: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=4, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut


class UserOut(BaseModel):
    id: str
    login: str
    imie_nazwisko: str
    rola: str
    czy_aktywny: bool
    czy_2fa_wymagane: bool

    model_config = {"from_attributes": True}


class UserCreateRequest(BaseModel):
    login: str = Field(min_length=3, max_length=64)
    imie_nazwisko: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=8, max_length=128)
    rola: str
    czy_aktywny: bool = True


class UserUpdateRequest(BaseModel):
    imie_nazwisko: str | None = None
    rola: str | None = None
    czy_aktywny: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


class ConfigUpdateRequest(BaseModel):
    wartosc: str = Field(min_length=1, max_length=128)


class AuthCodeCreateRequest(BaseModel):
    cel: str = "AWARIA_WAGI"
    opis: str | None = None
    waznosc_minuty: int = Field(default=60, ge=5, le=10080)


class KontrahentCreate(BaseModel):
    nip: str = Field(min_length=10, max_length=16)
    nazwa: str = Field(min_length=2, max_length=200)
    adres: str = Field(min_length=3, max_length=255)
    typ: str = Field(pattern="^(DOSTAWCA|ODBIORCA|OBA)$")
    termin_platnosci_dni: int = Field(default=14, ge=0, le=180)
    forma_platnosci: str = Field(default="PRZELEW", pattern="^(PRZELEW|GOTOWKA|KARTA)$")
    zrodlo_danych: str = Field(default="RECZNE")


class AsortymentCreate(BaseModel):
    kod_ean: str = Field(min_length=8, max_length=32)
    kod_wewnetrzny: str = Field(min_length=2, max_length=32)
    nazwa: str = Field(min_length=2, max_length=160)
    kategoria: str = Field(pattern="^(SUROWIEC|WYROB_GOTOWY|PRODUKT_UBOCZNY)$")
    jednostka: str = "kg"
    stawka_vat: Decimal = Field(default=Decimal("5.00"), ge=0, le=99)
    wilgotnosc_max_pct: Decimal | None = None
    zanieczyszczenia_max_pct: Decimal | None = None
    typ_granulacji: str | None = None
    okres_przydatnosci_dni: int | None = None
    cena_bazowa_netto: Decimal = Field(default=Decimal("0.000"), ge=0)


class CennikUpsertRequest(BaseModel):
    kontrahent_id: str
    asortyment_id: str
    cena_netto: Decimal = Field(gt=0)
    waluta: str = "PLN"


class LokalizacjaCreate(BaseModel):
    kod: str = Field(min_length=2, max_length=32)
    nazwa: str = Field(min_length=2, max_length=120)
    typ: str = Field(pattern="^(SILOS|BUFOR|REGAL_PALETOWY)$")
    strefa: str = Field(pattern="^(SUROWCE|BUFOR|WYROBY_GOTOWE)$")
    pojemnosc_max_kg: Decimal = Field(gt=0)
    gestosc_usypowa: Decimal | None = None
    liczba_miejsc_palet: int | None = None


class ScaleReadRequest(BaseModel):
    symuluj_awarie: bool = False
    masa_brutto_kg: Decimal | None = None


class PrzyjecieCreateRequest(BaseModel):
    dostawca_id: str
    asortyment_id: str
    silos_docelowy_id: str
    nr_rejestracyjny: str = Field(min_length=3, max_length=32)
    tryb_reczny: bool = False
    kod_autoryzacji: str | None = None
    masa_brutto_kg: Decimal = Field(gt=0)


class PrzyjecieJakoscRequest(BaseModel):
    wilgotnosc_pct: Decimal = Field(ge=0, le=50)
    zanieczyszczenia_pct: Decimal = Field(ge=0, le=50)
    gestosc_ziarna: Decimal | None = Field(default=None, gt=0)
    liczba_opadania: int | None = Field(default=None, gt=0)


class PrzyjecieDecyzjaRequest(BaseModel):
    zatwierdz: bool
    komentarz: str = Field(min_length=3, max_length=255)


class PrzyjecieTaraPzRequest(BaseModel):
    tryb_reczny: bool = False
    kod_autoryzacji: str | None = None
    masa_tara_kg: Decimal = Field(gt=0)
    uwagi: str | None = None


class BomComponentIn(BaseModel):
    asortyment_id: str
    typ_skladnika: str = Field(pattern="^(SUROWIEC|DODATEK|PRODUKT_UBOCZNY)$")
    udzial_procentowy: Decimal = Field(gt=0, le=100)


class BomCreateRequest(BaseModel):
    kod: str = Field(min_length=2, max_length=48)
    nazwa: str = Field(min_length=3, max_length=160)
    wyrob_docelowy_id: str
    normatyw_strat_pct: Decimal = Field(default=Decimal("2.000"), ge=0, le=30)
    skladniki: list[BomComponentIn] = Field(min_length=1)


class ZlecenieCreateRequest(BaseModel):
    receptura_id: str
    linia_przemialowa: str = Field(default="Linia Mlynarska L1", min_length=2, max_length=64)
    planowany_zasyp_kg: Decimal = Field(gt=0)
    partia_surowca_id: str


class ByProductYieldIn(BaseModel):
    asortyment_id: str
    lokalizacja_id: str
    ilosc_kg: Decimal = Field(gt=0)
    data_waznosci: date | None = None


class ZlecenieRozliczRequest(BaseModel):
    wyrob_glowny_kg: Decimal = Field(gt=0)
    lokalizacja_docelowa_id: str
    data_waznosci_wyrobu: date
    produkty_uboczne: list[ByProductYieldIn] = Field(default_factory=list)
    strata_odsiew_kg: Decimal = Field(ge=0)
    strata_wilgotnosc_kg: Decimal = Field(ge=0)
    powod_straty: str | None = None


class ZlecenieAkceptacjaStratyRequest(BaseModel):
    akceptuj: bool
    komentarz: str = Field(min_length=3, max_length=255)


class ZlecenieKorektaRwRequest(BaseModel):
    korekta_rw_kg: Decimal  # dodatnia = dopisanie rozchodu (RW), ujemna = zwrot (RW-kor)
    powod: str = Field(min_length=3, max_length=255)


class ZamowieniePozycjaIn(BaseModel):
    asortyment_id: str
    ilosc_zamowiona_kg: Decimal = Field(gt=0)


class ZamowienieCreateRequest(BaseModel):
    odbiorca_id: str
    data_wydania: date
    uwagi: str | None = None
    pozycje: list[ZamowieniePozycjaIn] = Field(min_length=1)


class WzPickLineIn(BaseModel):
    asortyment_id: str
    partia_id: str
    ilosc_kg: Decimal = Field(gt=0)
    odstepstwo_fefo_powod: str | None = None


class WzCreateApproveRequest(BaseModel):
    zamowienie_id: str
    data_wydania: date
    nr_rejestracyjny: str | None = None
    uwagi: str | None = None
    pozycje: list[WzPickLineIn] = Field(min_length=1)


class InvoicePriceOverrideIn(BaseModel):
    asortyment_id: str
    nowa_cena_netto: Decimal = Field(gt=0)
    powod_zmiany: str = Field(min_length=3, max_length=255)


class FakturaFromWzRequest(BaseModel):
    wz_ids: list[str] = Field(min_length=1)
    termin_platnosci: date | None = None
    forma_platnosci: str | None = None
    uwagi: str | None = None
    nadpisania_cen: list[InvoicePriceOverrideIn] = Field(default_factory=list)


class FakturaKorektaRequest(BaseModel):
    nowe_ceny: list[InvoicePriceOverrideIn] = Field(min_length=1)
    uwagi: str = Field(min_length=3, max_length=255)


class FzCreateRequest(BaseModel):
    kontrahent_id: str
    asortyment_id: str
    ilosc_kg: Decimal = Field(gt=0)
    cena_netto: Decimal = Field(gt=0)
    stawka_vat: Decimal = Field(default=Decimal("5.00"), ge=0, le=99)
    uwagi: str | None = None


class MmTransferRequest(BaseModel):
    partia_id: str
    lokalizacja_docelowa_id: str
    ilosc_kg: Decimal = Field(gt=0)
    uwagi: str | None = None


class InwentaryzacjaStartRequest(BaseModel):
    zakres_strefa: str = Field(pattern="^(SUROWCE|BUFOR|WYROBY_GOTOWE)$")
    komentarz: str | None = None


class InwentaryzacjaCountLineIn(BaseModel):
    pozycja_id: str
    stan_spisany_kg: Decimal = Field(ge=0)
    podstawa_pomiaru: str = Field(default="SPIS_Z_NATURY", max_length=64)
    uzasadnienie: str | None = None


class InwentaryzacjaCountsRequest(BaseModel):
    pozycje: list[InwentaryzacjaCountLineIn] = Field(min_length=1)


class InwentaryzacjaCloseRequest(BaseModel):
    komentarz: str = Field(min_length=3, max_length=255)


class CancelDocRequest(BaseModel):
    powod: str = Field(min_length=3, max_length=255)


class AuditOut(BaseModel):
    id: str
    znacznik_utc: datetime
    login: str | None
    rola: str | None
    adres_ip: str
    akcja: str
    zasob: str
    zasob_id: str | None
    zmiana_stanu: dict[str, Any]
    komentarz: str | None

    model_config = {"from_attributes": True}
