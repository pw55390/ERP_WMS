from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.db.session import get_db
from app.models.entities import (
    Asortyment,
    DokumentMagazynowy,
    KodAutoryzacyjny,
    Kontrahent,
    LokalizacjaMagazynowa,
    PartiaMagazynowa,
    PozycjaDokumentu,
    PrzyjecieSkupowe,
    RuchMagazynowy,
    Uzytkownik,
)
from app.schemas.dto import (
    PrzyjecieCreateRequest,
    PrzyjecieDecyzjaRequest,
    PrzyjecieJakoscRequest,
    PrzyjecieTaraPzRequest,
    ScaleReadRequest,
)
from app.services.adapters import AdapterWagi
from app.services.audit import client_ip_from_request, record_audit
from app.services.common import (
    D_ZERO,
    get_config_decimal,
    get_location_occupied_kg,
    lock_location_for_update,
    next_batch_code,
    next_document_number,
    q3,
)

router = APIRouter(prefix="/api/p1", tags=["P1 - Skup i przyjęcie"])


def _serialize_przyjecie(p: PrzyjecieSkupowe, db: Session) -> dict:
    pz_num = None
    if p.dokument_pz_id:
        doc = db.get(DokumentMagazynowy, p.dokument_pz_id)
        pz_num = doc.numer if doc else None
    lot_code = None
    if p.partia_id:
        lot = db.get(PartiaMagazynowa, p.partia_id)
        lot_code = lot.kod_partii if lot else None
    return {
        "id": p.id,
        "numer_roboczy": p.numer_roboczy,
        "dostawca_id": p.dostawca_id,
        "dostawca_nazwa": p.dostawca.nazwa,
        "asortyment_id": p.asortyment_id,
        "asortyment_nazwa": p.asortyment.nazwa,
        "silos_docelowy_id": p.silos_docelowy_id,
        "silos_kod": p.silos_docelowy.kod,
        "nr_rejestracyjny": p.nr_rejestracyjny,
        "masa_brutto_kg": str(p.masa_brutto_kg) if p.masa_brutto_kg is not None else None,
        "masa_tara_kg": str(p.masa_tara_kg) if p.masa_tara_kg is not None else None,
        "masa_netto_kg": str(p.masa_netto_kg) if p.masa_netto_kg is not None else None,
        "potracenie_kg": str(p.potracenie_kg) if p.potracenie_kg is not None else None,
        "masa_rozliczeniowa_kg": str(p.masa_rozliczeniowa_kg) if p.masa_rozliczeniowa_kg is not None else None,
        "wilgotnosc_pct": str(p.wilgotnosc_pct) if p.wilgotnosc_pct is not None else None,
        "zanieczyszczenia_pct": str(p.zanieczyszczenia_pct) if p.zanieczyszczenia_pct is not None else None,
        "gestosc_ziarna": str(p.gestosc_ziarna) if p.gestosc_ziarna is not None else None,
        "liczba_opadania": p.liczba_opadania,
        "flaga_awarii_wagi": p.flaga_awarii_wagi,
        "zrodlo_pomiaru": p.zrodlo_pomiaru,
        "czy_przekroczono_prog": p.czy_przekroczono_prog,
        "decyzja_kierownika_wymagana": p.decyzja_kierownika_wymagana,
        "decyzja_komentarz": p.decyzja_komentarz,
        "status": p.status,
        "partia_id": p.partia_id,
        "kod_partii": lot_code,
        "dokument_pz_id": p.dokument_pz_id,
        "dokument_pz_numer": pz_num,
        "utworzono_utc": p.utworzono_utc.isoformat(),
        "zatwierdzono_utc": p.zatwierdzono_utc.isoformat() if p.zatwierdzono_utc else None,
    }


def _consume_auth_code(db: Session, code_str: str | None, user: Uzytkownik) -> KodAutoryzacyjny:
    if not code_str or not code_str.strip():
        raise HTTPException(
            status_code=403,
            detail="Ręczne wprowadzenie masy przy awarii wagi wymaga podania kodu autoryzacyjnego KIER_MAG (UC-01.5).",
        )
    code = db.scalar(select(KodAutoryzacyjny).where(KodAutoryzacyjny.kod == code_str.strip()))
    now = datetime.now(timezone.utc)
    if code is None or code.czy_uzyty:
        raise HTTPException(status_code=403, detail="Nieprawidłowy lub już wykorzystany kod autoryzacyjny kierownika.")
    expires = code.wygasa_utc if code.wygasa_utc.tzinfo else code.wygasa_utc.replace(tzinfo=timezone.utc)
    if expires < now:
        raise HTTPException(status_code=403, detail="Kod autoryzacyjny kierownika wygasł.")
    code.czy_uzyty = True
    code.uzyty_przez_id = user.id
    code.uzyty_utc = now
    return code


@router.post("/waga/odczyt-brutto")
def scale_read_gross(
    payload: ScaleReadRequest,
    user: Uzytkownik = Depends(require_roles("OP_WAG", "KIER_MAG")),
):
    reading = AdapterWagi().odczytaj_brutto(symuluj_awarie=payload.symuluj_awarie)
    return {
        "masa_kg": str(reading.masa_kg),
        "protokol": reading.protokol,
        "tryb": reading.tryb,
        "status_urzadzenia": reading.status_urzadzenia,
        "komunikat": reading.komunikat,
    }


@router.post("/waga/odczyt-tara")
def scale_read_tare(
    payload: ScaleReadRequest,
    user: Uzytkownik = Depends(require_roles("OP_WAG", "KIER_MAG")),
):
    brutto = payload.masa_brutto_kg or Decimal("38000.000")
    reading = AdapterWagi().odczytaj_tare(brutto, symuluj_awarie=payload.symuluj_awarie)
    return {
        "masa_kg": str(reading.masa_kg),
        "protokol": reading.protokol,
        "tryb": reading.tryb,
        "status_urzadzenia": reading.status_urzadzenia,
        "komunikat": reading.komunikat,
    }


@router.get("/przyjecia")
def list_przyjecia(
    status_filter: str | None = None,
    user: Uzytkownik = Depends(require_roles("OP_WAG", "KIER_MAG", "FAKT_KS", "ADMIN")),
    db: Session = Depends(get_db),
):
    stmt = select(PrzyjecieSkupowe).order_by(PrzyjecieSkupowe.utworzono_utc.desc())
    if status_filter:
        stmt = stmt.where(PrzyjecieSkupowe.status == status_filter)
    rows = db.scalars(stmt).all()
    return [_serialize_przyjecie(p, db) for p in rows]


@router.post("/przyjecia", status_code=status.HTTP_201_CREATED)
def create_przyjecie(
    payload: PrzyjecieCreateRequest,
    request: Request,
    user: Uzytkownik = Depends(require_roles("OP_WAG", "KIER_MAG")),
    db: Session = Depends(get_db),
):
    supplier = db.get(Kontrahent, payload.dostawca_id)
    if supplier is None or supplier.typ not in ("DOSTAWCA", "OBA"):
        raise HTTPException(status_code=422, detail="Wybrany kontrahent nie istnieje lub nie jest dostawcą.")
    item = db.get(Asortyment, payload.asortyment_id)
    if item is None or item.kategoria != "SUROWIEC":
        raise HTTPException(status_code=422, detail="Wybrany asortyment musi być surowcem skupowym.")
    silo = db.get(LokalizacjaMagazynowa, payload.silos_docelowy_id)
    if silo is None or silo.typ != "SILOS":
        raise HTTPException(status_code=422, detail="Docelowa lokalizacja musi być silosem zbożowym.")
    if silo.czy_zablokowana:
        raise HTTPException(status_code=409, detail=f"Silos {silo.kod} jest zablokowany ({silo.powod_blokady}).")

    auth_code = None
    zrodlo = "SYMULATOR_WAGI"
    if payload.tryb_reczny:
        auth_code = _consume_auth_code(db, payload.kod_autoryzacji, user)
        zrodlo = "RECZNE_AWARIA"

    seq = db.scalars(select(PrzyjecieSkupowe.id)).all()
    numer_roboczy = f"SKUP-{datetime.now(timezone.utc).year}-{len(seq) + 1:04d}"

    przyjecie = PrzyjecieSkupowe(
        numer_roboczy=numer_roboczy,
        dostawca_id=supplier.id,
        asortyment_id=item.id,
        silos_docelowy_id=silo.id,
        nr_rejestracyjny=payload.nr_rejestracyjny.strip().upper(),
        masa_brutto_kg=q3(payload.masa_brutto_kg),
        flaga_awarii_wagi=payload.tryb_reczny,
        kod_autoryzacji_id=auth_code.id if auth_code else None,
        zrodlo_pomiaru=zrodlo,
        status="W_TOKU",
        operator_id=user.id,
    )
    db.add(przyjecie)
    db.flush()

    record_audit(
        db,
        akcja="SKUP_REJESTRACJA_BRUTTO" if not payload.tryb_reczny else "SKUP_RECZNA_WAGA_BRUTTO",
        zasob="PRZYJECIE_SKUP",
        zasob_id=przyjecie.id,
        zmiana_stanu={
            "numer_roboczy": numer_roboczy,
            "masa_brutto_kg": str(przyjecie.masa_brutto_kg),
            "flaga_awarii_wagi": przyjecie.flaga_awarii_wagi,
            "zrodlo_pomiaru": zrodlo,
        },
        user=user,
        adres_ip=client_ip_from_request(request),
        komentarz="Tryb awaryjny z kodem KIER_MAG" if payload.tryb_reczny else None,
    )
    db.commit()
    db.refresh(przyjecie)
    return _serialize_przyjecie(przyjecie, db)


@router.post("/przyjecia/{przyjecie_id}/jakosc")
def submit_quality(
    przyjecie_id: str,
    payload: PrzyjecieJakoscRequest,
    request: Request,
    user: Uzytkownik = Depends(require_roles("OP_WAG", "KIER_MAG")),
    db: Session = Depends(get_db),
):
    p = db.get(PrzyjecieSkupowe, przyjecie_id)
    if p is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono przyjęcia skupowego.")
    if p.status in ("ZATWIERDZONE", "ODRZUCONE", "ANULOWANE"):
        raise HTTPException(status_code=409, detail=f"Przyjęcie ma już końcowy status {p.status}.")

    prog_wilg = get_config_decimal(db, "prog_wilgotnosci_pct", Decimal("15.000"))
    prog_zan = get_config_decimal(db, "prog_zanieczyszczen_pct", Decimal("4.000"))

    wilg = q3(payload.wilgotnosc_pct)
    zan = q3(payload.zanieczyszczenia_pct)
    exceeded = wilg > prog_wilg or zan > prog_zan

    p.wilgotnosc_pct = wilg
    p.zanieczyszczenia_pct = zan
    p.gestosc_ziarna = payload.gestosc_ziarna
    p.liczba_opadania = payload.liczba_opadania
    p.czy_przekroczono_prog = exceeded
    p.decyzja_kierownika_wymagana = exceeded
    p.status = "OCZEKUJE_KIEROWNIKA" if exceeded else "W_TOKU"

    record_audit(
        db,
        akcja="SKUP_METRYKA_JAKOSCIOWA",
        zasob="PRZYJECIE_SKUP",
        zasob_id=p.id,
        zmiana_stanu={
            "wilgotnosc_pct": str(wilg),
            "prog_wilgotnosci_pct": str(prog_wilg),
            "zanieczyszczenia_pct": str(zan),
            "prog_zanieczyszczen_pct": str(prog_zan),
            "przekroczono": exceeded,
        },
        user=user,
        adres_ip=client_ip_from_request(request),
    )
    db.commit()
    db.refresh(p)
    return {
        "przyjecie": _serialize_przyjecie(p, db),
        "progi": {"prog_wilgotnosci_pct": str(prog_wilg), "prog_zanieczyszczen_pct": str(prog_zan)},
    }


@router.post("/przyjecia/{przyjecie_id}/decyzja-kierownika")
def manager_quality_decision(
    przyjecie_id: str,
    payload: PrzyjecieDecyzjaRequest,
    request: Request,
    kierownik: Uzytkownik = Depends(require_roles("KIER_MAG")),
    db: Session = Depends(get_db),
):
    p = db.get(PrzyjecieSkupowe, przyjecie_id)
    if p is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono przyjęcia skupowego.")
    if p.status != "OCZEKUJE_KIEROWNIKA":
        raise HTTPException(status_code=409, detail="To przyjęcie nie oczekuje na decyzję kierownika.")

    p.decyzja_kierownika_id = kierownik.id
    p.decyzja_komentarz = payload.komentarz.strip()
    if payload.zatwierdz:
        p.decyzja_kierownika_wymagana = False
        p.status = "W_TOKU"
        akcja = "SKUP_ZGODA_KIEROWNIKA"
    else:
        p.status = "ODRZUCONE"
        akcja = "SKUP_ODRZUCENIE_DOSTAWY"

    record_audit(
        db,
        akcja=akcja,
        zasob="PRZYJECIE_SKUP",
        zasob_id=p.id,
        zmiana_stanu={"zatwierdzono": payload.zatwierdz, "komentarz": p.decyzja_komentarz},
        user=kierownik,
        adres_ip=client_ip_from_request(request),
    )
    db.commit()
    db.refresh(p)
    return _serialize_przyjecie(p, db)


@router.post("/przyjecia/{przyjecie_id}/tara-i-pz")
def finalize_tare_and_pz(
    przyjecie_id: str,
    payload: PrzyjecieTaraPzRequest,
    request: Request,
    user: Uzytkownik = Depends(require_roles("OP_WAG", "KIER_MAG")),
    db: Session = Depends(get_db),
):
    p = db.get(PrzyjecieSkupowe, przyjecie_id)
    if p is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono przyjęcia skupowego.")
    if p.status == "OCZEKUJE_KIEROWNIKA":
        raise HTTPException(
            status_code=409,
            detail="Przekroczono dopuszczalny próg jakościowy. Wymagana decyzja Kierownika Magazynu przed wystawieniem PZ.",
        )
    if p.status != "W_TOKU":
        raise HTTPException(status_code=409, detail=f"Nie można zatwierdzić PZ dla przyjęcia w statusie {p.status}.")
    if p.wilgotnosc_pct is None or p.zanieczyszczenia_pct is None:
        raise HTTPException(status_code=422, detail="Przed wystawieniem PZ należy wprowadzić metrykę jakościową ziarna.")
    if p.masa_brutto_kg is None:
        raise HTTPException(status_code=422, detail="Brak zarejestrowanej masy brutto.")

    tara = q3(payload.masa_tara_kg)
    if tara <= D_ZERO or tara >= p.masa_brutto_kg:
        raise HTTPException(
            status_code=422,
            detail=f"Nieprawidłowa tara ({tara} kg): musi być > 0 i mniejsza od masy brutto ({p.masa_brutto_kg} kg).",
        )

    if payload.tryb_reczny:
        _consume_auth_code(db, payload.kod_autoryzacji, user)
        p.flaga_awarii_wagi = True
        p.zrodlo_pomiaru = "RECZNE_AWARIA"

    silo = lock_location_for_update(db, p.silos_docelowy_id)
    if silo is None or silo.czy_zablokowana:
        raise HTTPException(status_code=409, detail="Docelowy silos jest zablokowany (np. inwentaryzacja) lub niedostępny.")

    masa_netto = q3(p.masa_brutto_kg - tara)
    occupied = get_location_occupied_kg(db, silo.id)
    if occupied + masa_netto > silo.pojemnosc_max_kg:
        raise HTTPException(
            status_code=409,
            detail=f"Brak wystarczającej pojemności w silosie {silo.kod} (wolne: {silo.pojemnosc_max_kg - occupied} kg, dostawa: {masa_netto} kg).",
        )

    # Przeliczenie na masę rozliczeniową (potrącenie za nadmiar wilgotności ponad 14% i zanieczyszczeń ponad 1%)
    nadmiar_wilg = max(Decimal("0"), p.wilgotnosc_pct - Decimal("14.0"))
    nadmiar_zan = max(Decimal("0"), p.zanieczyszczenia_pct - Decimal("1.0"))
    wspolczynnik_potracenia = (nadmiar_wilg + nadmiar_zan) / Decimal("100")
    potracenie = q3(masa_netto * wspolczynnik_potracenia)
    masa_rozliczeniowa = q3(masa_netto - potracenie)

    now = datetime.now(timezone.utc)
    lot_code = next_batch_code(db, "LOT-SUR")
    pz_number = next_document_number(db, "PZ", DokumentMagazynowy)

    lot = PartiaMagazynowa(
        kod_partii=lot_code,
        asortyment_id=p.asortyment_id,
        lokalizacja_id=silo.id,
        dostawca_id=p.dostawca_id,
        masa_poczatkowa_kg=masa_netto,
        masa_dostepna_kg=masa_netto,
        wilgotnosc_pct=p.wilgotnosc_pct,
        zanieczyszczenia_pct=p.zanieczyszczenia_pct,
        gestosc_ziarna=p.gestosc_ziarna,
        liczba_opadania=p.liczba_opadania,
        parametry_json={
            "masa_rozliczeniowa_kg": str(masa_rozliczeniowa),
            "potracenie_kg": str(potracenie),
            "flaga_awarii_wagi": p.flaga_awarii_wagi,
        },
        data_przyjecia=now,
        status="DOSTEPNA",
    )
    db.add(lot)
    db.flush()

    pz = DokumentMagazynowy(
        typ="PZ",
        numer=pz_number,
        data_wystawienia=now,
        status="ZATWIERDZONY",
        kontrahent_id=p.dostawca_id,
        lokalizacja_docelowa_id=silo.id,
        nr_rejestracyjny=p.nr_rejestracyjny,
        flaga_awarii_wagi=p.flaga_awarii_wagi,
        uwagi=payload.uwagi,
        utworzyl_id=user.id,
        zatwierdzil_id=user.id,
        zatwierdzono_utc=now,
    )
    db.add(pz)
    db.flush()

    db.add(
        PozycjaDokumentu(
            dokument_id=pz.id,
            lp=1,
            asortyment_id=p.asortyment_id,
            partia_id=lot.id,
            lokalizacja_id=silo.id,
            ilosc_fizyczna_kg=masa_netto,
            ilosc_rozliczeniowa_kg=masa_rozliczeniowa,
            cena_netto=p.asortyment.cena_bazowa_netto,
            stawka_vat=p.asortyment.stawka_vat,
        )
    )
    db.add(
        RuchMagazynowy(
            dokument_id=pz.id,
            typ_dokumentu="PZ",
            partia_id=lot.id,
            lokalizacja_docelowa_id=silo.id,
            asortyment_id=p.asortyment_id,
            ilosc_kg=masa_netto,
            kierunek="PRZYCHOD",
            stan_po_ruchu_kg=masa_netto,
            uzytkownik_id=user.id,
        )
    )

    p.masa_tara_kg = tara
    p.masa_netto_kg = masa_netto
    p.potracenie_kg = potracenie
    p.masa_rozliczeniowa_kg = masa_rozliczeniowa
    p.partia_id = lot.id
    p.dokument_pz_id = pz.id
    p.status = "ZATWIERDZONE"
    p.zatwierdzono_utc = now

    record_audit(
        db,
        akcja="ZATWIERDZENIE_PZ",
        zasob="DOKUMENT_PZ",
        zasob_id=pz.id,
        zmiana_stanu={
            "numer_pz": pz.numer,
            "kod_partii": lot.kod_partii,
            "silos": silo.kod,
            "masa_netto_kg": str(masa_netto),
            "masa_rozliczeniowa_kg": str(masa_rozliczeniowa),
            "flaga_awarii_wagi": p.flaga_awarii_wagi,
        },
        user=user,
        adres_ip=client_ip_from_request(request),
    )
    db.commit()
    db.refresh(p)
    return _serialize_przyjecie(p, db)


@router.get("/raport-kontrolny")
def control_report(
    user: Uzytkownik = Depends(require_roles("KIER_MAG", "ADMIN")),
    db: Session = Depends(get_db),
):
    rows = db.scalars(
        select(PrzyjecieSkupowe)
        .where(
            (PrzyjecieSkupowe.flaga_awarii_wagi.is_(True))
            | (PrzyjecieSkupowe.czy_przekroczono_prog.is_(True))
        )
        .order_by(PrzyjecieSkupowe.utworzono_utc.desc())
    ).all()
    return [_serialize_przyjecie(p, db) for p in rows]
