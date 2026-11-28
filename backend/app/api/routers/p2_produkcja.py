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
    LokalizacjaMagazynowa,
    PartiaMagazynowa,
    PozycjaDokumentu,
    RecepturaBOM,
    RuchMagazynowy,
    SkladnikReceptury,
    Uzytkownik,
    ZlecenieProdukcyjne,
)
from app.schemas.dto import (
    BomCreateRequest,
    ZlecenieAkceptacjaStratyRequest,
    ZlecenieCreateRequest,
    ZlecenieKorektaRwRequest,
    ZlecenieRozliczRequest,
)
from app.services.audit import client_ip_from_request, record_audit
from app.services.common import (
    D_ZERO,
    get_config_decimal,
    get_location_occupied_kg,
    lock_batch_for_update,
    lock_location_for_update,
    next_batch_code,
    next_document_number,
    q3,
)

router = APIRouter(prefix="/api/p2", tags=["P2 - Produkcja i bilans"])


def _serialize_bom(b: RecepturaBOM) -> dict:
    return {
        "id": b.id,
        "kod": b.kod,
        "nazwa": b.nazwa,
        "wyrob_docelowy_id": b.wyrob_docelowy_id,
        "wyrob_docelowy_nazwa": b.wyrob_docelowy.nazwa,
        "wersja": b.wersja,
        "normatyw_strat_pct": str(b.normatyw_strat_pct),
        "status": b.status,
        "utworzono_utc": b.utworzono_utc.isoformat(),
        "skladniki": [
            {
                "id": s.id,
                "asortyment_id": s.asortyment_id,
                "asortyment_nazwa": s.asortyment.nazwa,
                "typ_skladnika": s.typ_skladnika,
                "udzial_procentowy": str(s.udzial_procentowy),
            }
            for s in b.skladniki
        ],
    }


def _serialize_order(z: ZlecenieProdukcyjne, db: Session) -> dict:
    docs = db.scalars(
        select(DokumentMagazynowy).where(DokumentMagazynowy.zlecenie_id == z.id).order_by(DokumentMagazynowy.utworzono_utc)
    ).all()
    return {
        "id": z.id,
        "numer": z.numer,
        "receptura_id": z.receptura_id,
        "receptura_nazwa": f"{z.receptura.kod} v{z.receptura.wersja} ({z.receptura.nazwa})",
        "wyrob_docelowy_id": z.receptura.wyrob_docelowy_id,
        "wyrob_docelowy_nazwa": z.receptura.wyrob_docelowy.nazwa,
        "normatyw_strat_pct": str(z.receptura.normatyw_strat_pct),
        "linia_przemialowa": z.linia_przemialowa,
        "planowany_zasyp_kg": str(z.planowany_zasyp_kg),
        "partia_surowca_id": z.partia_surowca_id,
        "partia_surowca_kod": z.partia_surowca.kod_partii,
        "ilosc_rw_kg": str(z.ilosc_rw_kg),
        "ilosc_pw_glowny_kg": str(z.ilosc_pw_glowny_kg),
        "ilosc_pw_uboczne_kg": str(z.ilosc_pw_uboczne_kg),
        "strata_odsiew_kg": str(z.strata_odsiew_kg),
        "strata_wilgotnosc_kg": str(z.strata_wilgotnosc_kg),
        "strata_calkowita_kg": str(z.strata_calkowita_kg),
        "roznica_bilansowa_kg": str(z.roznica_bilansowa_kg),
        "roznica_bilansowa_pct": str(z.roznica_bilansowa_pct),
        "czy_bilans_uzgodniony": z.czy_bilans_uzgodniony,
        "powod_straty": z.powod_straty,
        "status": z.status,
        "dokumenty": [{"id": d.id, "typ": d.typ, "numer": d.numer, "status": d.status} for d in docs],
        "utworzono_utc": z.utworzono_utc.isoformat(),
        "zakonczono_utc": z.zakonczono_utc.isoformat() if z.zakonczono_utc else None,
    }


def _finalize_pw_atomic(
    db: Session,
    *,
    order: ZlecenieProdukcyjne,
    pw_doc: DokumentMagazynowy,
    user: Uzytkownik,
    request: Request,
    payload_meta: dict,
) -> None:
    now = datetime.now(timezone.utc)
    main_lot_loc = lock_location_for_update(db, payload_meta["lokalizacja_docelowa_id"])
    if main_lot_loc is None or main_lot_loc.czy_zablokowana:
        raise HTTPException(status_code=409, detail="Docelowa lokalizacja dla wyrobu gotowego jest zablokowana.")

    occupied = get_location_occupied_kg(db, main_lot_loc.id)
    main_kg = Decimal(payload_meta["wyrob_glowny_kg"])
    if occupied + main_kg > main_lot_loc.pojemnosc_max_kg:
        raise HTTPException(status_code=409, detail=f"Brak pojemności w lokalizacji {main_lot_loc.kod}.")

    main_lot = PartiaMagazynowa(
        kod_partii=next_batch_code(db, "LOT-WG"),
        asortyment_id=order.receptura.wyrob_docelowy_id,
        lokalizacja_id=main_lot_loc.id,
        zlecenie_zrodlowe_id=order.id,
        partia_zrodlowa_id=order.partia_surowca_id,
        masa_poczatkowa_kg=main_kg,
        masa_dostepna_kg=main_kg,
        data_przyjecia=now,
        data_waznosci=datetime.fromisoformat(payload_meta["data_waznosci_wyrobu"]).date(),
        status="DOSTEPNA",
    )
    db.add(main_lot)
    db.flush()

    db.add(
        PozycjaDokumentu(
            dokument_id=pw_doc.id,
            lp=1,
            asortyment_id=order.receptura.wyrob_docelowy_id,
            partia_id=main_lot.id,
            lokalizacja_id=main_lot_loc.id,
            ilosc_fizyczna_kg=main_kg,
            ilosc_rozliczeniowa_kg=main_kg,
            cena_netto=order.receptura.wyrob_docelowy.cena_bazowa_netto,
            stawka_vat=order.receptura.wyrob_docelowy.stawka_vat,
        )
    )
    db.add(
        RuchMagazynowy(
            dokument_id=pw_doc.id,
            typ_dokumentu="PW",
            partia_id=main_lot.id,
            lokalizacja_docelowa_id=main_lot_loc.id,
            asortyment_id=order.receptura.wyrob_docelowy_id,
            ilosc_kg=main_kg,
            kierunek="PRZYCHOD",
            stan_po_ruchu_kg=main_kg,
            uzytkownik_id=user.id,
        )
    )

    for idx, bp in enumerate(payload_meta.get("produkty_uboczne", []), start=2):
        bp_loc = lock_location_for_update(db, bp["lokalizacja_id"])
        if bp_loc is None or bp_loc.czy_zablokowana:
            raise HTTPException(status_code=409, detail="Lokalizacja dla produktu ubocznego jest zablokowana.")
        bp_item = db.get(Asortyment, bp["asortyment_id"])
        if bp_item is None:
            raise HTTPException(status_code=422, detail="Nieznany produkt uboczny.")
        bp_kg = Decimal(bp["ilosc_kg"])
        exp_date = (
            datetime.fromisoformat(bp["data_waznosci"]).date()
            if bp.get("data_waznosci")
            else datetime.fromisoformat(payload_meta["data_waznosci_wyrobu"]).date()
        )
        bp_lot = PartiaMagazynowa(
            kod_partii=next_batch_code(db, "LOT-OTR"),
            asortyment_id=bp_item.id,
            lokalizacja_id=bp_loc.id,
            zlecenie_zrodlowe_id=order.id,
            partia_zrodlowa_id=order.partia_surowca_id,
            masa_poczatkowa_kg=bp_kg,
            masa_dostepna_kg=bp_kg,
            data_przyjecia=now,
            data_waznosci=exp_date,
            status="DOSTEPNA",
        )
        db.add(bp_lot)
        db.flush()
        db.add(
            PozycjaDokumentu(
                dokument_id=pw_doc.id,
                lp=idx,
                asortyment_id=bp_item.id,
                partia_id=bp_lot.id,
                lokalizacja_id=bp_loc.id,
                ilosc_fizyczna_kg=bp_kg,
                ilosc_rozliczeniowa_kg=bp_kg,
                cena_netto=bp_item.cena_bazowa_netto,
                stawka_vat=bp_item.stawka_vat,
            )
        )
        db.add(
            RuchMagazynowy(
                dokument_id=pw_doc.id,
                typ_dokumentu="PW",
                partia_id=bp_lot.id,
                lokalizacja_docelowa_id=bp_loc.id,
                asortyment_id=bp_item.id,
                ilosc_kg=bp_kg,
                kierunek="PRZYCHOD",
                stan_po_ruchu_kg=bp_kg,
                uzytkownik_id=user.id,
            )
        )

    pw_doc.status = "ZATWIERDZONY"
    pw_doc.zatwierdzil_id = user.id
    pw_doc.zatwierdzono_utc = now
    order.status = "ZAKONCZONE"
    order.zakonczono_utc = now

    record_audit(
        db,
        akcja="ZATWIERDZENIE_PW",
        zasob="DOKUMENT_PW",
        zasob_id=pw_doc.id,
        zmiana_stanu={
            "zlecenie": order.numer,
            "numer_pw": pw_doc.numer,
            "partia_glowna": main_lot.kod_partii,
            "wyrob_glowny_kg": str(main_kg),
            "pw_uboczne_kg": str(order.ilosc_pw_uboczne_kg),
            "strata_calkowita_kg": str(order.strata_calkowita_kg),
            "roznica_bilansowa_pct": str(order.roznica_bilansowa_pct),
        },
        user=user,
        adres_ip=client_ip_from_request(request),
    )


@router.get("/receptury")
def list_boms(
    user: Uzytkownik = Depends(require_roles("INZ_PROD", "KIER_MAG", "ADMIN")),
    db: Session = Depends(get_db),
):
    rows = db.scalars(select(RecepturaBOM).order_by(RecepturaBOM.kod, RecepturaBOM.wersja.desc())).all()
    return [_serialize_bom(b) for b in rows]


@router.post("/receptury", status_code=status.HTTP_201_CREATED)
def create_bom(
    payload: BomCreateRequest,
    request: Request,
    user: Uzytkownik = Depends(require_roles("INZ_PROD")),
    db: Session = Depends(get_db),
):
    target_prod = db.get(Asortyment, payload.wyrob_docelowy_id)
    if target_prod is None or target_prod.kategoria != "WYROB_GOTOWY":
        raise HTTPException(status_code=422, detail="Wyrób docelowy musi być wyrobem gotowym z kartoteki.")

    input_sum = sum(
        (s.udzial_procentowy for s in payload.skladniki if s.typ_skladnika in ("SUROWIEC", "DODATEK")),
        Decimal("0.000"),
    )
    if abs(input_sum - Decimal("100.000")) > Decimal("0.010"):
        raise HTTPException(
            status_code=422,
            detail=f"Udziały surowców i dodatków muszą sumować się do 100% (obecnie: {input_sum}%).",
        )

    existing_same_code = db.scalars(select(RecepturaBOM).where(RecepturaBOM.kod == payload.kod.strip())).all()
    next_version = max((b.wersja for b in existing_same_code), default=0) + 1

    # Poprzednia aktywna receptura dla tego wyrobu staje się archiwalna (UC-02.1 ścieżka 6a)
    prev_active = db.scalars(
        select(RecepturaBOM).where(
            RecepturaBOM.wyrob_docelowy_id == target_prod.id,
            RecepturaBOM.status == "AKTYWNA",
        )
    ).all()
    for old_b in prev_active:
        old_b.status = "ARCHIWALNA"

    bom = RecepturaBOM(
        kod=payload.kod.strip(),
        nazwa=payload.nazwa.strip(),
        wyrob_docelowy_id=target_prod.id,
        wersja=next_version,
        normatyw_strat_pct=q3(payload.normatyw_strat_pct),
        status="AKTYWNA",
        autor_id=user.id,
    )
    db.add(bom)
    db.flush()

    for s in payload.skladniki:
        item = db.get(Asortyment, s.asortyment_id)
        if item is None:
            raise HTTPException(status_code=422, detail=f"Nie znaleziono składnika {s.asortyment_id}.")
        db.add(
            SkladnikReceptury(
                receptura_id=bom.id,
                asortyment_id=item.id,
                typ_skladnika=s.typ_skladnika,
                udzial_procentowy=q3(s.udzial_procentowy),
            )
        )

    record_audit(
        db,
        akcja="UTWORZENIE_RECEPTURY_BOM",
        zasob="RECEPTURA_BOM",
        zasob_id=bom.id,
        zmiana_stanu={"kod": bom.kod, "wersja": bom.wersja, "normatyw_strat_pct": str(bom.normatyw_strat_pct)},
        user=user,
        adres_ip=client_ip_from_request(request),
    )
    db.commit()
    db.refresh(bom)
    return _serialize_bom(bom)


@router.get("/zlecenia")
def list_orders(
    user: Uzytkownik = Depends(require_roles("INZ_PROD", "KIER_MAG", "ADMIN")),
    db: Session = Depends(get_db),
):
    rows = db.scalars(select(ZlecenieProdukcyjne).order_by(ZlecenieProdukcyjne.utworzono_utc.desc())).all()
    return [_serialize_order(z, db) for z in rows]


@router.post("/zlecenia", status_code=status.HTTP_201_CREATED)
def create_order_and_rw(
    payload: ZlecenieCreateRequest,
    request: Request,
    user: Uzytkownik = Depends(require_roles("INZ_PROD", "KIER_MAG")),
    db: Session = Depends(get_db),
):
    bom = db.get(RecepturaBOM, payload.receptura_id)
    if bom is None or bom.status != "AKTYWNA":
        raise HTTPException(status_code=422, detail="Wybrana receptura BOM nie istnieje lub nie jest aktywna.")

    lot = lock_batch_for_update(db, payload.partia_surowca_id)
    if lot is None or lot.status != "DOSTEPNA":
        raise HTTPException(status_code=409, detail="Wybrana partia surowca jest niedostępna.")
    if lot.asortyment.kategoria != "SUROWIEC":
        raise HTTPException(status_code=422, detail="Zlecenie wymaga partii surowca.")

    loc = lock_location_for_update(db, lot.lokalizacja_id)
    if loc is None or loc.czy_zablokowana:
        raise HTTPException(status_code=409, detail="Lokalizacja surowca jest zablokowana (np. inwentaryzacja).")

    qty = q3(payload.planowany_zasyp_kg)
    if lot.masa_dostepna_kg < qty:
        raise HTTPException(
            status_code=409,
            detail=f"Brak wystarczającej ilości surowca w partii {lot.kod_partii} (dostępne: {lot.masa_dostepna_kg} kg).",
        )

    now = datetime.now(timezone.utc)
    order_num = next_document_number(db, "ZP", ZlecenieProdukcyjne)
    rw_num = next_document_number(db, "RW", DokumentMagazynowy)

    order = ZlecenieProdukcyjne(
        numer=order_num,
        receptura_id=bom.id,
        linia_przemialowa=payload.linia_przemialowa.strip(),
        planowany_zasyp_kg=qty,
        partia_surowca_id=lot.id,
        lokalizacja_zrodlowa_id=loc.id,
        ilosc_rw_kg=qty,
        status="W_REALIZACJI",
        inzynier_id=user.id,
    )
    db.add(order)
    db.flush()

    lot.masa_dostepna_kg = q3(lot.masa_dostepna_kg - qty)
    if lot.masa_dostepna_kg == D_ZERO:
        lot.status = "ZUZYTA"

    rw = DokumentMagazynowy(
        typ="RW",
        numer=rw_num,
        data_wystawienia=now,
        status="ZATWIERDZONY",
        lokalizacja_zrodlowa_id=loc.id,
        zlecenie_id=order.id,
        utworzyl_id=user.id,
        zatwierdzil_id=user.id,
        zatwierdzono_utc=now,
        uwagi=f"Automatyczne RW do zlecenia {order.numer}",
    )
    db.add(rw)
    db.flush()

    db.add(
        PozycjaDokumentu(
            dokument_id=rw.id,
            lp=1,
            asortyment_id=lot.asortyment_id,
            partia_id=lot.id,
            lokalizacja_id=loc.id,
            ilosc_fizyczna_kg=qty,
            ilosc_rozliczeniowa_kg=qty,
            cena_netto=lot.asortyment.cena_bazowa_netto,
            stawka_vat=lot.asortyment.stawka_vat,
        )
    )
    db.add(
        RuchMagazynowy(
            dokument_id=rw.id,
            typ_dokumentu="RW",
            partia_id=lot.id,
            lokalizacja_zrodlowa_id=loc.id,
            asortyment_id=lot.asortyment_id,
            ilosc_kg=qty,
            kierunek="ROZCHOD",
            stan_po_ruchu_kg=lot.masa_dostepna_kg,
            uzytkownik_id=user.id,
        )
    )

    record_audit(
        db,
        akcja="UTWORZENIE_ZLECENIA_I_RW",
        zasob="ZLECENIE_PRODUKCYJNE",
        zasob_id=order.id,
        zmiana_stanu={
            "zlecenie": order.numer,
            "numer_rw": rw.numer,
            "partia_surowca": lot.kod_partii,
            "ilosc_rw_kg": str(qty),
        },
        user=user,
        adres_ip=client_ip_from_request(request),
    )
    db.commit()
    db.refresh(order)
    return _serialize_order(order, db)


@router.post("/zlecenia/{zlecenie_id}/rozlicz-pw")
def settle_production_pw(
    zlecenie_id: str,
    payload: ZlecenieRozliczRequest,
    request: Request,
    user: Uzytkownik = Depends(require_roles("INZ_PROD", "KIER_MAG")),
    db: Session = Depends(get_db),
):
    order = db.get(ZlecenieProdukcyjne, zlecenie_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono zlecenia produkcyjnego.")
    if order.status != "W_REALIZACJI":
        raise HTTPException(status_code=409, detail=f"Zlecenie ma status {order.status} i nie może zostać rozliczone.")

    tolerancja_pct = get_config_decimal(db, "tolerancja_bilansu_pct", Decimal("0.500"))
    prog_straty_pct = get_config_decimal(db, "prog_straty_procesowej_pct", Decimal("3.000"))

    rw_kg = q3(order.ilosc_rw_kg)
    pw_glowny = q3(payload.wyrob_glowny_kg)
    pw_uboczne = sum((q3(bp.ilosc_kg) for bp in payload.produkty_uboczne), D_ZERO)
    strata_odsiew = q3(payload.strata_odsiew_kg)
    strata_wilg = q3(payload.strata_wilgotnosc_kg)
    strata_total = q3(strata_odsiew + strata_wilg)

    suma_wyjsc = q3(pw_glowny + pw_uboczne + strata_total)
    roznica_kg = q3(abs(rw_kg - suma_wyjsc))
    roznica_pct = q3((roznica_kg / rw_kg) * Decimal("100")) if rw_kg > D_ZERO else Decimal("100.000")
    strata_pct = q3((strata_total / rw_kg) * Decimal("100")) if rw_kg > D_ZERO else D_ZERO

    # Twarda kontrola bilansu masowego: nigdy nie księguj różnicy automatycznie jako straty!
    if roznica_pct > tolerancja_pct:
        record_audit(
            db,
            akcja="BLOKADA_BILANSU_PRODUKCJI",
            zasob="ZLECENIE_PRODUKCYJNE",
            zasob_id=order.id,
            zmiana_stanu={
                "rw_kg": str(rw_kg),
                "pw_suma_kg": str(pw_glowny + pw_uboczne),
                "strata_kg": str(strata_total),
                "roznica_kg": str(roznica_kg),
                "roznica_pct": str(roznica_pct),
                "tolerancja_pct": str(tolerancja_pct),
            },
            user=user,
            adres_ip=client_ip_from_request(request),
            komentarz="Nieuzgodniony bilans masowy — wstrzymano PW",
        )
        db.commit()
        raise HTTPException(
            status_code=422,
            detail=(
                f"Nieuzgodniony bilans masowy (RF-02.4)! RW={rw_kg} kg, PW+uboczne={pw_glowny + pw_uboczne} kg, "
                f"Strata={strata_total} kg. Różnica={roznica_kg} kg ({roznica_pct}% > tolerancji {tolerancja_pct}%). "
                "Różnica nie może zostać automatycznie zaksięgowana jako strata."
            ),
        )

    order.ilosc_pw_glowny_kg = pw_glowny
    order.ilosc_pw_uboczne_kg = pw_uboczne
    order.strata_odsiew_kg = strata_odsiew
    order.strata_wilgotnosc_kg = strata_wilg
    order.strata_calkowita_kg = strata_total
    order.roznica_bilansowa_kg = roznica_kg
    order.roznica_bilansowa_pct = roznica_pct
    order.czy_bilans_uzgodniony = True
    order.powod_straty = payload.powod_straty

    meta = {
        "lokalizacja_docelowa_id": payload.lokalizacja_docelowa_id,
        "wyrob_glowny_kg": str(pw_glowny),
        "data_waznosci_wyrobu": payload.data_waznosci_wyrobu.isoformat(),
        "produkty_uboczne": [
            {
                "asortyment_id": bp.asortyment_id,
                "lokalizacja_id": bp.lokalizacja_id,
                "ilosc_kg": str(q3(bp.ilosc_kg)),
                "data_waznosci": bp.data_waznosci.isoformat() if bp.data_waznosci else None,
            }
            for bp in payload.produkty_uboczne
        ],
    }

    pw_num = next_document_number(db, "PW", DokumentMagazynowy)
    # Jeśli strata przekracza próg 3%, wstrzymaj PW do akceptacji KIER_MAG (UC-02.3 ścieżka 4a)
    if strata_pct > prog_straty_pct:
        if not payload.powod_straty or len(payload.powod_straty.strip()) < 3:
            raise HTTPException(
                status_code=422,
                detail=f"Strata procesowa ({strata_pct}%) przekracza normę ({prog_straty_pct}%). Podaj przyczynę technologiczną dla kierownika.",
            )
        import json

        pw_doc = DokumentMagazynowy(
            typ="PW",
            numer=pw_num,
            status="WSTRZYMANY",
            lokalizacja_docelowa_id=payload.lokalizacja_docelowa_id,
            zlecenie_id=order.id,
            uwagi=json.dumps(meta),
            utworzyl_id=user.id,
        )
        db.add(pw_doc)
        order.status = "WSTRZYMANE_DO_AKCEPTACJI"
        record_audit(
            db,
            akcja="WSTRZYMANIE_PW_STRATA_POWYZEJ_PROGU",
            zasob="ZLECENIE_PRODUKCYJNE",
            zasob_id=order.id,
            zmiana_stanu={"strata_pct": str(strata_pct), "prog_pct": str(prog_straty_pct), "powod": payload.powod_straty},
            user=user,
            adres_ip=client_ip_from_request(request),
        )
        db.commit()
        db.refresh(order)
        return _serialize_order(order, db)

    pw_doc = DokumentMagazynowy(
        typ="PW",
        numer=pw_num,
        status="ROBOCZY",
        lokalizacja_docelowa_id=payload.lokalizacja_docelowa_id,
        zlecenie_id=order.id,
        utworzyl_id=user.id,
        uwagi=f"Rozliczenie zlecenia {order.numer}",
    )
    db.add(pw_doc)
    db.flush()
    _finalize_pw_atomic(db, order=order, pw_doc=pw_doc, user=user, request=request, payload_meta=meta)
    db.commit()
    db.refresh(order)
    return _serialize_order(order, db)


@router.post("/zlecenia/{zlecenie_id}/akceptuj-strate")
def manager_accept_loss(
    zlecenie_id: str,
    payload: ZlecenieAkceptacjaStratyRequest,
    request: Request,
    kierownik: Uzytkownik = Depends(require_roles("KIER_MAG")),
    db: Session = Depends(get_db),
):
    import json

    order = db.get(ZlecenieProdukcyjne, zlecenie_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono zlecenia.")
    if order.status != "WSTRZYMANE_DO_AKCEPTACJI":
        raise HTTPException(status_code=409, detail="Zlecenie nie oczekuje na akceptację straty.")

    pw_doc = db.scalar(
        select(DokumentMagazynowy).where(
            DokumentMagazynowy.zlecenie_id == order.id,
            DokumentMagazynowy.typ == "PW",
            DokumentMagazynowy.status == "WSTRZYMANY",
        )
    )
    if pw_doc is None:
        raise HTTPException(status_code=404, detail="Brak wstrzymanego dokumentu PW dla tego zlecenia.")

    order.kierownik_akceptacja_id = kierownik.id
    if not payload.akceptuj:
        pw_doc.status = "ANULOWANY"
        pw_doc.uwagi = f"Odrzucono stratę przez KIER_MAG: {payload.komentarz}"
        order.status = "W_REALIZACJI"
        order.czy_bilans_uzgodniony = False
        record_audit(
            db,
            akcja="ODRZUCENIE_STRATY_PRODUKCJI",
            zasob="ZLECENIE_PRODUKCYJNE",
            zasob_id=order.id,
            zmiana_stanu={"komentarz": payload.komentarz},
            user=kierownik,
            adres_ip=client_ip_from_request(request),
        )
        db.commit()
        db.refresh(order)
        return _serialize_order(order, db)

    meta = json.loads(pw_doc.uwagi or "{}")
    pw_doc.uwagi = f"Zaakceptowano ponadnormatywną stratę ({payload.komentarz})"
    _finalize_pw_atomic(db, order=order, pw_doc=pw_doc, user=kierownik, request=request, payload_meta=meta)
    db.commit()
    db.refresh(order)
    return _serialize_order(order, db)


@router.post("/zlecenia/{zlecenie_id}/korekta-rw")
def manager_correct_rw(
    zlecenie_id: str,
    payload: ZlecenieKorektaRwRequest,
    request: Request,
    kierownik: Uzytkownik = Depends(require_roles("KIER_MAG")),
    db: Session = Depends(get_db),
):
    order = db.get(ZlecenieProdukcyjne, zlecenie_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono zlecenia.")
    if order.status not in ("W_REALIZACJI", "WSTRZYMANE_DO_AKCEPTACJI"):
        raise HTTPException(status_code=409, detail="Korekta RW możliwa tylko dla aktywnego zlecenia.")

    delta = q3(payload.korekta_rw_kg)
    if delta == D_ZERO:
        raise HTTPException(status_code=422, detail="Korekta RW nie może wynosić 0.")

    lot = lock_batch_for_update(db, order.partia_surowca_id)
    if lot is None:
        raise HTTPException(status_code=404, detail="Brak partii źródłowej surowca.")

    if delta > D_ZERO and lot.masa_dostepna_kg < delta:
        raise HTTPException(status_code=409, detail="Brak wystarczającej ilości w partii surowca na dopisanie RW.")

    now = datetime.now(timezone.utc)
    lot.masa_dostepna_kg = q3(lot.masa_dostepna_kg - delta)
    if lot.masa_dostepna_kg > D_ZERO and lot.status == "ZUZYTA":
        lot.status = "DOSTEPNA"
    elif lot.masa_dostepna_kg == D_ZERO:
        lot.status = "ZUZYTA"

    order.ilosc_rw_kg = q3(order.ilosc_rw_kg + delta)
    doc_type = "RW-kor"
    kor_num = next_document_number(db, "RW-KOR", DokumentMagazynowy)
    kor = DokumentMagazynowy(
        typ=doc_type,
        numer=kor_num,
        data_wystawienia=now,
        status="ZATWIERDZONY",
        lokalizacja_zrodlowa_id=lot.lokalizacja_id,
        zlecenie_id=order.id,
        uwagi=payload.powod,
        utworzyl_id=kierownik.id,
        zatwierdzil_id=kierownik.id,
        zatwierdzono_utc=now,
    )
    db.add(kor)
    db.flush()
    db.add(
        RuchMagazynowy(
            dokument_id=kor.id,
            typ_dokumentu=doc_type,
            partia_id=lot.id,
            lokalizacja_zrodlowa_id=lot.lokalizacja_id if delta > 0 else None,
            lokalizacja_docelowa_id=lot.lokalizacja_id if delta < 0 else None,
            asortyment_id=lot.asortyment_id,
            ilosc_kg=abs(delta),
            kierunek="KOREKTA_MINUS" if delta > 0 else "KOREKTA_PLUS",
            stan_po_ruchu_kg=lot.masa_dostepna_kg,
            uzytkownik_id=kierownik.id,
        )
    )
    record_audit(
        db,
        akcja="KOREKTA_RW_ZLECENIA",
        zasob="ZLECENIE_PRODUKCYJNE",
        zasob_id=order.id,
        zmiana_stanu={"delta_kg": str(delta), "nowe_rw_kg": str(order.ilosc_rw_kg), "powod": payload.powod},
        user=kierownik,
        adres_ip=client_ip_from_request(request),
    )
    db.commit()
    db.refresh(order)
    return _serialize_order(order, db)


@router.get("/raport-wydajnosci")
def yield_report(
    user: Uzytkownik = Depends(require_roles("INZ_PROD", "KIER_MAG", "ADMIN")),
    db: Session = Depends(get_db),
):
    orders = db.scalars(
        select(ZlecenieProdukcyjne)
        .where(ZlecenieProdukcyjne.status == "ZAKONCZONE")
        .order_by(ZlecenieProdukcyjne.zakonczono_utc.desc())
    ).all()
    result = []
    for z in orders:
        rw = z.ilosc_rw_kg or Decimal("1")
        uzysk_glowny_pct = q3((z.ilosc_pw_glowny_kg / rw) * Decimal("100"))
        uzysk_uboczne_pct = q3((z.ilosc_pw_uboczne_kg / rw) * Decimal("100"))
        strata_pct = q3((z.strata_calkowita_kg / rw) * Decimal("100"))
        result.append(
            {
                "zlecenie_id": z.id,
                "numer": z.numer,
                "wyrob_nazwa": z.receptura.wyrob_docelowy.nazwa,
                "linia_przemialowa": z.linia_przemialowa,
                "partia_surowca_kod": z.partia_surowca.kod_partii,
                "wilgotnosc_surowca_pct": str(z.partia_surowca.wilgotnosc_pct) if z.partia_surowca.wilgotnosc_pct else None,
                "zanieczyszczenia_surowca_pct": str(z.partia_surowca.zanieczyszczenia_pct) if z.partia_surowca.zanieczyszczenia_pct else None,
                "ilosc_rw_kg": str(z.ilosc_rw_kg),
                "ilosc_pw_glowny_kg": str(z.ilosc_pw_glowny_kg),
                "ilosc_pw_uboczne_kg": str(z.ilosc_pw_uboczne_kg),
                "strata_calkowita_kg": str(z.strata_calkowita_kg),
                "uzysk_glowny_pct": str(uzysk_glowny_pct),
                "uzysk_uboczne_pct": str(uzysk_uboczne_pct),
                "strata_rzeczywista_pct": str(strata_pct),
                "normatyw_strat_pct": str(z.receptura.normatyw_strat_pct),
                "zakonczono_utc": z.zakonczono_utc.isoformat() if z.zakonczono_utc else None,
            }
        )
    return result
