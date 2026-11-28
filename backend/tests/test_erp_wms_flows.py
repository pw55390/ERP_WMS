from __future__ import annotations

import os
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///./test_emagazyn.db"
os.environ["DEMO_MODE"] = "true"

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.db.base import Base  # noqa: E402
from app.db.seed import DEMO_PASSWORD_PLAIN, seed_demo_data  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    if os.path.exists("test_emagazyn.db"):
        os.remove("test_emagazyn.db")
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_demo_data(db)
    with TestClient(app) as c:
        yield c
    engine.dispose()
    if os.path.exists("test_emagazyn.db"):
        os.remove("test_emagazyn.db")


def _auth_header(client: TestClient, login: str) -> dict[str, str]:
    resp = client.post("/api/auth/login", json={"login": login, "password": DEMO_PASSWORD_PLAIN})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_rbac_matrix_enforcement(client: TestClient):
    h_op = _auth_header(client, "op_wag")
    h_mag = _auth_header(client, "mag_wg")
    h_admin = _auth_header(client, "admin")

    # OP_WAG nie ma dostępu do audytu ani zleceń produkcyjnych ani faktur
    assert client.get("/api/admin/audyt", headers=h_op).status_code == 403
    assert client.get("/api/p2/zlecenia", headers=h_op).status_code == 403
    assert client.get("/api/p3/faktury", headers=h_op).status_code == 403

    # MAG_WG nie może wystawiać FS ani otwierać inwentaryzacji
    assert client.post("/api/p3/faktury/z-wz", json={"wz_ids": ["x"]}, headers=h_mag).status_code == 403
    assert client.post("/api/p4/inwentaryzacje", json={"zakres_strefa": "WYROBY_GOTOWE"}, headers=h_mag).status_code == 403

    # ADMIN może czytać dziennik audytu
    r_audit = client.get("/api/admin/audyt", headers=h_admin)
    assert r_audit.status_code == 200
    assert len(r_audit.json()) >= 1


def test_p1_intake_quality_escalation_scale_failure_and_pz_pdf(client: TestClient):
    h_op = _auth_header(client, "op_wag")
    h_kier = _auth_header(client, "kier_mag")

    # Symulator GUS
    gus = client.get("/api/kontrahenci/gus/5250001122", headers=h_op)
    assert gus.status_code == 200
    assert gus.json()["tryb"] == "SYMULACJA"

    suppliers = client.get("/api/kontrahenci?typ=DOSTAWCA", headers=h_op).json()
    items = client.get("/api/asortyment?kategoria=SUROWIEC", headers=h_op).json()
    silos = client.get("/api/lokalizacje?typ=SILOS", headers=h_op).json()
    sup_id = suppliers[0]["id"]
    wheat_id = items[0]["id"]
    silo_id = silos[0]["id"]

    # 1. Próba ręcznego wpisu wagi bez kodu kierownika -> 403
    bad_manual = client.post(
        "/api/p1/przyjecia",
        headers=h_op,
        json={
            "dostawca_id": sup_id,
            "asortyment_id": wheat_id,
            "silos_docelowy_id": silo_id,
            "nr_rejestracyjny": "DW 9999X",
            "tryb_reczny": True,
            "kod_autoryzacji": "BLEDNY-KOD",
            "masa_brutto_kg": "40000.000",
        },
    )
    assert bad_manual.status_code == 403

    # 2. Poprawne ręczne przyjęcie z kodem KIER-AWARIA-2026
    good_manual = client.post(
        "/api/p1/przyjecia",
        headers=h_op,
        json={
            "dostawca_id": sup_id,
            "asortyment_id": wheat_id,
            "silos_docelowy_id": silo_id,
            "nr_rejestracyjny": "DW 7711A",
            "tryb_reczny": True,
            "kod_autoryzacji": "KIER-AWARIA-2026",
            "masa_brutto_kg": "40000.000",
        },
    )
    assert good_manual.status_code == 201, good_manual.text
    skup = good_manual.json()
    assert skup["flaga_awarii_wagi"] is True

    # 3. Wilgotność 16.2% > progu 15% -> blokada do decyzji kierownika
    q_resp = client.post(
        f"/api/p1/przyjecia/{skup['id']}/jakosc",
        headers=h_op,
        json={"wilgotnosc_pct": "16.2", "zanieczyszczenia_pct": "1.5"},
    )
    assert q_resp.status_code == 200
    assert q_resp.json()["przyjecie"]["status"] == "OCZEKUJE_KIEROWNIKA"

    # OP_WAG nie może zatwierdzić PZ przed decyzją kierownika
    blocked_pz = client.post(
        f"/api/p1/przyjecia/{skup['id']}/tara-i-pz",
        headers=h_op,
        json={"masa_tara_kg": "15000.000"},
    )
    assert blocked_pz.status_code == 409

    # OP_WAG nie może sam podjąć decyzji kierownika
    assert (
        client.post(
            f"/api/p1/przyjecia/{skup['id']}/decyzja-kierownika",
            headers=h_op,
            json={"zatwierdz": True, "komentarz": "Próba obejścia"},
        ).status_code
        == 403
    )

    # KIER_MAG wyraża zgodę warunkową
    dec = client.post(
        f"/api/p1/przyjecia/{skup['id']}/decyzja-kierownika",
        headers=h_kier,
        json={"zatwierdz": True, "komentarz": "Warunkowe przyjęcie do szybkiego przemiału"},
    )
    assert dec.status_code == 200
    assert dec.json()["status"] == "W_TOKU"

    # Błędna tara (>= brutto) -> 422
    bad_tare = client.post(
        f"/api/p1/przyjecia/{skup['id']}/tara-i-pz",
        headers=h_op,
        json={"masa_tara_kg": "41000.000"},
    )
    assert bad_tare.status_code == 422

    # Poprawna tara i wystawienie PZ
    pz_resp = client.post(
        f"/api/p1/przyjecia/{skup['id']}/tara-i-pz",
        headers=h_op,
        json={"masa_tara_kg": "15000.000"},
    )
    assert pz_resp.status_code == 200, pz_resp.text
    pz_data = pz_resp.json()
    assert pz_data["status"] == "ZATWIERDZONE"
    assert Decimal(pz_data["masa_netto_kg"]) == Decimal("25000.000")
    assert pz_data["dokument_pz_numer"].startswith("PZ/")

    # PDF dokumentu PZ
    pdf = client.get(f"/api/dokumenty/{pz_data['dokument_pz_id']}/pdf", headers=h_op)
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")

    # Raport kontrolny zawiera przyjęcie z awarią wagi i przekroczoną wilgotnością
    ctrl = client.get("/api/p1/raport-kontrolny", headers=h_kier)
    assert ctrl.status_code == 200
    assert any(r["id"] == skup["id"] for r in ctrl.json())


def test_p2_production_bom_rw_balance_loss_and_pw(client: TestClient):
    h_prod = _auth_header(client, "inz_prod")
    h_kier = _auth_header(client, "kier_mag")

    boms = client.get("/api/p2/receptury", headers=h_prod).json()
    bom_id = boms[0]["id"]

    stock = client.get("/api/p4/stany?strefa=SUROWCE&tylko_dostepne=true", headers=h_prod).json()["partie"]
    wheat_lot = stock[0]

    locs_wg = client.get("/api/lokalizacje?strefa=WYROBY_GOTOWE", headers=h_prod).json()
    reg1_id = locs_wg[0]["id"]
    items_bp = client.get("/api/asortyment?kategoria=PRODUKT_UBOCZNY", headers=h_prod).json()
    bran_id = items_bp[0]["id"]

    # Tworzenie zlecenia na 10 000 kg -> auto RW
    order_resp = client.post(
        "/api/p2/zlecenia",
        headers=h_prod,
        json={
            "receptura_id": bom_id,
            "linia_przemialowa": "Linia Młynarska L1",
            "planowany_zasyp_kg": "10000.000",
            "partia_surowca_id": wheat_lot["id"],
        },
    )
    assert order_resp.status_code == 201, order_resp.text
    order = order_resp.json()
    assert order["status"] == "W_REALIZACJI"
    assert Decimal(order["ilosc_rw_kg"]) == Decimal("10000.000")

    exp_date = (date.today() + timedelta(days=180)).isoformat()

    # Nieuzgodniony bilans (>0.5% różnicy) -> twarda blokada 422
    unbalanced = client.post(
        f"/api/p2/zlecenia/{order['id']}/rozlicz-pw",
        headers=h_prod,
        json={
            "wyrob_glowny_kg": "7000.000",
            "lokalizacja_docelowa_id": reg1_id,
            "data_waznosci_wyrobu": exp_date,
            "produkty_uboczne": [{"asortyment_id": bran_id, "lokalizacja_id": reg1_id, "ilosc_kg": "2000.000"}],
            "strata_odsiew_kg": "100.000",
            "strata_wilgotnosc_kg": "50.000",
        },
    )
    assert unbalanced.status_code == 422

    # Zbilansowane, ale strata 400 kg (4.0% > 3.0%) -> wstrzymane do akceptacji KIER_MAG
    high_loss = client.post(
        f"/api/p2/zlecenia/{order['id']}/rozlicz-pw",
        headers=h_prod,
        json={
            "wyrob_glowny_kg": "7300.000",
            "lokalizacja_docelowa_id": reg1_id,
            "data_waznosci_wyrobu": exp_date,
            "produkty_uboczne": [{"asortyment_id": bran_id, "lokalizacja_id": reg1_id, "ilosc_kg": "2300.000"}],
            "strata_odsiew_kg": "250.000",
            "strata_wilgotnosc_kg": "150.000",
            "powod_straty": "Podwyższona wilgotność ziarna z przyjęcia warunkowego",
        },
    )
    assert high_loss.status_code == 200, high_loss.text
    assert high_loss.json()["status"] == "WSTRZYMANE_DO_AKCEPTACJI"

    # Akceptacja straty przez KIER_MAG -> zatwierdza PW i kończy zlecenie
    accept = client.post(
        f"/api/p2/zlecenia/{order['id']}/akceptuj-strate",
        headers=h_kier,
        json={"akceptuj": True, "komentarz": "Akceptuję uzasadnioną stratę wilgotnościową"},
    )
    assert accept.status_code == 200, accept.text
    assert accept.json()["status"] == "ZAKONCZONE"

    # Raport wydajności
    rep = client.get("/api/p2/raport-wydajnosci", headers=h_prod)
    assert rep.status_code == 200
    assert len(rep.json()) >= 1


def test_p3_fefo_expiry_block_wz_fs_and_pdf(client: TestClient):
    h_mag = _auth_header(client, "mag_wg")
    h_kier = _auth_header(client, "kier_mag")
    h_fakt = _auth_header(client, "fakt_ks")

    orders = client.get("/api/p3/zamowienia", headers=h_mag).json()
    order = orders[0]
    item_id = order["pozycje"][0]["asortyment_id"]

    fefo = client.get(f"/api/p3/zamowienia/{order['id']}/podpowiedz-fefo", headers=h_mag).json()
    pos_fefo = fefo["pozycje"][0]
    assert len(pos_fefo["dostepne_fefo"]) >= 1
    assert any(b["kod_partii"] == "LOT-WG-2026-EXP1" for b in pos_fefo["zablokowane_partie"])

    expired_lot = next(b for b in pos_fefo["zablokowane_partie"] if b["kod_partii"] == "LOT-WG-2026-EXP1")
    valid_lot = pos_fefo["dostepne_fefo"][0]

    # Twarda blokada wydania partii przeterminowanej nawet dla KIER_MAG!
    for hdr in (h_mag, h_kier):
        blocked = client.post(
            "/api/p3/wz/kompletuj-i-zatwierdz",
            headers=hdr,
            json={
                "zamowienie_id": order["id"],
                "data_wydania": order["data_wydania"],
                "pozycje": [
                    {
                        "asortyment_id": item_id,
                        "partia_id": expired_lot["partia_id"],
                        "ilosc_kg": "100.000",
                    }
                ],
            },
        )
        assert blocked.status_code == 422

    # Poprawna kompletacja wg FEFO
    wz_resp = client.post(
        "/api/p3/wz/kompletuj-i-zatwierdz",
        headers=h_mag,
        json={
            "zamowienie_id": order["id"],
            "data_wydania": order["data_wydania"],
            "nr_rejestracyjny": "DW 3210M",
            "pozycje": [
                {
                    "asortyment_id": item_id,
                    "partia_id": valid_lot["partia_id"],
                    "ilosc_kg": "1500.000",
                }
            ],
        },
    )
    assert wz_resp.status_code == 201, wz_resp.text
    wz = wz_resp.json()
    assert wz["status"] == "ZATWIERDZONY"

    # Wystawienie FS z WZ z ręczną zmianą ceny przez FAKT_KS (wymaga powodu -> audyt)
    fs_resp = client.post(
        "/api/p3/faktury/z-wz",
        headers=h_fakt,
        json={
            "wz_ids": [wz["id"]],
            "nadpisania_cen": [
                {
                    "asortyment_id": item_id,
                    "nowa_cena_netto": "2.200",
                    "powod_zmiany": "Rabat kontraktowy za odbiór własny",
                }
            ],
        },
    )
    assert fs_resp.status_code == 201, fs_resp.text
    fs = fs_resp.json()
    assert fs["numer"].startswith("FS/")
    assert Decimal(fs["wartosc_netto"]) == Decimal("3300.00")

    pdf1 = client.get(f"/api/p3/faktury/{fs['id']}/pdf", headers=h_fakt)
    assert pdf1.status_code == 200
    assert pdf1.content.startswith(b"%PDF")


def test_p4_mm_inventory_lock_reconcile_and_traceability(client: TestClient):
    h_kier = _auth_header(client, "kier_mag")
    h_mag = _auth_header(client, "mag_wg")

    # Traceability dowolnej partii WG
    wg_lots = client.get("/api/p4/stany?strefa=WYROBY_GOTOWE&tylko_dostepne=true", headers=h_kier).json()["partie"]
    lot_to_move = next(l for l in wg_lots if l["kod_partii"] == "LOT-WG-2026-0001")
    trace = client.get(f"/api/p4/partia/{lot_to_move['id']}/traceability", headers=h_kier)
    assert trace.status_code == 200
    assert trace.json()["pochodzenie_surowca"]["partia_zrodlowa_kod"] == "LOT-SUR-2026-0001"

    locs = client.get("/api/lokalizacje?strefa=WYROBY_GOTOWE", headers=h_kier).json()
    target_loc = next(l for l in locs if l["id"] != lot_to_move["lokalizacja_id"])

    # Przesunięcie MM
    mm = client.post(
        "/api/p4/mm",
        headers=h_kier,
        json={"partia_id": lot_to_move["id"], "lokalizacja_docelowa_id": target_loc["id"], "ilosc_kg": "200.000"},
    )
    assert mm.status_code == 201, mm.text

    # Inwentaryzacja z blokadą strefy WYROBY_GOTOWE
    inw = client.post(
        "/api/p4/inwentaryzacje",
        headers=h_kier,
        json={"zakres_strefa": "WYROBY_GOTOWE", "komentarz": "Spis miesięczny"},
    )
    assert inw.status_code == 201, inw.text
    sheet = inw.json()

    # W trakcie blokady MM w tej strefie musi być zablokowane (409)
    blocked_mm = client.post(
        "/api/p4/mm",
        headers=h_kier,
        json={"partia_id": lot_to_move["id"], "lokalizacja_docelowa_id": target_loc["id"], "ilosc_kg": "50.000"},
    )
    assert blocked_mm.status_code == 409

    # MAG_WG wprowadza spis (np. 10 kg niedoboru na pierwszej pozycji)
    counts = []
    for idx, pos in enumerate(sheet["pozycje"]):
        ew = Decimal(pos["stan_ewidencyjny_kg"])
        spis = ew - Decimal("10.000") if idx == 0 and ew >= Decimal("10.000") else ew
        counts.append(
            {
                "pozycja_id": pos["id"],
                "stan_spisany_kg": str(spis),
                "podstawa_pomiaru": "SKAN_PALET",
                "uzasadnienie": "Uszkodzony worek 10 kg" if idx == 0 else None,
            }
        )
    spis_resp = client.post(f"/api/p4/inwentaryzacje/{sheet['id']}/spis", headers=h_mag, json={"pozycje": counts})
    assert spis_resp.status_code == 200

    # KIER_MAG rozlicza różnice (RW-kor) i zwalnia blokadę
    rec = client.post(
        f"/api/p4/inwentaryzacje/{sheet['id']}/rozlicz",
        headers=h_kier,
        json={"komentarz": "Zatwierdzono spis po przeliczeniu"},
    )
    assert rec.status_code == 200, rec.text
    assert rec.json()["arkusz"]["status"] == "ROZLICZONA"
    assert len(rec.json()["dokumenty_korygujace"]) >= 1

    # Raport rotacji (KIER_MAG)
    rot = client.get("/api/p4/raport-rotacji", headers=h_kier)
    assert rot.status_code == 200
    assert len(rot.json()["pozycje"]) >= 4
