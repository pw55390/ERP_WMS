from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.db.session import get_db
from app.models.entities import (
    Asortyment,
    CennikKontrahenta,
    DokumentMagazynowy,
    FakturaVAT,
    Kontrahent,
    LokalizacjaMagazynowa,
    PartiaMagazynowa,
    PozycjaDokumentu,
    PozycjaFaktury,
    PozycjaZamowienia,
    RuchMagazynowy,
    Uzytkownik,
    ZamowienieSprzedazy,
)
from app.schemas.dto import (
    FakturaFromWzRequest,
    FakturaKorektaRequest,
    FzCreateRequest,
    WzCreateApproveRequest,
    ZamowienieCreateRequest,
)
from app.services.audit import client_ip_from_request, record_audit
from app.services.common import (
    D_ZERO,
    lock_batch_for_update,
    lock_location_for_update,
    next_document_number,
    q2,
    q3,
)
from app.services.pdf_service import render_invoice_pdf, render_warehouse_doc_pdf

router = APIRouter(tags=["P3 - Sprzedaż, FEFO, WZ i Fakturowanie"])


def _resolve_customer_price(db: Session, kontrahent_id: str, asortyment: Asortyment) -> tuple[Decimal, bool]:
    entry = db.scalar(
        select(CennikKontrahenta).where(
            CennikKontrahenta.kontrahent_id == kontrahent_id,
            CennikKontrahenta.asortyment_id == asortyment.id,
        )
    )
    if entry is not None:
        return q3(entry.cena_netto), True
    return q3(asortyment.cena_bazowa_netto), False


def _serialize_order(o: ZamowienieSprzedazy) -> dict:
    return {
        "id": o.id,
        "numer": o.numer,
        "odbiorca_id": o.odbiorca_id,
        "odbiorca_nazwa": o.odbiorca.nazwa,
        "data_zamowienia": o.data_zamowienia.isoformat(),
        "data_wydania": o.data_wydania.isoformat(),
        "status": o.status,
        "uwagi": o.uwagi,
        "pozycje": [
            {
                "id": p.id,
                "lp": p.lp,
                "asortyment_id": p.asortyment_id,
                "asortyment_nazwa": p.asortyment.nazwa,
                "ilosc_zamowiona_kg": str(p.ilosc_zamowiona_kg),
                "ilosc_wydana_kg": str(p.ilosc_wydana_kg),
                "pozostalo_kg": str(q3(p.ilosc_zamowiona_kg - p.ilosc_wydana_kg)),
                "cena_netto": str(p.cena_netto),
                "cena_z_cennika": p.cena_z_cennika,
            }
            for p in o.pozycje
        ],
    }


def _serialize_wz(d: DokumentMagazynowy) -> dict:
    return {
        "id": d.id,
        "typ": d.typ,
        "numer": d.numer,
        "status": d.status,
        "kontrahent_id": d.kontrahent_id,
        "kontrahent_nazwa": d.kontrahent.nazwa if d.kontrahent else None,
        "zamowienie_id": d.zamowienie_id,
        "data_wydania": d.data_wydania.isoformat() if d.data_wydania else None,
        "data_wystawienia": d.data_wystawienia.isoformat(),
        "nr_rejestracyjny": d.nr_rejestracyjny,
        "czy_zafakturowany": d.czy_zafakturowany,
        "faktura_id": d.faktura_id,
        "liczba_wydrukow": d.liczba_wydrukow,
        "uwagi": d.uwagi,
        "pozycje": [
            {
                "id": p.id,
                "lp": p.lp,
                "asortyment_id": p.asortyment_id,
                "asortyment_nazwa": p.asortyment.nazwa,
                "partia_id": p.partia_id,
                "kod_partii": p.partia.kod_partii if p.partia else None,
                "data_waznosci": p.partia.data_waznosci.isoformat() if p.partia and p.partia.data_waznosci else None,
                "lokalizacja_kod": p.lokalizacja.kod if p.lokalizacja else None,
                "ilosc_kg": str(p.ilosc_rozliczeniowa_kg),
                "cena_netto": str(p.cena_netto),
                "stawka_vat": str(p.stawka_vat),
                "odstepstwo_fefo_powod": p.odstepstwo_fefo_powod,
            }
            for p in d.pozycje
        ],
    }


def _serialize_invoice(f: FakturaVAT) -> dict:
    return {
        "id": f.id,
        "typ": f.typ,
        "numer": f.numer,
        "korekta_do_faktury_id": f.korekta_do_faktury_id,
        "kontrahent_id": f.kontrahent_id,
        "kontrahent_nazwa": f.kontrahent.nazwa,
        "kontrahent_nip": f.kontrahent.nip,
        "data_wystawienia": f.data_wystawienia.isoformat(),
        "termin_platnosci": f.termin_platnosci.isoformat(),
        "forma_platnosci": f.forma_platnosci,
        "status": f.status,
        "wartosc_netto": str(f.wartosc_netto),
        "wartosc_vat": str(f.wartosc_vat),
        "wartosc_brutto": str(f.wartosc_brutto),
        "liczba_wydrukow": f.liczba_wydrukow,
        "uwagi": f.uwagi,
        "pozycje": [
            {
                "id": p.id,
                "lp": p.lp,
                "asortyment_id": p.asortyment_id,
                "asortyment_nazwa": p.asortyment.nazwa,
                "dokument_wz_id": p.dokument_wz_id,
                "ilosc_kg": str(p.ilosc_kg),
                "cena_netto": str(p.cena_netto),
                "cena_z_cennika": str(p.cena_z_cennika),
                "czy_cena_zmieniona_recznie": p.czy_cena_zmieniona_recznie,
                "powod_zmiany_ceny": p.powod_zmiany_ceny,
                "stawka_vat": str(p.stawka_vat),
                "wartosc_netto": str(p.wartosc_netto),
                "wartosc_vat": str(p.wartosc_vat),
                "wartosc_brutto": str(p.wartosc_brutto),
            }
            for p in f.pozycje
        ],
    }


@router.get("/api/p3/zamowienia")
def list_orders(
    user: Uzytkownik = Depends(require_roles("MAG_WG", "FAKT_KS", "KIER_MAG", "ADMIN")),
    db: Session = Depends(get_db),
):
    rows = db.scalars(select(ZamowienieSprzedazy).order_by(ZamowienieSprzedazy.utworzono_utc.desc())).all()
    return [_serialize_order(o) for o in rows]


@router.post("/api/p3/zamowienia", status_code=status.HTTP_201_CREATED)
def create_order(
    payload: ZamowienieCreateRequest,
    request: Request,
    user: Uzytkownik = Depends(require_roles("FAKT_KS", "KIER_MAG", "MAG_WG")),
    db: Session = Depends(get_db),
):
    buyer = db.get(Kontrahent, payload.odbiorca_id)
    if buyer is None or buyer.typ not in ("ODBIORCA", "OBA"):
        raise HTTPException(status_code=422, detail="Wybrany kontrahent nie jest odbiorcą.")

    order_num = next_document_number(db, "ZS", ZamowienieSprzedazy)
    order = ZamowienieSprzedazy(
        numer=order_num,
        odbiorca_id=buyer.id,
        data_zamowienia=date.today(),
        data_wydania=payload.data_wydania,
        status="NOWE",
        uwagi=payload.uwagi,
        utworzono_przez_id=user.id,
    )
    db.add(order)
    db.flush()

    for idx, line in enumerate(payload.pozycje, start=1):
        item = db.get(Asortyment, line.asortyment_id)
        if item is None or item.kategoria not in ("WYROB_GOTOWY", "PRODUKT_UBOCZNY"):
            raise HTTPException(status_code=422, detail="Zamówienie sprzedaży może dotyczyć tylko wyrobów gotowych lub ubocznych.")
        price, from_pricelist = _resolve_customer_price(db, buyer.id, item)
        db.add(
            PozycjaZamowienia(
                zamowienie_id=order.id,
                lp=idx,
                asortyment_id=item.id,
                ilosc_zamowiona_kg=q3(line.ilosc_zamowiona_kg),
                ilosc_wydana_kg=D_ZERO,
                cena_netto=price,
                cena_z_cennika=from_pricelist,
            )
        )

    record_audit(
        db,
        akcja="UTWORZENIE_ZAMOWIENIA_SPRZEDAZY",
        zasob="ZAMOWIENIE",
        zasob_id=order.id,
        zmiana_stanu={"numer": order.numer, "odbiorca": buyer.nazwa, "data_wydania": payload.data_wydania.isoformat()},
        user=user,
        adres_ip=client_ip_from_request(request),
    )
    db.commit()
    db.refresh(order)
    return _serialize_order(order)


@router.get("/api/p3/zamowienia/{order_id}/podpowiedz-fefo")
def suggest_fefo(
    order_id: str,
    data_wydania: date | None = None,
    user: Uzytkownik = Depends(require_roles("MAG_WG", "KIER_MAG", "FAKT_KS")),
    db: Session = Depends(get_db),
):
    """StrategiaWydanFEFO: sortuje dopuszczone partie rosnąco po dacie ważności oraz jawnie wskazuje zablokowane/przeterminowane."""
    order = db.get(ZamowienieSprzedazy, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono zamówienia sprzedaży.")

    check_date = max(date.today(), data_wydania or order.data_wydania)
    suggestions = []

    for poz in order.pozycje:
        remaining = q3(poz.ilosc_zamowiona_kg - poz.ilosc_wydana_kg)
        all_lots = db.scalars(
            select(PartiaMagazynowa)
            .where(
                PartiaMagazynowa.asortyment_id == poz.asortyment_id,
                PartiaMagazynowa.masa_dostepna_kg > D_ZERO,
            )
            .order_by(PartiaMagazynowa.data_waznosci.asc(), PartiaMagazynowa.data_przyjecia.asc())
        ).all()

        eligible = []
        blocked = []
        allocated_acc = D_ZERO

        for lot in all_lots:
            loc = db.get(LokalizacjaMagazynowa, lot.lokalizacja_id)
            is_expired = lot.data_waznosci is not None and lot.data_waznosci < check_date
            is_loc_locked = loc.czy_zablokowana if loc else True
            is_lot_ok = lot.status == "DOSTEPNA" and not is_expired and not is_loc_locked

            entry = {
                "partia_id": lot.id,
                "kod_partii": lot.kod_partii,
                "lokalizacja_kod": loc.kod if loc else "-",
                "lokalizacja_zablokowana": is_loc_locked,
                "masa_dostepna_kg": str(lot.masa_dostepna_kg),
                "data_waznosci": lot.data_waznosci.isoformat() if lot.data_waznosci else None,
                "status": lot.status,
                "przeterminowana_na_dzien_wydania": is_expired,
            }
            if is_lot_ok:
                suggested_qty = min(lot.masa_dostepna_kg, max(D_ZERO, remaining - allocated_acc))
                entry["sugerowana_ilosc_kg"] = str(q3(suggested_qty))
                allocated_acc = q3(allocated_acc + suggested_qty)
                eligible.append(entry)
            else:
                reason = []
                if is_expired:
                    reason.append(f"Termin ważności ({lot.data_waznosci}) upłynął przed datą wydania ({check_date})")
                if lot.status != "DOSTEPNA":
                    reason.append(f"Status partii: {lot.status}")
                if is_loc_locked:
                    reason.append("Lokalizacja zablokowana (inwentaryzacja)")
                entry["powod_blokady"] = "; ".join(reason)
                blocked.append(entry)

        suggestions.append(
            {
                "asortyment_id": poz.asortyment_id,
                "asortyment_nazwa": poz.asortyment.nazwa,
                "pozostalo_do_wydania_kg": str(remaining),
                "pokrycie_pelne": allocated_acc >= remaining,
                "dostepne_fefo": eligible,
                "zablokowane_partie": blocked,
            }
        )

    return {"zamowienie_id": order.id, "data_weryfikacji_waznosci": check_date.isoformat(), "pozycje": suggestions}


@router.get("/api/p3/wz")
def list_wz(
    user: Uzytkownik = Depends(require_roles("MAG_WG", "FAKT_KS", "KIER_MAG", "ADMIN")),
    db: Session = Depends(get_db),
):
    rows = db.scalars(
        select(DokumentMagazynowy)
        .where(DokumentMagazynowy.typ == "WZ")
        .order_by(DokumentMagazynowy.utworzono_utc.desc())
    ).all()
    return [_serialize_wz(d) for d in rows]


@router.post("/api/p3/wz/kompletuj-i-zatwierdz", status_code=status.HTTP_201_CREATED)
def create_and_approve_wz(
    payload: WzCreateApproveRequest,
    request: Request,
    user: Uzytkownik = Depends(require_roles("MAG_WG", "KIER_MAG")),
    db: Session = Depends(get_db),
):
    order = db.get(ZamowienieSprzedazy, payload.zamowienie_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono zamówienia sprzedaży.")
    if order.status in ("ZREALIZOWANE", "ANULOWANE"):
        raise HTTPException(status_code=409, detail=f"Zamówienie ma status {order.status} i nie podlega kompletacji.")

    today = date.today()
    effective_check_date = max(today, payload.data_wydania)
    now = datetime.now(timezone.utc)
    wz_num = next_document_number(db, "WZ", DokumentMagazynowy)

    wz = DokumentMagazynowy(
        typ="WZ",
        numer=wz_num,
        data_wystawienia=now,
        status="ZATWIERDZONY",
        kontrahent_id=order.odbiorca_id,
        zamowienie_id=order.id,
        nr_rejestracyjny=payload.nr_rejestracyjny,
        data_wydania=payload.data_wydania,
        uwagi=payload.uwagi,
        utworzyl_id=user.id,
        zatwierdzil_id=user.id,
        zatwierdzono_utc=now,
    )
    db.add(wz)
    db.flush()

    order_lines_by_item = {p.asortyment_id: p for p in order.pozycje}

    for idx, pick in enumerate(payload.pozycje, start=1):
        lot = lock_batch_for_update(db, pick.partia_id)
        if lot is None:
            raise HTTPException(status_code=404, detail=f"Nie znaleziono partii {pick.partia_id}.")
        if lot.asortyment_id != pick.asortyment_id:
            raise HTTPException(status_code=422, detail=f"Partia {lot.kod_partii} nie odpowiada wybranemu asortymentowi.")

        # RF-03.3 / UC-03.3: BEZWZGLĘDNA BLOKADA SERWEROWA PARTII PRZETERMINOWANYCH (bez możliwości obejścia dla żadnej roli!)
        if lot.data_waznosci is not None and lot.data_waznosci < effective_check_date:
            db.rollback()
            record_audit(
                db,
                akcja="BLOKADA_WYDANIA_PARTII_PRZETERMINOWANEJ",
                zasob="PARTIA_MAGAZYNOWA",
                zasob_id=lot.id,
                zmiana_stanu={
                    "kod_partii": lot.kod_partii,
                    "data_waznosci": lot.data_waznosci.isoformat(),
                    "data_wydania": payload.data_wydania.isoformat(),
                    "zamowienie": order.numer,
                },
                user=user,
                adres_ip=client_ip_from_request(request),
                komentarz="Próba zatwierdzenia WZ z partią przeterminowaną lub upływającą przed datą wydania",
            )
            db.commit()
            raise HTTPException(
                status_code=422,
                detail=(
                    f"BLOKADA RF-03.3: Partia {lot.kod_partii} ma termin przydatności {lot.data_waznosci.isoformat()}, "
                    f"który minął lub upłynie przed datą wydania ({effective_check_date.isoformat()}). Wydanie jest zablokowane."
                ),
            )

        if lot.status != "DOSTEPNA":
            raise HTTPException(status_code=409, detail=f"Partia {lot.kod_partii} ma status {lot.status} i jest niedopuszczona.")

        loc = lock_location_for_update(db, lot.lokalizacja_id)
        if loc is None or loc.czy_zablokowana:
            raise HTTPException(status_code=409, detail=f"Lokalizacja partii {lot.kod_partii} jest objęta blokadą inwentaryzacyjną.")

        qty = q3(pick.ilosc_kg)
        if lot.masa_dostepna_kg < qty:
            raise HTTPException(
                status_code=409,
                detail=f"Niewystarczający stan partii {lot.kod_partii} (dostępne: {lot.masa_dostepna_kg} kg, żądane: {qty} kg).",
            )

        ord_line = order_lines_by_item.get(pick.asortyment_id)
        if ord_line is None:
            raise HTTPException(status_code=422, detail="Asortyment nie figuruje na wybranym zamówieniu.")

        # Sprawdź czy istnieją dopuszczone partie z krótszym terminem (odstępstwo FEFO wymaga odnotowania)
        earlier_lot = db.scalar(
            select(PartiaMagazynowa).where(
                PartiaMagazynowa.asortyment_id == pick.asortyment_id,
                PartiaMagazynowa.status == "DOSTEPNA",
                PartiaMagazynowa.masa_dostepna_kg > D_ZERO,
                PartiaMagazynowa.data_waznosci >= effective_check_date,
                PartiaMagazynowa.data_waznosci < lot.data_waznosci,
            )
        )
        fefo_note = pick.odstepstwo_fefo_powod
        if earlier_lot is not None and not fefo_note:
            fefo_note = f"Odstępstwo od kolejności FEFO (dostępna wcześniejsza partia {earlier_lot.kod_partii})"

        lot.masa_dostepna_kg = q3(lot.masa_dostepna_kg - qty)
        if lot.masa_dostepna_kg == D_ZERO:
            lot.status = "ZUZYTA"

        ord_line.ilosc_wydana_kg = q3(ord_line.ilosc_wydana_kg + qty)

        db.add(
            PozycjaDokumentu(
                dokument_id=wz.id,
                lp=idx,
                asortyment_id=lot.asortyment_id,
                partia_id=lot.id,
                lokalizacja_id=loc.id,
                ilosc_fizyczna_kg=qty,
                ilosc_rozliczeniowa_kg=qty,
                cena_netto=ord_line.cena_netto,
                stawka_vat=lot.asortyment.stawka_vat,
                odstepstwo_fefo_powod=fefo_note,
            )
        )
        db.add(
            RuchMagazynowy(
                dokument_id=wz.id,
                typ_dokumentu="WZ",
                partia_id=lot.id,
                lokalizacja_zrodlowa_id=loc.id,
                asortyment_id=lot.asortyment_id,
                ilosc_kg=qty,
                kierunek="ROZCHOD",
                stan_po_ruchu_kg=lot.masa_dostepna_kg,
                uzytkownik_id=user.id,
            )
        )

    all_done = all(p.ilosc_wydana_kg >= p.ilosc_zamowiona_kg for p in order.pozycje)
    order.status = "ZREALIZOWANE" if all_done else "CZESCIOWO_WYDANE"

    record_audit(
        db,
        akcja="ZATWIERDZENIE_WZ",
        zasob="DOKUMENT_WZ",
        zasob_id=wz.id,
        zmiana_stanu={
            "numer_wz": wz.numer,
            "zamowienie": order.numer,
            "status_zamowienia": order.status,
            "liczba_pozycji": len(payload.pozycje),
        },
        user=user,
        adres_ip=client_ip_from_request(request),
    )
    db.commit()
    db.refresh(wz)
    return _serialize_wz(wz)


@router.get("/api/p3/faktury")
def list_invoices(
    user: Uzytkownik = Depends(require_roles("FAKT_KS", "KIER_MAG", "ADMIN")),
    db: Session = Depends(get_db),
):
    rows = db.scalars(select(FakturaVAT).order_by(FakturaVAT.utworzono_utc.desc())).all()
    return [_serialize_invoice(f) for f in rows]


@router.post("/api/p3/faktury/z-wz", status_code=status.HTTP_201_CREATED)
def create_invoice_from_wz(
    payload: FakturaFromWzRequest,
    request: Request,
    user: Uzytkownik = Depends(require_roles("FAKT_KS")),
    db: Session = Depends(get_db),
):
    wz_docs = [db.get(DokumentMagazynowy, wid) for wid in payload.wz_ids]
    if any(w is None for w in wz_docs):
        raise HTTPException(status_code=404, detail="Co najmniej jeden wskazany dokument WZ nie istnieje.")
    if any(w.typ != "WZ" or w.status != "ZATWIERDZONY" for w in wz_docs):
        raise HTTPException(status_code=422, detail="Fakturę FS można wystawić wyłącznie do zatwierdzonych dokumentów WZ.")
    if any(w.czy_zafakturowany for w in wz_docs):
        raise HTTPException(status_code=409, detail="Jeden z wybranych dokumentów WZ został już zafakturowany.")

    buyer_ids = {w.kontrahent_id for w in wz_docs}
    if len(buyer_ids) != 1:
        raise HTTPException(status_code=422, detail="Jedna faktura FS może rozliczać dokumenty WZ wyłącznie jednego odbiorcy.")

    buyer = db.get(Kontrahent, next(iter(buyer_ids)))
    if buyer is None:
        raise HTTPException(status_code=422, detail="Brak danych odbiorcy.")

    overrides = {o.asortyment_id: o for o in payload.nadpisania_cen}
    today = date.today()
    due_date = payload.termin_platnosci or (today + timedelta(days=buyer.termin_platnosci_dni))
    pay_method = payload.forma_platnosci or buyer.forma_platnosci
    fs_num = next_document_number(db, "FS", FakturaVAT)
    now = datetime.now(timezone.utc)

    inv = FakturaVAT(
        typ="FS",
        numer=fs_num,
        kontrahent_id=buyer.id,
        data_wystawienia=today,
        termin_platnosci=due_date,
        forma_platnosci=pay_method,
        status="ZATWIERDZONA",
        uwagi=payload.uwagi,
        utworzyl_id=user.id,
        zatwierdzil_id=user.id,
        zatwierdzono_utc=now,
    )
    db.add(inv)
    db.flush()

    total_netto = D_ZERO
    total_vat = D_ZERO
    total_brutto = D_ZERO
    lp = 1

    for wz in wz_docs:
        for poz in wz.pozycje:
            catalog_price, _ = _resolve_customer_price(db, buyer.id, poz.asortyment)
            unit_price = catalog_price
            changed_manually = False
            change_reason = None

            if poz.asortyment_id in overrides:
                ov = overrides[poz.asortyment_id]
                unit_price = q3(ov.nowa_cena_netto)
                changed_manually = unit_price != catalog_price
                change_reason = ov.powod_zmiany.strip()
                if changed_manually:
                    record_audit(
                        db,
                        akcja="RECZNA_ZMIANA_CENY_FS",
                        zasob="FAKTURA_VAT",
                        zasob_id=inv.id,
                        zmiana_stanu={
                            "numer_fs": fs_num,
                            "asortyment": poz.asortyment.nazwa,
                            "cena_cennik_netto": str(catalog_price),
                            "nowa_cena_netto": str(unit_price),
                            "powod": change_reason,
                        },
                        user=user,
                        adres_ip=client_ip_from_request(request),
                    )

            line_netto = q2(poz.ilosc_rozliczeniowa_kg * unit_price)
            line_vat = q2(line_netto * (poz.stawka_vat / Decimal("100")))
            line_brutto = q2(line_netto + line_vat)

            total_netto = q2(total_netto + line_netto)
            total_vat = q2(total_vat + line_vat)
            total_brutto = q2(total_brutto + line_brutto)

            db.add(
                PozycjaFaktury(
                    faktura_id=inv.id,
                    lp=lp,
                    asortyment_id=poz.asortyment_id,
                    dokument_wz_id=wz.id,
                    ilosc_kg=poz.ilosc_rozliczeniowa_kg,
                    cena_netto=unit_price,
                    cena_z_cennika=catalog_price,
                    czy_cena_zmieniona_recznie=changed_manually,
                    powod_zmiany_ceny=change_reason,
                    stawka_vat=poz.stawka_vat,
                    wartosc_netto=line_netto,
                    wartosc_vat=line_vat,
                    wartosc_brutto=line_brutto,
                )
            )
            lp += 1

        wz.czy_zafakturowany = True
        wz.faktura_id = inv.id

    inv.wartosc_netto = total_netto
    inv.wartosc_vat = total_vat
    inv.wartosc_brutto = total_brutto

    record_audit(
        db,
        akcja="WYSTAWIENIE_FAKTURY_FS",
        zasob="FAKTURA_VAT",
        zasob_id=inv.id,
        zmiana_stanu={
            "numer_fs": inv.numer,
            "odbiorca": buyer.nazwa,
            "wz_ids": payload.wz_ids,
            "wartosc_brutto": str(inv.wartosc_brutto),
        },
        user=user,
        adres_ip=client_ip_from_request(request),
    )
    db.commit()
    db.refresh(inv)
    return _serialize_invoice(inv)


@router.post("/api/p3/faktury/{inv_id}/korekta", status_code=status.HTTP_201_CREATED)
def create_invoice_correction(
    inv_id: str,
    payload: FakturaKorektaRequest,
    request: Request,
    user: Uzytkownik = Depends(require_roles("FAKT_KS")),
    db: Session = Depends(get_db),
):
    orig = db.get(FakturaVAT, inv_id)
    if orig is None or orig.typ != "FS" or orig.status != "ZATWIERDZONA":
        raise HTTPException(status_code=404, detail="Korygować można wyłącznie zatwierdzoną fakturę FS.")

    overrides = {o.asortyment_id: o for o in payload.nowe_ceny}
    kor_num = next_document_number(db, "FS-KOR", FakturaVAT)
    now = datetime.now(timezone.utc)
    today = date.today()

    kor = FakturaVAT(
        typ="FS-KOR",
        numer=kor_num,
        korekta_do_faktury_id=orig.id,
        kontrahent_id=orig.kontrahent_id,
        data_wystawienia=today,
        termin_platnosci=today + timedelta(days=orig.kontrahent.termin_platnosci_dni),
        forma_platnosci=orig.forma_platnosci,
        status="ZATWIERDZONA",
        uwagi=f"Korekta do {orig.numer}: {payload.uwagi}",
        utworzyl_id=user.id,
        zatwierdzil_id=user.id,
        zatwierdzono_utc=now,
    )
    db.add(kor)
    db.flush()

    delta_netto = D_ZERO
    delta_vat = D_ZERO
    delta_brutto = D_ZERO
    lp = 1

    for poz in orig.pozycje:
        if poz.asortyment_id not in overrides:
            continue
        ov = overrides[poz.asortyment_id]
        new_price = q3(ov.nowa_cena_netto)
        new_netto = q2(poz.ilosc_kg * new_price)
        diff_netto = q2(new_netto - poz.wartosc_netto)
        diff_vat = q2(diff_netto * (poz.stawka_vat / Decimal("100")))
        diff_brutto = q2(diff_netto + diff_vat)

        delta_netto = q2(delta_netto + diff_netto)
        delta_vat = q2(delta_vat + diff_vat)
        delta_brutto = q2(delta_brutto + diff_brutto)

        db.add(
            PozycjaFaktury(
                faktura_id=kor.id,
                lp=lp,
                asortyment_id=poz.asortyment_id,
                dokument_wz_id=poz.dokument_wz_id,
                ilosc_kg=poz.ilosc_kg,
                cena_netto=new_price,
                cena_z_cennika=poz.cena_z_cennika,
                czy_cena_zmieniona_recznie=True,
                powod_zmiany_ceny=ov.powod_zmiany,
                stawka_vat=poz.stawka_vat,
                wartosc_netto=diff_netto,
                wartosc_vat=diff_vat,
                wartosc_brutto=diff_brutto,
            )
        )
        lp += 1

    if lp == 1:
        raise HTTPException(status_code=422, detail="Żadna z pozycji korygowanych nie pasuje do faktury źródłowej.")

    kor.wartosc_netto = delta_netto
    kor.wartosc_vat = delta_vat
    kor.wartosc_brutto = delta_brutto

    record_audit(
        db,
        akcja="WYSTAWIENIE_KOREKTY_FS",
        zasob="FAKTURA_VAT",
        zasob_id=kor.id,
        zmiana_stanu={"numer": kor.numer, "faktura_zrodlowa": orig.numer, "roznica_brutto": str(delta_brutto)},
        user=user,
        adres_ip=client_ip_from_request(request),
    )
    db.commit()
    db.refresh(kor)
    return _serialize_invoice(kor)


@router.post("/api/p3/faktury/fz", status_code=status.HTTP_201_CREATED)
def register_purchase_invoice_fz(
    payload: FzCreateRequest,
    request: Request,
    user: Uzytkownik = Depends(require_roles("FAKT_KS")),
    db: Session = Depends(get_db),
):
    supplier = db.get(Kontrahent, payload.kontrahent_id)
    item = db.get(Asortyment, payload.asortyment_id)
    if supplier is None or item is None:
        raise HTTPException(status_code=422, detail="Nieprawidłowy dostawca lub asortyment.")

    fz_num = next_document_number(db, "FZ", FakturaVAT)
    now = datetime.now(timezone.utc)
    today = date.today()
    netto = q2(payload.ilosc_kg * payload.cena_netto)
    vat = q2(netto * (payload.stawka_vat / Decimal("100")))
    brutto = q2(netto + vat)

    fz = FakturaVAT(
        typ="FZ",
        numer=fz_num,
        kontrahent_id=supplier.id,
        data_wystawienia=today,
        termin_platnosci=today + timedelta(days=supplier.termin_platnosci_dni),
        forma_platnosci=supplier.forma_platnosci,
        status="ZATWIERDZONA",
        wartosc_netto=netto,
        wartosc_vat=vat,
        wartosc_brutto=brutto,
        uwagi=payload.uwagi,
        utworzyl_id=user.id,
        zatwierdzil_id=user.id,
        zatwierdzono_utc=now,
    )
    db.add(fz)
    db.flush()
    db.add(
        PozycjaFaktury(
            faktura_id=fz.id,
            lp=1,
            asortyment_id=item.id,
            ilosc_kg=q3(payload.ilosc_kg),
            cena_netto=q3(payload.cena_netto),
            cena_z_cennika=q3(payload.cena_netto),
            czy_cena_zmieniona_recznie=False,
            stawka_vat=q2(payload.stawka_vat),
            wartosc_netto=netto,
            wartosc_vat=vat,
            wartosc_brutto=brutto,
        )
    )
    record_audit(
        db,
        akcja="REJESTRACJA_FAKTURY_ZAKUPU_FZ",
        zasob="FAKTURA_VAT",
        zasob_id=fz.id,
        zmiana_stanu={"numer": fz.numer, "dostawca": supplier.nazwa, "wartosc_brutto": str(brutto)},
        user=user,
        adres_ip=client_ip_from_request(request),
    )
    db.commit()
    db.refresh(fz)
    return _serialize_invoice(fz)


@router.get("/api/dokumenty/{doc_id}/pdf")
def download_warehouse_doc_pdf(
    doc_id: str,
    request: Request,
    user: Uzytkownik = Depends(require_roles("OP_WAG", "MAG_WG", "INZ_PROD", "KIER_MAG", "FAKT_KS", "ADMIN")),
    db: Session = Depends(get_db),
):
    doc = db.get(DokumentMagazynowy, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono dokumentu magazynowego.")
    if doc.status not in ("ZATWIERDZONY", "ANULOWANY"):
        raise HTTPException(status_code=422, detail="Wydruk PDF jest dostępny wyłącznie dla dokumentów zatwierdzonych.")

    doc.liczba_wydrukow += 1
    pdf_bytes = render_warehouse_doc_pdf(doc, doc.liczba_wydrukow)
    record_audit(
        db,
        akcja="WYDRUK_DOKUMENTU_PDF",
        zasob="DOKUMENT_MAGAZYNOWY",
        zasob_id=doc.id,
        zmiana_stanu={"numer": doc.numer, "typ": doc.typ, "wydruk_nr": doc.liczba_wydrukow},
        user=user,
        adres_ip=client_ip_from_request(request),
    )
    db.commit()
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{doc.numer.replace("/", "_")}.pdf"'},
    )


@router.get("/api/p3/faktury/{inv_id}/pdf")
def download_invoice_pdf(
    inv_id: str,
    request: Request,
    user: Uzytkownik = Depends(require_roles("FAKT_KS", "KIER_MAG", "ADMIN")),
    db: Session = Depends(get_db),
):
    inv = db.get(FakturaVAT, inv_id)
    if inv is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono faktury.")
    if inv.status != "ZATWIERDZONA":
        raise HTTPException(status_code=422, detail="Drukować można wyłącznie zatwierdzone faktury.")

    inv.liczba_wydrukow += 1
    pdf_bytes = render_invoice_pdf(inv, inv.liczba_wydrukow)
    record_audit(
        db,
        akcja="WYDRUK_FAKTURY_PDF",
        zasob="FAKTURA_VAT",
        zasob_id=inv.id,
        zmiana_stanu={"numer": inv.numer, "typ": inv.typ, "wydruk_nr": inv.liczba_wydrukow},
        user=user,
        adres_ip=client_ip_from_request(request),
    )
    db.commit()
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{inv.numer.replace("/", "_")}.pdf"'},
    )
