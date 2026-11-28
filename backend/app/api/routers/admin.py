from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import VALID_ROLES, get_current_user, require_roles
from app.core.security import hash_password
from app.db.session import get_db
from app.models.entities import KodAutoryzacyjny, KonfiguracjaSystemowa, Uzytkownik, WpisAudytowy
from app.schemas.dto import (
    AuditOut,
    AuthCodeCreateRequest,
    ConfigUpdateRequest,
    UserCreateRequest,
    UserOut,
    UserUpdateRequest,
)
from app.services.audit import client_ip_from_request, record_audit

router = APIRouter(prefix="/api/admin", tags=["Administracja i Audyt"])


@router.get("/uzytkownicy", response_model=list[UserOut])
def list_users(
    user: Uzytkownik = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    return db.scalars(select(Uzytkownik).order_by(Uzytkownik.login)).all()


@router.post("/uzytkownicy", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreateRequest,
    request: Request,
    admin: Uzytkownik = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    if payload.rola not in VALID_ROLES:
        raise HTTPException(status_code=422, detail=f"Niedopuszczalna rola: {payload.rola}")
    login = payload.login.strip()
    if db.scalar(select(Uzytkownik).where(Uzytkownik.login == login)):
        raise HTTPException(status_code=409, detail=f"Login '{login}' jest już zajęty.")

    new_user = Uzytkownik(
        login=login,
        imie_nazwisko=payload.imie_nazwisko.strip(),
        haslo_hash=hash_password(payload.password),
        rola=payload.rola,
        czy_aktywny=payload.czy_aktywny,
        czy_2fa_wymagane=payload.rola in {"KIER_MAG", "FAKT_KS", "ADMIN"},
    )
    db.add(new_user)
    db.flush()
    record_audit(
        db,
        akcja="UTWORZENIE_KONTA",
        zasob="UZYTKOWNIK",
        zasob_id=new_user.id,
        zmiana_stanu={"login": new_user.login, "rola": new_user.rola, "czy_aktywny": new_user.czy_aktywny},
        user=admin,
        adres_ip=client_ip_from_request(request),
    )
    db.commit()
    return new_user


@router.patch("/uzytkownicy/{user_id}", response_model=UserOut)
def update_user(
    user_id: str,
    payload: UserUpdateRequest,
    request: Request,
    admin: Uzytkownik = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    target = db.get(Uzytkownik, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono użytkownika.")

    changes: dict[str, object] = {}
    if payload.imie_nazwisko is not None:
        changes["imie_nazwisko"] = {"przed": target.imie_nazwisko, "po": payload.imie_nazwisko.strip()}
        target.imie_nazwisko = payload.imie_nazwisko.strip()
    if payload.rola is not None:
        if payload.rola not in VALID_ROLES:
            raise HTTPException(status_code=422, detail=f"Niedopuszczalna rola: {payload.rola}")
        changes["rola"] = {"przed": target.rola, "po": payload.rola}
        target.rola = payload.rola
        target.czy_2fa_wymagane = payload.rola in {"KIER_MAG", "FAKT_KS", "ADMIN"}
    if payload.czy_aktywny is not None:
        if target.id == admin.id and not payload.czy_aktywny:
            raise HTTPException(status_code=422, detail="Administrator nie może zablokować własnego konta.")
        changes["czy_aktywny"] = {"przed": target.czy_aktywny, "po": payload.czy_aktywny}
        target.czy_aktywny = payload.czy_aktywny
    if payload.password:
        target.haslo_hash = hash_password(payload.password)
        changes["haslo"] = "ZMIENIONE"

    record_audit(
        db,
        akcja="MODYFIKACJA_KONTA",
        zasob="UZYTKOWNIK",
        zasob_id=target.id,
        zmiana_stanu=changes,
        user=admin,
        adres_ip=client_ip_from_request(request),
    )
    db.commit()
    return target


@router.get("/konfiguracja")
def list_config(
    user: Uzytkownik = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = db.scalars(select(KonfiguracjaSystemowa).order_by(KonfiguracjaSystemowa.klucz)).all()
    return [
        {
            "klucz": r.klucz,
            "wartosc": r.wartosc,
            "jednostka": r.jednostka,
            "opis": r.opis,
            "zmodyfikowano_utc": r.zmodyfikowano_utc.isoformat(),
        }
        for r in rows
    ]


@router.patch("/konfiguracja/{klucz}")
def update_config(
    klucz: str,
    payload: ConfigUpdateRequest,
    request: Request,
    admin: Uzytkownik = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    cfg = db.get(KonfiguracjaSystemowa, klucz)
    if cfg is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono parametru konfiguracji.")

    try:
        num = Decimal(payload.wartosc.replace(",", "."))
    except InvalidOperation:
        raise HTTPException(status_code=422, detail="Wartość parametru musi być poprawną liczbą.")
    if num <= 0:
        raise HTTPException(status_code=422, detail="Wartość parametru musi być większa od zera.")

    old_val = cfg.wartosc
    cfg.wartosc = str(num)
    cfg.zmodyfikowano_utc = datetime.now(timezone.utc)
    cfg.zmodyfikowano_przez_id = admin.id

    record_audit(
        db,
        akcja="ZMIANA_KONFIGURACJI",
        zasob="KONFIGURACJA",
        zasob_id=klucz,
        zmiana_stanu={"klucz": klucz, "przed": old_val, "po": cfg.wartosc},
        user=admin,
        adres_ip=client_ip_from_request(request),
    )
    db.commit()
    return {"klucz": cfg.klucz, "wartosc": cfg.wartosc, "opis": cfg.opis}


@router.get("/audyt", response_model=list[AuditOut])
def list_audit_log(
    akcja: str | None = None,
    zasob: str | None = None,
    limit: int = 150,
    admin: Uzytkownik = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    stmt = select(WpisAudytowy).order_by(WpisAudytowy.znacznik_utc.desc())
    if akcja:
        stmt = stmt.where(WpisAudytowy.akcja == akcja)
    if zasob:
        stmt = stmt.where(WpisAudytowy.zasob == zasob)
    return db.scalars(stmt.limit(min(limit, 500))).all()


@router.get("/kody-autoryzacyjne")
def list_auth_codes(
    user: Uzytkownik = Depends(require_roles("KIER_MAG")),
    db: Session = Depends(get_db),
):
    rows = db.scalars(select(KodAutoryzacyjny).order_by(KodAutoryzacyjny.utworzono_utc.desc())).all()
    return [
        {
            "id": r.id,
            "kod": r.kod,
            "cel": r.cel,
            "opis": r.opis,
            "czy_uzyty": r.czy_uzyty,
            "wygasa_utc": r.wygasa_utc.isoformat(),
            "utworzono_utc": r.utworzono_utc.isoformat(),
        }
        for r in rows
    ]


@router.post("/kody-autoryzacyjne", status_code=status.HTTP_201_CREATED)
def create_auth_code(
    payload: AuthCodeCreateRequest,
    request: Request,
    kierownik: Uzytkownik = Depends(require_roles("KIER_MAG")),
    db: Session = Depends(get_db),
):
    code_str = f"KM-{secrets.token_hex(3).upper()}"
    item = KodAutoryzacyjny(
        kod=code_str,
        kierownik_id=kierownik.id,
        cel=payload.cel,
        opis=payload.opis or "Jednorazowy kod autoryzacji wyjątku wagi (UC-01.5)",
        wygasa_utc=datetime.now(timezone.utc) + timedelta(minutes=payload.waznosc_minuty),
    )
    db.add(item)
    db.flush()
    record_audit(
        db,
        akcja="WYGENEROWANIE_KODU_AUTORYZACJI",
        zasob="KOD_AUTORYZACYJNY",
        zasob_id=item.id,
        zmiana_stanu={"kod_prefiks": code_str[:5] + "***", "cel": item.cel},
        user=kierownik,
        adres_ip=client_ip_from_request(request),
    )
    db.commit()
    return {
        "id": item.id,
        "kod": item.kod,
        "cel": item.cel,
        "wygasa_utc": item.wygasa_utc.isoformat(),
    }
