from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.models.entities import (
    ArkuszInwentaryzacji,
    Asortyment,
    DokumentMagazynowy,
    LokalizacjaMagazynowa,
    PartiaMagazynowa,
    PozycjaDokumentu,
    PozycjaInwentaryzacji,
    PrzyjecieSkupowe,
    RuchMagazynowy,
    Uzytkownik,
    ZlecenieProdukcyjne,
)
from app.schemas.dto import (
    CancelDocRequest,
    InwentaryzacjaCloseRequest,
    InwentaryzacjaCountsRequest,
    InwentaryzacjaStartRequest,
    MmTransferRequest,
)
from app.services.audit import client_ip_from_request, record_audit
from app.services.common import (
    D_ZERO,
    get_location_occupied_kg,
    lock_batch_for_update,
    lock_location_for_update,
    next_batch_code,
    next_document_number,
    q2,
    q3,
)

router = APIRouter(prefix="/api/p4", tags=["P4 - Nadzór magazynowy, MM, Inwentaryzacja"])


def _serialize_inventory(a: ArkuszInwentaryzacji) -> dict:
    return {
        "id": a.id,
        "numer": a.numer,
        "zakres_strefa": a.zakres_strefa,
        "status": a.status,
        "komentarz": a.komentarz,
        "utworzono_utc": a.utworzono_utc.isoformat(),
        "zamknieto_utc": a.zamknieto_utc.isoformat() if a.zamknieto_utc else None,
        "pozycje": [
            {
                "id": p.id,
                "lokalizacja_id": p.lokalizacja_id,
                "lokalizacja_kod": p.lokalizacja.kod,
                "partia_id": p.partia_id,
                "kod_partii": p.partia.kod_partii,
                "asortyment_nazwa": p.asortyment.nazwa,
                "stan_ewidencyjny_kg": str(p.stan_ewidencyjny_kg),
                "stan_spisany_kg": str(p.stan_spisany_kg) if p.stan_spisany_kg is not None else None,
                "roznica_kg": str(p.roznica_kg) if p.roznica_kg is not None else None,
                "podstawa_pomiaru": p.podstawa_pomiaru,
                "uzasadnienie": p.uzasadnienie,
            }
            for p in a.pozycje
        ],
    }


@router.get("/stany")
def current_stock(
    strefa: str | None = None,
    lokalizacja_id: str | None = None,
    asortyment_id: str | None = None,
    tylko_dostepne: bool = False,
    user: Uzytkownik = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = (
        select(PartiaMagazynowa)
        .join(LokalizacjaMagazynowa, PartiaMagazynowa.lokalizacja_id == LokalizacjaMagazynowa.id)
        .order_by(LokalizacjaMagazynowa.kod, PartiaMagazynowa.data_przyjecia.desc())
    )
    if strefa:
        stmt = stmt.where(LokalizacjaMagazynowa.strefa == strefa)
    if lokalizacja_id:
        stmt = stmt.where(PartiaMagazynowa.lokalizacja_id == lokalizacja_id)
    if asortyment_id:
        stmt = stmt.where(PartiaMagazynowa.asortyment_id == asortyment_id)
    if tylko_dostepne:
        stmt = stmt.where(PartiaMagazynowa.masa_dostepna_kg > D_ZERO)

    lots = db.scalars(stmt).all()
    today = date.today()
    return {
        "czas_odczytu_utc": datetime.now(timezone.utc).isoformat(),
        "partie": [
            {
                "id": l.id,
                "kod_partii": l.kod_partii,
                "asortyment_id": l.asortyment_id,
                "asortyment_nazwa": l.asortyment.nazwa,
                "kategoria": l.asortyment.kategoria,
                "lokalizacja_id": l.lokalizacja_id,
                "lokalizacja_kod": l.lokalizacja.kod,
                "lokalizacja_strefa": l.lokalizacja.strefa,
                "lokalizacja_zablokowana": l.lokalizacja.czy_zablokowana,
                "dostawca_nazwa": l.dostawca.nazwa if l.dostawca else None,
                "masa_poczatkowa_kg": str(l.masa_poczatkowa_kg),
                "masa_dostepna_kg": str(l.masa_dostepna_kg),
                "masa_zarezerwowana_kg": str(l.masa_zarezerwowana_kg),
                "wilgotnosc_pct": str(l.wilgotnosc_pct) if l.wilgotnosc_pct is not None else None,
                "zanieczyszczenia_pct": str(l.zanieczyszczenia_pct) if l.zanieczyszczenia_pct is not None else None,
                "data_przyjecia": l.data_przyjecia.isoformat(),
                "data_waznosci": l.data_waznosci.isoformat() if l.data_waznosci else None,
                "czy_przeterminowana": bool(l.data_waznosci and l.data_waznosci < today),
                "status": l.status,
                "powod_blokady": l.powod_blokady,
                "partia_zrodlowa_id": l.partia_zrodlowa_id,
            }
            for l in lots
        ],
    }


@router.get("/partia/{partia_id}/traceability")
def batch_traceability(
    partia_id: str,
    user: Uzytkownik = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    lot = db.get(PartiaMagazynowa, partia_id)
    if lot is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono partii magazynowej.")

    source_lot = db.get(PartiaMagazynowa, lot.partia_zrodlowa_id) if lot.partia_zrodlowa_id else None
    source_order = db.get(ZlecenieProdukcyjne, lot.zlecenie_zrodlowe_id) if lot.zlecenie_zrodlowe_id else None
    child_lots = db.scalars(select(PartiaMagazynowa).where(PartiaMagazynowa.partia_zrodlowa_id == lot.id)).all()

    movements = db.scalars(
        select(RuchMagazynowy).where(RuchMagazynowy.partia_id == lot.id).order_by(RuchMagazynowy.utworzono_utc)
    ).all()

    doc_ids = {m.dokument_id for m in movements}
    docs = [db.get(DokumentMagazynowy, did) for did in doc_ids]
    docs = [d for d in docs if d is not None]

    skup = db.scalar(select(PrzyjecieSkupowe).where(PrzyjecieSkupowe.partia_id == (source_lot.id if source_lot else lot.id)))

    return {
        "partia": {
            "id": lot.id,
            "kod_partii": lot.kod_partii,
            "asortyment": lot.asortyment.nazwa,
            "lokalizacja": lot.lokalizacja.kod,
            "masa_poczatkowa_kg": str(lot.masa_poczatkowa_kg),
            "masa_dostepna_kg": str(lot.masa_dostepna_kg),
            "wilgotnosc_pct": str(lot.wilgotnosc_pct) if lot.wilgotnosc_pct else None,
            "zanieczyszczenia_pct": str(lot.zanieczyszczenia_pct) if lot.zanieczyszczenia_pct else None,
            "data_waznosci": lot.data_waznosci.isoformat() if lot.data_waznosci else None,
        },
        "pochodzenie_surowca": {
            "partia_zrodlowa_kod": source_lot.kod_partii if source_lot else lot.kod_partii,
            "dostawca": (
                source_lot.dostawca.nazwa if source_lot and source_lot.dostawca
                else (lot.dostawca.nazwa if lot.dostawca else None)
            ),
            "nr_rejestracyjny": skup.nr_rejestracyjny if skup else None,
            "flaga_awarii_wagi": skup.flaga_awarii_wagi if skup else False,
        },
        "zlecenie_produkcyjne": {
            "id": source_order.id,
            "numer": source_order.numer,
            "linia": source_order.linia_przemialowa,
        } if source_order else None,
        "partie_pochodne": [
            {"id": c.id, "kod_partii": c.kod_partii, "asortyment": c.asortyment.nazwa, "masa_kg": str(c.masa_poczatkowa_kg)}
            for c in child_lots
        ],
        "dokumenty": [
            {
                "id": d.id,
                "typ": d.typ,
                "numer": d.numer,
                "status": d.status,
                "faktura_id": d.faktura_id,
            }
            for d in docs
        ],
        "ruchy": [
            {
                "id": m.id,
                "typ_dokumentu": m.typ_dokumentu,
                "kierunek": m.kierunek,
                "ilosc_kg": str(m.ilosc_kg),
                "stan_po_ruchu_kg": str(m.stan_po_ruchu_kg),
                "utworzono_utc": m.utworzono_utc.isoformat(),
            }
            for m in movements
        ],
    }


@router.get("/dokumenty")
def list_all_documents(
    typ: str | None = None,
    user: Uzytkownik = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(DokumentMagazynowy).order_by(DokumentMagazynowy.utworzono_utc.desc())
    if typ:
        stmt = stmt.where(DokumentMagazynowy.typ == typ)
    docs = db.scalars(stmt.limit(200)).all()
    return [
        {
            "id": d.id,
            "typ": d.typ,
            "numer": d.numer,
            "status": d.status,
            "data_wystawienia": d.data_wystawienia.isoformat(),
            "kontrahent_nazwa": d.kontrahent.nazwa if d.kontrahent else None,
            "flaga_awarii_wagi": d.flaga_awarii_wagi,
            "czy_zafakturowany": d.czy_zafakturowany,
            "liczba_wydrukow": d.liczba_wydrukow,
            "uwagi": d.uwagi,
        }
        for d in docs
    ]


@router.post("/mm", status_code=status.HTTP_201_CREATED)
def transfer_mm(
    payload: MmTransferRequest,
    request: Request,
    kierownik: Uzytkownik = Depends(require_roles("KIER_MAG")),
    db: Session = Depends(get_db),
):
    lot = lock_batch_for_update(db, payload.partia_id)
    if lot is None or lot.status != "DOSTEPNA":
        raise HTTPException(status_code=409, detail="Partia jest niedostępna do przesunięcia.")

    src_loc = lock_location_for_update(db, lot.lokalizacja_id)
    dst_loc = lock_location_for_update(db, payload.lokalizacja_docelowa_id)
    if src_loc is None or dst_loc is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono lokalizacji źródłowej lub docelowej.")
    if src_loc.id == dst_loc.id:
        raise HTTPException(status_code=422, detail="Lokalizacja źródłowa i docelowa muszą być różne.")
    if src_loc.czy_zablokowana or dst_loc.czy_zablokowana:
        raise HTTPException(status_code=409, detail="Przesunięcie zablokowane — jedna z lokalizacji jest objęta inwentaryzacją.")

    qty = q3(payload.ilosc_kg)
    if lot.masa_dostepna_kg < qty:
        raise HTTPException(status_code=409, detail=f"Brak wystarczającego zapasu w partii (dostępne: {lot.masa_dostepna_kg} kg).")

    dst_occupied = get_location_occupied_kg(db, dst_loc.id)
    if dst_occupied + qty > dst_loc.pojemnosc_max_kg:
        raise HTTPException(status_code=409, detail=f"Brak pojemności w lokalizacji docelowej {dst_loc.kod}.")

    now = datetime.now(timezone.utc)
    mm_num = next_document_number(db, "MM", DokumentMagazynowy)
    mm_doc = DokumentMagazynowy(
        typ="MM",
        numer=mm_num,
        data_wystawienia=now,
        status="ZATWIERDZONY",
        lokalizacja_zrodlowa_id=src_loc.id,
        lokalizacja_docelowa_id=dst_loc.id,
        uwagi=payload.uwagi,
        utworzyl_id=kierownik.id,
        zatwierdzil_id=kierownik.id,
        zatwierdzono_utc=now,
    )
    db.add(mm_doc)
    db.flush()

    if qty == lot.masa_dostepna_kg and lot.masa_poczatkowa_kg == lot.masa_dostepna_kg:
        # Pełne przeniesienie partii z zachowaniem dokładnego kodu partii
        lot.lokalizacja_id = dst_loc.id
        target_lot = lot
    else:
        lot.masa_dostepna_kg = q3(lot.masa_dostepna_kg - qty)
        if lot.masa_dostepna_kg == D_ZERO:
            lot.status = "ZUZYTA"
        target_lot = PartiaMagazynowa(
            kod_partii=next_batch_code(db, f"{lot.kod_partii[:7]}"),
            asortyment_id=lot.asortyment_id,
            lokalizacja_id=dst_loc.id,
            dostawca_id=lot.dostawca_id,
            zlecenie_zrodlowe_id=lot.zlecenie_zrodlowe_id,
            partia_zrodlowa_id=lot.partia_zrodlowa_id or lot.id,
            masa_poczatkowa_kg=qty,
            masa_dostepna_kg=qty,
            wilgotnosc_pct=lot.wilgotnosc_pct,
            zanieczyszczenia_pct=lot.zanieczyszczenia_pct,
            data_przyjecia=lot.data_przyjecia,
            data_waznosci=lot.data_waznosci,
            status="DOSTEPNA",
        )
        db.add(target_lot)
        db.flush()

    db.add(
        PozycjaDokumentu(
            dokument_id=mm_doc.id,
            lp=1,
            asortyment_id=lot.asortyment_id,
            partia_id=target_lot.id,
            lokalizacja_id=dst_loc.id,
            ilosc_fizyczna_kg=qty,
            ilosc_rozliczeniowa_kg=qty,
        )
    )
    db.add(
        RuchMagazynowy(
            dokument_id=mm_doc.id,
            typ_dokumentu="MM",
            partia_id=target_lot.id,
            lokalizacja_zrodlowa_id=src_loc.id,
            lokalizacja_docelowa_id=dst_loc.id,
            asortyment_id=lot.asortyment_id,
            ilosc_kg=qty,
            kierunek="TRANSFER",
            stan_po_ruchu_kg=target_lot.masa_dostepna_kg,
            uzytkownik_id=kierownik.id,
        )
    )

    record_audit(
        db,
        akcja="PRZESUNIECIE_MM",
        zasob="DOKUMENT_MM",
        zasob_id=mm_doc.id,
        zmiana_stanu={
            "numer_mm": mm_doc.numer,
            "partia_zrodlowa": lot.kod_partii,
            "partia_docelowa": target_lot.kod_partii,
            "z": src_loc.kod,
            "do": dst_loc.kod,
            "ilosc_kg": str(qty),
        },
        user=kierownik,
        adres_ip=client_ip_from_request(request),
    )
    db.commit()
    return {"id": mm_doc.id, "numer": mm_doc.numer, "partia_docelowa_kod": target_lot.kod_partii}


@router.get("/inwentaryzacje")
def list_inventories(
    user: Uzytkownik = Depends(require_roles("KIER_MAG", "MAG_WG", "FAKT_KS", "ADMIN")),
    db: Session = Depends(get_db),
):
    rows = db.scalars(select(ArkuszInwentaryzacji).order_by(ArkuszInwentaryzacji.utworzono_utc.desc())).all()
    return [_serialize_inventory(a) for a in rows]


@router.post("/inwentaryzacje", status_code=status.HTTP_201_CREATED)
def start_inventory(
    payload: InwentaryzacjaStartRequest,
    request: Request,
    kierownik: Uzytkownik = Depends(require_roles("KIER_MAG")),
    db: Session = Depends(get_db),
):
    existing_open = db.scalar(
        select(ArkuszInwentaryzacji).where(
            ArkuszInwentaryzacji.zakres_strefa == payload.zakres_strefa,
            ArkuszInwentaryzacji.status == "OTWARTA",
        )
    )
    if existing_open is not None:
        raise HTTPException(status_code=409, detail=f"Dla strefy {payload.zakres_strefa} istnieje już otwarty arkusz {existing_open.numer}.")

    locs = db.scalars(
        select(LokalizacjaMagazynowa).where(
            LokalizacjaMagazynowa.strefa == payload.zakres_strefa,
            LokalizacjaMagazynowa.czy_aktywna.is_(True),
        )
    ).all()
    if not locs:
        raise HTTPException(status_code=422, detail="Brak lokalizacji w wybranej strefie.")

    for loc in locs:
        if loc.czy_zablokowana:
            raise HTTPException(status_code=409, detail=f"Lokalizacja {loc.kod} jest już zablokowana.")
        loc.czy_zablokowana = True
        loc.powod_blokady = f"Inwentaryzacja strefy {payload.zakres_strefa}"

    loc_ids = [l.id for l in locs]
    lots = db.scalars(
        select(PartiaMagazynowa).where(
            PartiaMagazynowa.lokalizacja_id.in_(loc_ids),
            PartiaMagazynowa.masa_dostepna_kg > D_ZERO,
            PartiaMagazynowa.status.in_(["DOSTEPNA", "WSTRZYMANA", "ZABLOKOWANA"]),
        )
    ).all()

    inv_num = next_document_number(db, "INW", ArkuszInwentaryzacji)
    sheet = ArkuszInwentaryzacji(
        numer=inv_num,
        zakres_strefa=payload.zakres_strefa,
        status="OTWARTA",
        kierownik_id=kierownik.id,
        komentarz=payload.komentarz,
    )
    db.add(sheet)
    db.flush()

    for lot in lots:
        loc_obj = next((l for l in locs if l.id == lot.lokalizacja_id), None)
        podstawa = "POMIAR_SILOSU_GESTOSC" if (loc_obj and loc_obj.typ == "SILOS") else "SKAN_PALET"
        db.add(
            PozycjaInwentaryzacji(
                arkusz_id=sheet.id,
                lokalizacja_id=lot.lokalizacja_id,
                partia_id=lot.id,
                asortyment_id=lot.asortyment_id,
                stan_ewidencyjny_kg=lot.masa_dostepna_kg,
                podstawa_pomiaru=podstawa,
            )
        )

    record_audit(
        db,
        akcja="OTWARCIE_INWENTARYZACJI_BLOKADA_STREFY",
        zasob="INWENTARYZACJA",
        zasob_id=sheet.id,
        zmiana_stanu={"numer": sheet.numer, "strefa": sheet.zakres_strefa, "liczba_pozycji": len(lots)},
        user=kierownik,
        adres_ip=client_ip_from_request(request),
    )
    db.commit()
    db.refresh(sheet)
    return _serialize_inventory(sheet)


@router.post("/inwentaryzacje/{sheet_id}/spis")
def submit_inventory_counts(
    sheet_id: str,
    payload: InwentaryzacjaCountsRequest,
    request: Request,
    user: Uzytkownik = Depends(require_roles("KIER_MAG", "MAG_WG")),
    db: Session = Depends(get_db),
):
    sheet = db.get(ArkuszInwentaryzacji, sheet_id)
    if sheet is None or sheet.status != "OTWARTA":
        raise HTTPException(status_code=409, detail="Arkusz inwentaryzacji nie istnieje lub jest zamknięty.")

    lines_map = {p.id: p for p in sheet.pozycje}
    for line_in in payload.pozycje:
        poz = lines_map.get(line_in.pozycja_id)
        if poz is None:
            raise HTTPException(status_code=422, detail=f"Pozycja {line_in.pozycja_id} nie należy do tego arkusza.")
        spis = q3(line_in.stan_spisany_kg)
        poz.stan_spisany_kg = spis
        poz.roznica_kg = q3(spis - poz.stan_ewidencyjny_kg)
        poz.podstawa_pomiaru = line_in.podstawa_pomiaru
        poz.uzasadnienie = line_in.uzasadnienie

    record_audit(
        db,
        akcja="REJESTRACJA_SPISU_INWENTARYZACJI",
        zasob="INWENTARYZACJA",
        zasob_id=sheet.id,
        zmiana_stanu={"numer": sheet.numer, "liczba_wpisow": len(payload.pozycje)},
        user=user,
        adres_ip=client_ip_from_request(request),
    )
    db.commit()
    db.refresh(sheet)
    return _serialize_inventory(sheet)


@router.post("/inwentaryzacje/{sheet_id}/rozlicz")
def reconcile_inventory(
    sheet_id: str,
    payload: InwentaryzacjaCloseRequest,
    request: Request,
    kierownik: Uzytkownik = Depends(require_roles("KIER_MAG")),
    db: Session = Depends(get_db),
):
    sheet = db.get(ArkuszInwentaryzacji, sheet_id)
    if sheet is None or sheet.status != "OTWARTA":
        raise HTTPException(status_code=409, detail="Arkusz inwentaryzacji nie istnieje lub nie jest otwarty.")

    incomplete = [p.partia.kod_partii for p in sheet.pozycje if p.stan_spisany_kg is None]
    if incomplete:
        raise HTTPException(status_code=422, detail=f"Niepełny spis dla partii: {', '.join(incomplete)}")

    now = datetime.now(timezone.utc)
    surplus_lines = [p for p in sheet.pozycje if p.roznica_kg and p.roznica_kg > D_ZERO]
    shortage_lines = [p for p in sheet.pozycje if p.roznica_kg and p.roznica_kg < D_ZERO]
    created_docs = []

    if surplus_lines:
        pw_kor_num = next_document_number(db, "PW-KOR", DokumentMagazynowy)
        pw_kor = DokumentMagazynowy(
            typ="PW-kor",
            numer=pw_kor_num,
            data_wystawienia=now,
            status="ZATWIERDZONY",
            uwagi=f"Rozliczenie nadwyżki inwentaryzacji {sheet.numer}: {payload.komentarz}",
            utworzyl_id=kierownik.id,
            zatwierdzil_id=kierownik.id,
            zatwierdzono_utc=now,
        )
        db.add(pw_kor)
        db.flush()
        for idx, poz in enumerate(surplus_lines, start=1):
            lot = lock_batch_for_update(db, poz.partia_id)
            diff = q3(poz.roznica_kg)
            lot.masa_dostepna_kg = q3(lot.masa_dostepna_kg + diff)
            db.add(
                PozycjaDokumentu(
                    dokument_id=pw_kor.id,
                    lp=idx,
                    asortyment_id=lot.asortyment_id,
                    partia_id=lot.id,
                    lokalizacja_id=lot.lokalizacja_id,
                    ilosc_fizyczna_kg=diff,
                    ilosc_rozliczeniowa_kg=diff,
                )
            )
            db.add(
                RuchMagazynowy(
                    dokument_id=pw_kor.id,
                    typ_dokumentu="PW-kor",
                    partia_id=lot.id,
                    lokalizacja_docelowa_id=lot.lokalizacja_id,
                    asortyment_id=lot.asortyment_id,
                    ilosc_kg=diff,
                    kierunek="KOREKTA_PLUS",
                    stan_po_ruchu_kg=lot.masa_dostepna_kg,
                    uzytkownik_id=kierownik.id,
                )
            )
        created_docs.append(pw_kor.numer)

    if shortage_lines:
        rw_kor_num = next_document_number(db, "RW-KOR", DokumentMagazynowy)
        rw_kor = DokumentMagazynowy(
            typ="RW-kor",
            numer=rw_kor_num,
            data_wystawienia=now,
            status="ZATWIERDZONY",
            uwagi=f"Rozliczenie niedoboru inwentaryzacji {sheet.numer}: {payload.komentarz}",
            utworzyl_id=kierownik.id,
            zatwierdzil_id=kierownik.id,
            zatwierdzono_utc=now,
        )
        db.add(rw_kor)
        db.flush()
        for idx, poz in enumerate(shortage_lines, start=1):
            lot = lock_batch_for_update(db, poz.partia_id)
            shortage = q3(abs(poz.roznica_kg))
            lot.masa_dostepna_kg = max(D_ZERO, q3(lot.masa_dostepna_kg - shortage))
            if lot.masa_dostepna_kg == D_ZERO:
                lot.status = "ZUZYTA"
            db.add(
                PozycjaDokumentu(
                    dokument_id=rw_kor.id,
                    lp=idx,
                    asortyment_id=lot.asortyment_id,
                    partia_id=lot.id,
                    lokalizacja_id=lot.lokalizacja_id,
                    ilosc_fizyczna_kg=shortage,
                    ilosc_rozliczeniowa_kg=shortage,
                )
            )
            db.add(
                RuchMagazynowy(
                    dokument_id=rw_kor.id,
                    typ_dokumentu="RW-kor",
                    partia_id=lot.id,
                    lokalizacja_zrodlowa_id=lot.lokalizacja_id,
                    asortyment_id=lot.asortyment_id,
                    ilosc_kg=shortage,
                    kierunek="KOREKTA_MINUS",
                    stan_po_ruchu_kg=lot.masa_dostepna_kg,
                    uzytkownik_id=kierownik.id,
                )
            )
        created_docs.append(rw_kor.numer)

    # Odblokowanie strefy
    locs = db.scalars(
        select(LokalizacjaMagazynowa).where(LokalizacjaMagazynowa.strefa == sheet.zakres_strefa)
    ).all()
    for loc in locs:
        loc.czy_zablokowana = False
        loc.powod_blokady = None

    sheet.status = "ROZLICZONA"
    sheet.rozliczyl_id = kierownik.id
    sheet.zamknieto_utc = now
    sheet.komentarz = payload.komentarz

    record_audit(
        db,
        akcja="ROZLICZENIE_INWENTARYZACJI",
        zasob="INWENTARYZACJA",
        zasob_id=sheet.id,
        zmiana_stanu={"numer": sheet.numer, "dokumenty_korygujace": created_docs, "komentarz": payload.komentarz},
        user=kierownik,
        adres_ip=client_ip_from_request(request),
    )
    db.commit()
    db.refresh(sheet)
    return {"arkusz": _serialize_inventory(sheet), "dokumenty_korygujace": created_docs}


@router.post("/inwentaryzacje/{sheet_id}/anuluj")
def cancel_inventory(
    sheet_id: str,
    payload: CancelDocRequest,
    request: Request,
    kierownik: Uzytkownik = Depends(require_roles("KIER_MAG")),
    db: Session = Depends(get_db),
):
    sheet = db.get(ArkuszInwentaryzacji, sheet_id)
    if sheet is None or sheet.status != "OTWARTA":
        raise HTTPException(status_code=409, detail="Anulować można tylko otwarty arkusz inwentaryzacji.")

    locs = db.scalars(
        select(LokalizacjaMagazynowa).where(LokalizacjaMagazynowa.strefa == sheet.zakres_strefa)
    ).all()
    for loc in locs:
        loc.czy_zablokowana = False
        loc.powod_blokady = None

    sheet.status = "ANULOWANA"
    sheet.zamknieto_utc = datetime.now(timezone.utc)
    sheet.komentarz = f"Anulowano: {payload.powod}"

    record_audit(
        db,
        akcja="ANULOWANIE_INWENTARYZACJI",
        zasob="INWENTARYZACJA",
        zasob_id=sheet.id,
        zmiana_stanu={"numer": sheet.numer, "powod": payload.powod},
        user=kierownik,
        adres_ip=client_ip_from_request(request),
    )
    db.commit()
    db.refresh(sheet)
    return _serialize_inventory(sheet)


@router.get("/raport-rotacji")
def stock_and_turnover_report(
    na_dzien: date | None = None,
    od_dnia: date | None = None,
    do_dnia: date | None = None,
    user: Uzytkownik = Depends(require_roles("KIER_MAG", "ADMIN")),
    db: Session = Depends(get_db),
):
    """UC-05.1: Raport ilościowo-wartościowy stanów oraz rotacji (z wyłączeniem transferów MM)."""
    target_day = na_dzien or date.today()
    start_day = od_dnia or date(target_day.year, target_day.month, 1)
    end_day = do_dnia or target_day
    if start_day > end_day:
        raise HTTPException(status_code=422, detail="Data początkowa nie może być późniejsza niż końcowa.")

    target_dt = datetime.combine(target_day, time.max, tzinfo=timezone.utc)
    start_dt = datetime.combine(start_day, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(end_day, time.max, tzinfo=timezone.utc)

    items = db.scalars(select(Asortyment).where(Asortyment.czy_aktywny.is_(True)).order_by(Asortyment.kategoria, Asortyment.nazwa)).all()
    all_movements = db.scalars(select(RuchMagazynowy).order_by(RuchMagazynowy.utworzono_utc)).all()

    rows = []
    for item in items:
        item_mvs = [m for m in all_movements if m.asortyment_id == item.id]

        def _stock_until(cutoff: datetime) -> Decimal:
            total = D_ZERO
            for m in item_mvs:
                mv_dt = m.utworzono_utc if m.utworzono_utc.tzinfo else m.utworzono_utc.replace(tzinfo=timezone.utc)
                if mv_dt > cutoff:
                    continue
                if m.kierunek in ("PRZYCHOD", "KOREKTA_PLUS"):
                    total += m.ilosc_kg
                elif m.kierunek in ("ROZCHOD", "KOREKTA_MINUS"):
                    total -= m.ilosc_kg
            # Uwzględnij też początkowe partie bez ruchów wstecznych jeśli utworzono je na starcie
            return max(D_ZERO, q3(total))

        stan_na_dzien = _stock_until(target_dt)
        # Jeśli dla towaru istnieją partie bez historii ruchów (np. partie WG z seeda), dodaj ich saldo bazowe
        seeded_lots = db.scalars(
            select(PartiaMagazynowa).where(PartiaMagazynowa.asortyment_id == item.id)
        ).all()
        if not item_mvs and seeded_lots:
            stan_na_dzien = sum((l.masa_dostepna_kg for l in seeded_lots), D_ZERO)

        # Rozchód w okresie BEZ transferów MM (UC-05.1 krok 4)
        rozchod_okres = D_ZERO
        for m in item_mvs:
            mv_dt = m.utworzono_utc if m.utworzono_utc.tzinfo else m.utworzono_utc.replace(tzinfo=timezone.utc)
            if start_dt <= mv_dt <= end_dt and m.kierunek == "ROZCHOD" and m.typ_dokumentu != "MM":
                rozchod_okres = q3(rozchod_okres + m.ilosc_kg)

        sredni_stan = stan_na_dzien
        rotacja = str(q3(rozchod_okres / sredni_stan)) if sredni_stan > D_ZERO else "Nieokreślona (stan = 0)"
        wartosc = q2(stan_na_dzien * item.cena_bazowa_netto) if item.cena_bazowa_netto > D_ZERO else None

        rows.append(
            {
                "asortyment_id": item.id,
                "kod": item.kod_wewnetrzny,
                "nazwa": item.nazwa,
                "kategoria": item.kategoria,
                "stan_kg": str(stan_na_dzien),
                "wartosc_netto_pln": str(wartosc) if wartosc is not None else "Brak wyceny",
                "rozchod_okres_kg": str(rozchod_okres),
                "rotacja": rotacja,
            }
        )

    return {
        "na_dzien": target_day.isoformat(),
        "okres_rotacji": f"{start_day.isoformat()} .. {end_day.isoformat()}",
        "uwaga": "Transfery MM nie są traktowane jako zużycie ani sprzedaż.",
        "pozycje": rows,
    }


@router.post("/dokumenty/{doc_id}/anuluj")
def cancel_document(
    doc_id: str,
    payload: CancelDocRequest,
    request: Request,
    kierownik: Uzytkownik = Depends(require_roles("KIER_MAG")),
    db: Session = Depends(get_db),
):
    doc = db.get(DokumentMagazynowy, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono dokumentu.")
    if doc.status == "ANULOWANY":
        raise HTTPException(status_code=409, detail="Dokument jest już anulowany.")
    if doc.typ == "WZ" and doc.czy_zafakturowany:
        raise HTTPException(status_code=409, detail="Nie można anulować dokumentu WZ powiązanego z fakturą FS.")

    if doc.typ == "PZ":
        for poz in doc.pozycje:
            if poz.partia_id:
                lot = lock_batch_for_update(db, poz.partia_id)
                if lot and lot.masa_dostepna_kg < lot.masa_poczatkowa_kg:
                    raise HTTPException(status_code=409, detail="Partia z tego PZ została już częściowo zużyta lub przesunięta.")
                if lot:
                    lot.masa_dostepna_kg = D_ZERO
                    lot.status = "ZABLOKOWANA"
                    lot.powod_blokady = f"Anulowanie {doc.numer}: {payload.powod}"
    elif doc.typ == "WZ":
        for poz in doc.pozycje:
            if poz.partia_id:
                lot = lock_batch_for_update(db, poz.partia_id)
                if lot:
                    lot.masa_dostepna_kg = q3(lot.masa_dostepna_kg + poz.ilosc_rozliczeniowa_kg)
                    if lot.status == "ZUZYTA":
                        lot.status = "DOSTEPNA"
    else:
        raise HTTPException(status_code=422, detail=f"Anulowanie z poziomu tego ekranu dotyczy PZ/WZ (typ: {doc.typ}).")

    doc.status = "ANULOWANY"
    doc.uwagi = f"ANULOWANO ({kierownik.login}): {payload.powod}"
    record_audit(
        db,
        akcja="ANULOWANIE_DOKUMENTU",
        zasob="DOKUMENT_MAGAZYNOWY",
        zasob_id=doc.id,
        zmiana_stanu={"numer": doc.numer, "typ": doc.typ, "powod": payload.powod},
        user=kierownik,
        adres_ip=client_ip_from_request(request),
    )
    db.commit()
    return {"id": doc.id, "numer": doc.numer, "status": doc.status}
