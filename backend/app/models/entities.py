from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


JSON_VARIANT = JSON().with_variant(JSONB(astext_type=Text()), "postgresql")


class Uzytkownik(Base):
    __tablename__ = "uzytkownicy"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    login: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    imie_nazwisko: Mapped[str] = mapped_column(String(120), nullable=False)
    haslo_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    rola: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    czy_aktywny: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    czy_2fa_wymagane: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    utworzono_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)


class KodAutoryzacyjny(Base):
    __tablename__ = "kody_autoryzacyjne"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    kod: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    kierownik_id: Mapped[str] = mapped_column(ForeignKey("uzytkownicy.id"), nullable=False)
    cel: Mapped[str] = mapped_column(String(64), nullable=False, default="AWARIA_WAGI")
    opis: Mapped[str | None] = mapped_column(String(255), nullable=True)
    czy_uzyty: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    wygasa_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    utworzono_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    uzyty_przez_id: Mapped[str | None] = mapped_column(ForeignKey("uzytkownicy.id"), nullable=True)
    uzyty_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class KonfiguracjaSystemowa(Base):
    __tablename__ = "konfiguracja_systemowa"

    klucz: Mapped[str] = mapped_column(String(64), primary_key=True)
    wartosc: Mapped[str] = mapped_column(String(128), nullable=False)
    jednostka: Mapped[str | None] = mapped_column(String(32), nullable=True)
    opis: Mapped[str] = mapped_column(Text, nullable=False)
    zmodyfikowano_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    zmodyfikowano_przez_id: Mapped[str | None] = mapped_column(ForeignKey("uzytkownicy.id"), nullable=True)


class Kontrahent(Base):
    __tablename__ = "kontrahenci"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    nip: Mapped[str] = mapped_column(String(16), unique=True, nullable=False, index=True)
    nazwa: Mapped[str] = mapped_column(String(200), nullable=False)
    adres: Mapped[str] = mapped_column(String(255), nullable=False)
    typ: Mapped[str] = mapped_column(String(24), nullable=False)  # DOSTAWCA | ODBIORCA | OBA
    termin_platnosci_dni: Mapped[int] = mapped_column(Integer, nullable=False, default=14)
    forma_platnosci: Mapped[str] = mapped_column(String(32), nullable=False, default="PRZELEW")
    zrodlo_danych: Mapped[str] = mapped_column(String(32), nullable=False, default="RECZNE")
    czy_aktywny: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    utworzono_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)


class Asortyment(Base):
    __tablename__ = "asortyment"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    kod_ean: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    kod_wewnetrzny: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    nazwa: Mapped[str] = mapped_column(String(160), nullable=False)
    kategoria: Mapped[str] = mapped_column(String(32), nullable=False)  # SUROWIEC | WYROB_GOTOWY | PRODUKT_UBOCZNY
    jednostka: Mapped[str] = mapped_column(String(16), nullable=False, default="kg")
    stawka_vat: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("5.00"))
    wilgotnosc_max_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    zanieczyszczenia_max_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    typ_granulacji: Mapped[str | None] = mapped_column(String(64), nullable=True)
    okres_przydatnosci_dni: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cena_bazowa_netto: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0.000"))
    czy_aktywny: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class CennikKontrahenta(Base):
    __tablename__ = "cenniki_kontrahentow"
    __table_args__ = (UniqueConstraint("kontrahent_id", "asortyment_id", name="uq_cennik_kontrahent_asortyment"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    kontrahent_id: Mapped[str] = mapped_column(ForeignKey("kontrahenci.id"), nullable=False, index=True)
    asortyment_id: Mapped[str] = mapped_column(ForeignKey("asortyment.id"), nullable=False, index=True)
    cena_netto: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    waluta: Mapped[str] = mapped_column(String(8), nullable=False, default="PLN")
    obowiazuje_od: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)

    kontrahent: Mapped[Kontrahent] = relationship()
    asortyment: Mapped[Asortyment] = relationship()


class LokalizacjaMagazynowa(Base):
    __tablename__ = "lokalizacje_magazynowe"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    kod: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    nazwa: Mapped[str] = mapped_column(String(120), nullable=False)
    typ: Mapped[str] = mapped_column(String(32), nullable=False)  # SILOS | BUFOR | REGAL_PALETOWY
    strefa: Mapped[str] = mapped_column(String(32), nullable=False)  # SUROWCE | BUFOR | WYROBY_GOTOWE
    pojemnosc_max_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    gestosc_usypowa: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    liczba_miejsc_palet: Mapped[int | None] = mapped_column(Integer, nullable=True)
    czy_zablokowana: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    powod_blokady: Mapped[str | None] = mapped_column(String(255), nullable=True)
    czy_aktywna: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class PartiaMagazynowa(Base):
    __tablename__ = "partie_magazynowe"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    kod_partii: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    asortyment_id: Mapped[str] = mapped_column(ForeignKey("asortyment.id"), nullable=False, index=True)
    lokalizacja_id: Mapped[str] = mapped_column(ForeignKey("lokalizacje_magazynowe.id"), nullable=False, index=True)
    dostawca_id: Mapped[str | None] = mapped_column(ForeignKey("kontrahenci.id"), nullable=True)
    zlecenie_zrodlowe_id: Mapped[str | None] = mapped_column(
        ForeignKey("zlecenia_produkcyjne.id", use_alter=True, name="fk_partia_zlecenie_zrodlowe"),
        nullable=True,
    )
    partia_zrodlowa_id: Mapped[str | None] = mapped_column(ForeignKey("partie_magazynowe.id"), nullable=True)

    masa_poczatkowa_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    masa_dostepna_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    masa_zarezerwowana_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0.000"))

    wilgotnosc_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    zanieczyszczenia_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    gestosc_ziarna: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    liczba_opadania: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parametry_json: Mapped[dict[str, Any] | None] = mapped_column(JSON_VARIANT, nullable=True)

    data_przyjecia: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    data_waznosci: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DOSTEPNA", index=True)
    powod_blokady: Mapped[str | None] = mapped_column(String(255), nullable=True)

    asortyment: Mapped[Asortyment] = relationship()
    lokalizacja: Mapped[LokalizacjaMagazynowa] = relationship()
    dostawca: Mapped[Kontrahent | None] = relationship()


class PrzyjecieSkupowe(Base):
    __tablename__ = "przyjecia_skupowe"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    numer_roboczy: Mapped[str] = mapped_column(String(48), unique=True, nullable=False, index=True)
    dostawca_id: Mapped[str] = mapped_column(ForeignKey("kontrahenci.id"), nullable=False)
    asortyment_id: Mapped[str] = mapped_column(ForeignKey("asortyment.id"), nullable=False)
    silos_docelowy_id: Mapped[str] = mapped_column(ForeignKey("lokalizacje_magazynowe.id"), nullable=False)
    nr_rejestracyjny: Mapped[str] = mapped_column(String(32), nullable=False)

    masa_brutto_kg: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    masa_tara_kg: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    masa_netto_kg: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    potracenie_kg: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    masa_rozliczeniowa_kg: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)

    wilgotnosc_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    zanieczyszczenia_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    gestosc_ziarna: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    liczba_opadania: Mapped[int | None] = mapped_column(Integer, nullable=True)

    flaga_awarii_wagi: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    kod_autoryzacji_id: Mapped[str | None] = mapped_column(ForeignKey("kody_autoryzacyjne.id"), nullable=True)
    zrodlo_pomiaru: Mapped[str] = mapped_column(String(32), nullable=False, default="SYMULATOR_WAGI")

    czy_przekroczono_prog: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    decyzja_kierownika_wymagana: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    decyzja_kierownika_id: Mapped[str | None] = mapped_column(ForeignKey("uzytkownicy.id"), nullable=True)
    decyzja_komentarz: Mapped[str | None] = mapped_column(String(255), nullable=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="W_TOKU", index=True)
    partia_id: Mapped[str | None] = mapped_column(ForeignKey("partie_magazynowe.id"), nullable=True)
    dokument_pz_id: Mapped[str | None] = mapped_column(ForeignKey("dokumenty_magazynowe.id"), nullable=True)
    operator_id: Mapped[str] = mapped_column(ForeignKey("uzytkownicy.id"), nullable=False)
    utworzono_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    zatwierdzono_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    dostawca: Mapped[Kontrahent] = relationship()
    asortyment: Mapped[Asortyment] = relationship()
    silos_docelowy: Mapped[LokalizacjaMagazynowa] = relationship()


class RecepturaBOM(Base):
    __tablename__ = "receptury_bom"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    kod: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    nazwa: Mapped[str] = mapped_column(String(160), nullable=False)
    wyrob_docelowy_id: Mapped[str] = mapped_column(ForeignKey("asortyment.id"), nullable=False)
    wersja: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    normatyw_strat_pct: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False, default=Decimal("2.000"))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="ROBOCZA", index=True)
    autor_id: Mapped[str] = mapped_column(ForeignKey("uzytkownicy.id"), nullable=False)
    utworzono_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    wyrob_docelowy: Mapped[Asortyment] = relationship()
    skladniki: Mapped[list[SkladnikReceptury]] = relationship(
        back_populates="receptura", cascade="all, delete-orphan"
    )


class SkladnikReceptury(Base):
    __tablename__ = "skladniki_receptury"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    receptura_id: Mapped[str] = mapped_column(ForeignKey("receptury_bom.id", ondelete="CASCADE"), nullable=False)
    asortyment_id: Mapped[str] = mapped_column(ForeignKey("asortyment.id"), nullable=False)
    typ_skladnika: Mapped[str] = mapped_column(String(24), nullable=False)  # SUROWIEC | DODATEK | PRODUKT_UBOCZNY
    udzial_procentowy: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)

    receptura: Mapped[RecepturaBOM] = relationship(back_populates="skladniki")
    asortyment: Mapped[Asortyment] = relationship()


class ZlecenieProdukcyjne(Base):
    __tablename__ = "zlecenia_produkcyjne"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    numer: Mapped[str] = mapped_column(String(48), unique=True, nullable=False, index=True)
    receptura_id: Mapped[str] = mapped_column(ForeignKey("receptury_bom.id"), nullable=False)
    linia_przemialowa: Mapped[str] = mapped_column(String(64), nullable=False, default="Linia Mlynarska L1")
    planowany_zasyp_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)

    partia_surowca_id: Mapped[str] = mapped_column(ForeignKey("partie_magazynowe.id"), nullable=False)
    lokalizacja_zrodlowa_id: Mapped[str] = mapped_column(ForeignKey("lokalizacje_magazynowe.id"), nullable=False)

    ilosc_rw_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0.000"))
    ilosc_pw_glowny_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0.000"))
    ilosc_pw_uboczne_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0.000"))
    strata_odsiew_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0.000"))
    strata_wilgotnosc_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0.000"))
    strata_calkowita_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0.000"))
    roznica_bilansowa_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0.000"))
    roznica_bilansowa_pct: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False, default=Decimal("0.000"))
    czy_bilans_uzgodniony: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    powod_straty: Mapped[str | None] = mapped_column(String(255), nullable=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="W_REALIZACJI", index=True)
    kierownik_akceptacja_id: Mapped[str | None] = mapped_column(ForeignKey("uzytkownicy.id"), nullable=True)
    inzynier_id: Mapped[str] = mapped_column(ForeignKey("uzytkownicy.id"), nullable=False)
    utworzono_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    zakonczono_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    receptura: Mapped[RecepturaBOM] = relationship()
    partia_surowca: Mapped[PartiaMagazynowa] = relationship(foreign_keys=[partia_surowca_id])


class ZamowienieSprzedazy(Base):
    __tablename__ = "zamowienia_sprzedazy"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    numer: Mapped[str] = mapped_column(String(48), unique=True, nullable=False, index=True)
    odbiorca_id: Mapped[str] = mapped_column(ForeignKey("kontrahenci.id"), nullable=False)
    data_zamowienia: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    data_wydania: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="NOWE", index=True)
    uwagi: Mapped[str | None] = mapped_column(Text, nullable=True)
    utworzono_przez_id: Mapped[str] = mapped_column(ForeignKey("uzytkownicy.id"), nullable=False)
    utworzono_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    odbiorca: Mapped[Kontrahent] = relationship()
    pozycje: Mapped[list[PozycjaZamowienia]] = relationship(
        back_populates="zamowienie", cascade="all, delete-orphan"
    )


class PozycjaZamowienia(Base):
    __tablename__ = "pozycje_zamowienia"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    zamowienie_id: Mapped[str] = mapped_column(ForeignKey("zamowienia_sprzedazy.id", ondelete="CASCADE"), nullable=False)
    lp: Mapped[int] = mapped_column(Integer, nullable=False)
    asortyment_id: Mapped[str] = mapped_column(ForeignKey("asortyment.id"), nullable=False)
    ilosc_zamowiona_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    ilosc_wydana_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0.000"))
    cena_netto: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    cena_z_cennika: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    zamowienie: Mapped[ZamowienieSprzedazy] = relationship(back_populates="pozycje")
    asortyment: Mapped[Asortyment] = relationship()


class DokumentMagazynowy(Base):
    __tablename__ = "dokumenty_magazynowe"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    typ: Mapped[str] = mapped_column(String(16), nullable=False, index=True)  # PZ, RW, PW, WZ, MM, PW-kor, RW-kor
    numer: Mapped[str] = mapped_column(String(48), unique=True, nullable=False, index=True)
    data_wystawienia: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="ROBOCZY", index=True)

    kontrahent_id: Mapped[str | None] = mapped_column(ForeignKey("kontrahenci.id"), nullable=True)
    lokalizacja_zrodlowa_id: Mapped[str | None] = mapped_column(ForeignKey("lokalizacje_magazynowe.id"), nullable=True)
    lokalizacja_docelowa_id: Mapped[str | None] = mapped_column(ForeignKey("lokalizacje_magazynowe.id"), nullable=True)
    zlecenie_id: Mapped[str | None] = mapped_column(ForeignKey("zlecenia_produkcyjne.id"), nullable=True)
    zamowienie_id: Mapped[str | None] = mapped_column(ForeignKey("zamowienia_sprzedazy.id"), nullable=True)

    czy_zafakturowany: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    faktura_id: Mapped[str | None] = mapped_column(ForeignKey("faktury_vat.id"), nullable=True)
    nr_rejestracyjny: Mapped[str | None] = mapped_column(String(32), nullable=True)
    data_wydania: Mapped[date | None] = mapped_column(Date, nullable=True)
    flaga_awarii_wagi: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    liczba_wydrukow: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    uwagi: Mapped[str | None] = mapped_column(Text, nullable=True)

    utworzyl_id: Mapped[str] = mapped_column(ForeignKey("uzytkownicy.id"), nullable=False)
    zatwierdzil_id: Mapped[str | None] = mapped_column(ForeignKey("uzytkownicy.id"), nullable=True)
    utworzono_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    zatwierdzono_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    kontrahent: Mapped[Kontrahent | None] = relationship()
    pozycje: Mapped[list[PozycjaDokumentu]] = relationship(
        back_populates="dokument", cascade="all, delete-orphan"
    )


class PozycjaDokumentu(Base):
    __tablename__ = "pozycje_dokumentu"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    dokument_id: Mapped[str] = mapped_column(ForeignKey("dokumenty_magazynowe.id", ondelete="CASCADE"), nullable=False)
    lp: Mapped[int] = mapped_column(Integer, nullable=False)
    asortyment_id: Mapped[str] = mapped_column(ForeignKey("asortyment.id"), nullable=False)
    partia_id: Mapped[str | None] = mapped_column(ForeignKey("partie_magazynowe.id"), nullable=True)
    lokalizacja_id: Mapped[str | None] = mapped_column(ForeignKey("lokalizacje_magazynowe.id"), nullable=True)
    ilosc_fizyczna_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    ilosc_rozliczeniowa_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    cena_netto: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0.000"))
    stawka_vat: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("5.00"))
    czy_cena_zmieniona_recznie: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    powod_zmiany_ceny: Mapped[str | None] = mapped_column(String(255), nullable=True)
    odstepstwo_fefo_powod: Mapped[str | None] = mapped_column(String(255), nullable=True)

    dokument: Mapped[DokumentMagazynowy] = relationship(back_populates="pozycje")
    asortyment: Mapped[Asortyment] = relationship()
    partia: Mapped[PartiaMagazynowa | None] = relationship()
    lokalizacja: Mapped[LokalizacjaMagazynowa | None] = relationship()


class FakturaVAT(Base):
    __tablename__ = "faktury_vat"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    typ: Mapped[str] = mapped_column(String(16), nullable=False, default="FS", index=True)  # FS | FZ | FS-KOR
    numer: Mapped[str] = mapped_column(String(48), unique=True, nullable=False, index=True)
    korekta_do_faktury_id: Mapped[str | None] = mapped_column(ForeignKey("faktury_vat.id"), nullable=True)
    kontrahent_id: Mapped[str] = mapped_column(ForeignKey("kontrahenci.id"), nullable=False)
    data_wystawienia: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    termin_platnosci: Mapped[date] = mapped_column(Date, nullable=False)
    forma_platnosci: Mapped[str] = mapped_column(String(32), nullable=False, default="PRZELEW")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="ROBOCZA", index=True)

    wartosc_netto: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0.000"))
    wartosc_vat: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0.000"))
    wartosc_brutto: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0.000"))

    liczba_wydrukow: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    uwagi: Mapped[str | None] = mapped_column(Text, nullable=True)
    utworzyl_id: Mapped[str] = mapped_column(ForeignKey("uzytkownicy.id"), nullable=False)
    zatwierdzil_id: Mapped[str | None] = mapped_column(ForeignKey("uzytkownicy.id"), nullable=True)
    utworzono_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    zatwierdzono_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    kontrahent: Mapped[Kontrahent] = relationship()
    pozycje: Mapped[list[PozycjaFaktury]] = relationship(
        back_populates="faktura", cascade="all, delete-orphan"
    )


class PozycjaFaktury(Base):
    __tablename__ = "pozycje_faktury"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    faktura_id: Mapped[str] = mapped_column(ForeignKey("faktury_vat.id", ondelete="CASCADE"), nullable=False)
    lp: Mapped[int] = mapped_column(Integer, nullable=False)
    asortyment_id: Mapped[str] = mapped_column(ForeignKey("asortyment.id"), nullable=False)
    dokument_wz_id: Mapped[str | None] = mapped_column(ForeignKey("dokumenty_magazynowe.id"), nullable=True)
    ilosc_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    cena_netto: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    cena_z_cennika: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    czy_cena_zmieniona_recznie: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    powod_zmiany_ceny: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stawka_vat: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    wartosc_netto: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    wartosc_vat: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    wartosc_brutto: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)

    faktura: Mapped[FakturaVAT] = relationship(back_populates="pozycje")
    asortyment: Mapped[Asortyment] = relationship()


class ArkuszInwentaryzacji(Base):
    __tablename__ = "arkusze_inwentaryzacji"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    numer: Mapped[str] = mapped_column(String(48), unique=True, nullable=False, index=True)
    zakres_strefa: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="OTWARTA", index=True)
    kierownik_id: Mapped[str] = mapped_column(ForeignKey("uzytkownicy.id"), nullable=False)
    rozliczyl_id: Mapped[str | None] = mapped_column(ForeignKey("uzytkownicy.id"), nullable=True)
    komentarz: Mapped[str | None] = mapped_column(Text, nullable=True)
    utworzono_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    zamknieto_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    pozycje: Mapped[list[PozycjaInwentaryzacji]] = relationship(
        back_populates="arkusz", cascade="all, delete-orphan"
    )


class PozycjaInwentaryzacji(Base):
    __tablename__ = "pozycje_inwentaryzacji"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    arkusz_id: Mapped[str] = mapped_column(ForeignKey("arkusze_inwentaryzacji.id", ondelete="CASCADE"), nullable=False)
    lokalizacja_id: Mapped[str] = mapped_column(ForeignKey("lokalizacje_magazynowe.id"), nullable=False)
    partia_id: Mapped[str] = mapped_column(ForeignKey("partie_magazynowe.id"), nullable=False)
    asortyment_id: Mapped[str] = mapped_column(ForeignKey("asortyment.id"), nullable=False)
    stan_ewidencyjny_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    stan_spisany_kg: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    roznica_kg: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    podstawa_pomiaru: Mapped[str] = mapped_column(String(64), nullable=False, default="SPIS_Z_NATURY")
    uzasadnienie: Mapped[str | None] = mapped_column(String(255), nullable=True)

    arkusz: Mapped[ArkuszInwentaryzacji] = relationship(back_populates="pozycje")
    lokalizacja: Mapped[LokalizacjaMagazynowa] = relationship()
    partia: Mapped[PartiaMagazynowa] = relationship()
    asortyment: Mapped[Asortyment] = relationship()


class RuchMagazynowy(Base):
    __tablename__ = "ruchy_magazynowe"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    dokument_id: Mapped[str] = mapped_column(ForeignKey("dokumenty_magazynowe.id"), nullable=False, index=True)
    typ_dokumentu: Mapped[str] = mapped_column(String(16), nullable=False)
    partia_id: Mapped[str] = mapped_column(ForeignKey("partie_magazynowe.id"), nullable=False, index=True)
    lokalizacja_zrodlowa_id: Mapped[str | None] = mapped_column(ForeignKey("lokalizacje_magazynowe.id"), nullable=True)
    lokalizacja_docelowa_id: Mapped[str | None] = mapped_column(ForeignKey("lokalizacje_magazynowe.id"), nullable=True)
    asortyment_id: Mapped[str] = mapped_column(ForeignKey("asortyment.id"), nullable=False)
    ilosc_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    kierunek: Mapped[str] = mapped_column(String(24), nullable=False)  # PRZYCHOD | ROZCHOD | TRANSFER | KOREKTA_PLUS | KOREKTA_MINUS
    stan_po_ruchu_kg: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    uzytkownik_id: Mapped[str] = mapped_column(ForeignKey("uzytkownicy.id"), nullable=False)
    utworzono_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, index=True)


class WpisAudytowy(Base):
    """Dziennik audytowy Append-Only (tylko dopisywanie na poziomie warstwy aplikacji)."""

    __tablename__ = "wpisy_audytowe"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    znacznik_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, index=True)
    uzytkownik_id: Mapped[str | None] = mapped_column(ForeignKey("uzytkownicy.id"), nullable=True)
    login: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rola: Mapped[str | None] = mapped_column(String(32), nullable=True)
    adres_ip: Mapped[str] = mapped_column(String(64), nullable=False, default="127.0.0.1")
    akcja: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    zasob: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    zasob_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    zmiana_stanu: Mapped[dict[str, Any]] = mapped_column(JSON_VARIANT, nullable=False)
    komentarz: Mapped[str | None] = mapped_column(String(255), nullable=True)
