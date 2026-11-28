from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.models.entities import (
    Asortyment,
    CennikKontrahenta,
    Kontrahent,
    LokalizacjaMagazynowa,
    PartiaMagazynowa,
    Uzytkownik,
)
from app.schemas.dto import AsortymentCreate, CennikUpsertRequest, KontrahentCreate, LokalizacjaCreate
from app.services.adapters import AdapterGUS
from app.services.audit import client_ip_from_request, record_audit
from app.services.common import q3

router = APIRouter(prefix="/api", tags=["Kartoteki"])


@router.get("/kontrahenci")
def list_kontrahenci(
    typ: str | None = None,
    q: str | None = None,
    user: Uzytkownik = Depends(require_roles("OP_WAG", "MAG_WG", "KIER_MAG", "FAKT_KS", "ADMIN")),
    db: Session = Depends(get_db),
):
    stmt = select(Kontrahent).order_by(Kontrahent.nazwa)
    rows = db.scalars(stmt).all()
    if typ:
        rows = [r for r in rows if r.typ in (typ, "OBA")]
    if q:
        ql = q.lower().strip()
        rows = [r for r in rows if ql in r.nazwa.lower() or ql in r.nip]
    return [
        {
            "id": r.id,
            "nip": r.nip,
            "nazwa": r.nazwa,
            "adres": r.adres,
            "typ": r.typ,
            "termin_platnosci_dni": r.termin_platnosci_dni,
            "forma_platnosci": r.forma_platnosci,
            "zrodlo_danych": r.zrodlo_danych,
        }
        for r in rows
    ]


@router.get("/kontrahenci/gus/{nip}")
def lookup_gus(
    nip: str,
    user: Uzytkownik = Depends(require_roles("OP_WAG", "KIER_MAG", "FAKT_KS", "ADMIN")),
    db: Session = Depends(get_db),
):
    clean_nip = "".join(ch for ch in nip if ch.isdigit())
    existing = db.scalar(select(Kontrahent).where(Kontrahent.nip == clean_nip))
    res = AdapterGUS().pobierz_po_nip(clean_nip)
    return {
        "znaleziono_w_gus": res.znaleziono,
        "istnieje_w_bazie": existing is not None,
        "istniejacy_kontrahent_id": existing.id if existing else None,
        "nip": res.nip,
        "nazwa": existing.nazwa if existing else res.nazwa,
        "adres": existing.adres if existing else res.adres,
        "tryb": res.tryb,
        "komunikat": res.komunikat,
    }


@router.post("/kontrahenci", status_code=status.HTTP_201_CREATED)
def create_kontrahent(
    payload: KontrahentCreate,
    request: Request,
    user: Uzytkownik = Depends(require_roles("OP_WAG", "KIER_MAG", "FAKT_KS", "ADMIN")),
    db: Session = Depends(get_db),
):
    clean_nip = "".join(ch for ch in payload.nip if ch.isdigit())
    if len(clean_nip) != 10:
        raise HTTPException(status_code=422, detail="Numer NIP musi zawierać dokładnie 10 cyfr.")

    existing = db.scalar(select(Kontrahent).where(Kontrahent.nip == clean_nip))
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Kontrahent o NIP {clean_nip} już istnieje: {existing.nazwa} (id: {existing.id}).",
        )

    item = Kontrahent(
        nip=clean_nip,
        nazwa=payload.nazwa.strip(),
        adres=payload.adres.strip(),
        typ=payload.typ,
        termin_platnosci_dni=payload.termin_platnosci_dni,
        forma_platnosci=payload.forma_platnosci,
        zrodlo_danych=payload.zrodlo_danych,
    )
    db.add(item)
    db.flush()
    record_audit(
        db,
        akcja="UTWORZENIE_KONTRAHENTA",
        zasob="KONTRAHENT",
        zasob_id=item.id,
        zmiana_stanu={"nip": item.nip, "nazwa": item.nazwa, "typ": item.typ},
        user=user,
        adres_ip=client_ip_from_request(request),
    )
    db.commit()
    return {
        "id": item.id,
        "nip": item.nip,
        "nazwa": item.nazwa,
        "adres": item.adres,
        "typ": item.typ,
        "termin_platnosci_dni": item.termin_platnosci_dni,
        "forma_platnosci": item.forma_platnosci,
        "zrodlo_danych": item.zrodlo_danych,
    }


@router.get("/asortyment")
def list_asortyment(
    kategoria: str | None = None,
    user: Uzytkownik = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(Asortyment).where(Asortyment.czy_aktywny.is_(True)).order_by(Asortyment.kategoria, Asortyment.nazwa)
    if kategoria:
        stmt = stmt.where(Asortyment.kategoria == kategoria)
    rows = db.scalars(stmt).all()
    return [
        {
            "id": a.id,
            "kod_ean": a.kod_ean,
            "kod_wewnetrzny": a.kod_wewnetrzny,
            "nazwa": a.nazwa,
            "kategoria": a.kategoria,
            "jednostka": a.jednostka,
            "stawka_vat": str(a.stawka_vat),
            "wilgotnosc_max_pct": str(a.wilgotnosc_max_pct) if a.wilgotnosc_max_pct is not None else None,
            "zanieczyszczenia_max_pct": str(a.zanieczyszczenia_max_pct) if a.zanieczyszczenia_max_pct is not None else None,
            "typ_granulacji": a.typ_granulacji,
            "okres_przydatnosci_dni": a.okres_przydatnosci_dni,
            "cena_bazowa_netto": str(a.cena_bazowa_netto),
        }
        for a in rows
    ]


@router.post("/asortyment", status_code=status.HTTP_201_CREATED)
def create_asortyment(
    payload: AsortymentCreate,
    request: Request,
    user: Uzytkownik = Depends(require_roles("KIER_MAG", "ADMIN")),
    db: Session = Depends(get_db),
):
    if db.scalar(select(Asortyment).where(Asortyment.kod_wewnetrzny == payload.kod_wewnetrzny)):
        raise HTTPException(status_code=409, detail="Asortyment o takim kodzie wewnętrznym już istnieje.")
    if db.scalar(select(Asortyment).where(Asortyment.kod_ean == payload.kod_ean)):
        raise HTTPException(status_code=409, detail="Asortyment o takim kodzie EAN już istnieje.")

    item = Asortyment(**payload.model_dump())
    db.add(item)
    db.flush()
    record_audit(
        db,
        akcja="DODANIE_ASORTYMENTU",
        zasob="ASORTYMENT",
        zasob_id=item.id,
        zmiana_stanu={"kod": item.kod_wewnetrzny, "nazwa": item.nazwa, "kategoria": item.kategoria},
        user=user,
        adres_ip=client_ip_from_request(request),
    )
    db.commit()
    return {"id": item.id, "kod_wewnetrzny": item.kod_wewnetrzny, "nazwa": item.nazwa}


@router.get("/cenniki")
def list_cenniki(
    kontrahent_id: str | None = None,
    user: Uzytkownik = Depends(require_roles("MAG_WG", "KIER_MAG", "FAKT_KS", "ADMIN")),
    db: Session = Depends(get_db),
):
    stmt = select(CennikKontrahenta)
    if kontrahent_id:
        stmt = stmt.where(CennikKontrahenta.kontrahent_id == kontrahent_id)
    rows = db.scalars(stmt).all()
    return [
        {
            "id": c.id,
            "kontrahent_id": c.kontrahent_id,
            "kontrahent_nazwa": c.kontrahent.nazwa,
            "asortyment_id": c.asortyment_id,
            "asortyment_nazwa": c.asortyment.nazwa,
            "cena_netto": str(c.cena_netto),
            "waluta": c.waluta,
            "obowiazuje_od": c.obowiazuje_od.isoformat(),
        }
        for c in rows
    ]


@router.post("/cenniki")
def upsert_cennik(
    payload: CennikUpsertRequest,
    request: Request,
    user: Uzytkownik = Depends(require_roles("FAKT_KS", "KIER_MAG")),
    db: Session = Depends(get_db),
):
    existing = db.scalar(
        select(CennikKontrahenta).where(
            CennikKontrahenta.kontrahent_id == payload.kontrahent_id,
            CennikKontrahenta.asortyment_id == payload.asortyment_id,
        )
    )
    new_price = q3(payload.cena_netto)
    if existing:
        old_price = str(existing.cena_netto)
        existing.cena_netto = new_price
        existing.waluta = payload.waluta
        item = existing
    else:
        old_price = None
        item = CennikKontrahenta(
            kontrahent_id=payload.kontrahent_id,
            asortyment_id=payload.asortyment_id,
            cena_netto=new_price,
            waluta=payload.waluta,
        )
        db.add(item)
    db.flush()
    record_audit(
        db,
        akcja="AKTUALIZACJA_CENNIKA",
        zasob="CENNIK",
        zasob_id=item.id,
        zmiana_stanu={
            "kontrahent_id": payload.kontrahent_id,
            "asortyment_id": payload.asortyment_id,
            "stara_cena": old_price,
            "nowa_cena": str(new_price),
        },
        user=user,
        adres_ip=client_ip_from_request(request),
    )
    db.commit()
    return {"id": item.id, "cena_netto": str(item.cena_netto)}


@router.get("/lokalizacje")
def list_lokalizacje(
    typ: str | None = None,
    strefa: str | None = None,
    user: Uzytkownik = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(LokalizacjaMagazynowa).where(LokalizacjaMagazynowa.czy_aktywna.is_(True)).order_by(LokalizacjaMagazynowa.kod)
    if typ:
        stmt = stmt.where(LokalizacjaMagazynowa.typ == typ)
    if strefa:
        stmt = stmt.where(LokalizacjaMagazynowa.strefa == strefa)
    locs = db.scalars(stmt).all()

    occ_rows = db.execute(
        select(
            PartiaMagazynowa.lokalizacja_id,
            func.coalesce(func.sum(PartiaMagazynowa.masa_dostepna_kg), 0),
        )
        .where(PartiaMagazynowa.status.in_(["DOSTEPNA", "WSTRZYMANA", "ZABLOKOWANA"]))
        .group_by(PartiaMagazynowa.lokalizacja_id)
    ).all()
    occ_map = {loc_id: q3(total) for loc_id, total in occ_rows}

    return [
        {
            "id": loc.id,
            "kod": loc.kod,
            "nazwa": loc.nazwa,
            "typ": loc.typ,
            "strefa": loc.strefa,
            "pojemnosc_max_kg": str(loc.pojemnosc_max_kg),
            "stan_zajety_kg": str(occ_map.get(loc.id, q3(0))),
            "wolne_miejsce_kg": str(q3(loc.pojemnosc_max_kg - occ_map.get(loc.id, q3(0)))),
            "gestosc_usypowa": str(loc.gestosc_usypowa) if loc.gestosc_usypowa else None,
            "czy_zablokowana": loc.czy_zablokowana,
            "powod_blokady": loc.powod_blokady,
        }
        for loc in locs
    ]


@router.post("/lokalizacje", status_code=status.HTTP_201_CREATED)
def create_lokalizacja(
    payload: LokalizacjaCreate,
    request: Request,
    user: Uzytkownik = Depends(require_roles("KIER_MAG", "ADMIN")),
    db: Session = Depends(get_db),
):
    if db.scalar(select(LokalizacjaMagazynowa).where(LokalizacjaMagazynowa.kod == payload.kod.strip())):
        raise HTTPException(status_code=409, detail="Lokalizacja o takim kodzie już istnieje.")
    loc = LokalizacjaMagazynowa(**payload.model_dump())
    db.add(loc)
    db.flush()
    record_audit(
        db,
        akcja="DODANIE_LOKALIZACJI",
        zasob="LOKALIZACJA",
        zasob_id=loc.id,
        zmiana_stanu={"kod": loc.kod, "typ": loc.typ, "strefa": loc.strefa},
        user=user,
        adres_ip=client_ip_from_request(request),
    )
    db.commit()
    return {"id": loc.id, "kod": loc.kod, "nazwa": loc.nazwa}
