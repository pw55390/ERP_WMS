from __future__ import annotations

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.db.seed import DEMO_PASSWORD_PLAIN, DEMO_USERS
from app.db.session import get_db
from app.models.entities import KonfiguracjaSystemowa, Uzytkownik
from app.schemas.dto import LoginRequest, RefreshRequest, TokenResponse, UserOut
from app.services.audit import client_ip_from_request, record_audit

router = APIRouter(tags=["Autoryzacja i System"])


@router.post("/api/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    ip = client_ip_from_request(request)
    user = db.scalar(select(Uzytkownik).where(Uzytkownik.login == payload.login.strip()))
    if user is None or not verify_password(payload.password, user.haslo_hash):
        record_audit(
            db,
            akcja="LOGOWANIE_NIEUDANE",
            zasob="AUTH",
            zmiana_stanu={"login": payload.login.strip()},
            user=user,
            adres_ip=ip,
            komentarz="Niepoprawny login lub hasło",
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Niepoprawny login lub hasło.",
        )

    if not user.czy_aktywny:
        record_audit(
            db,
            akcja="LOGOWANIE_ZABLOKOWANE",
            zasob="AUTH",
            zasob_id=user.id,
            zmiana_stanu={"login": user.login},
            user=user,
            adres_ip=ip,
            komentarz="Konto jest zablokowane",
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Konto użytkownika zostało zablokowane przez administratora.",
        )

    access = create_access_token(user.id, user.rola, user.login)
    refresh = create_refresh_token(user.id, user.rola, user.login)

    record_audit(
        db,
        akcja="LOGOWANIE_SUKCES",
        zasob="AUTH",
        zasob_id=user.id,
        zmiana_stanu={"login": user.login, "rola": user.rola},
        user=user,
        adres_ip=ip,
    )
    db.commit()

    return TokenResponse(access_token=access, refresh_token=refresh, user=UserOut.model_validate(user))


@router.post("/api/auth/refresh", response_model=TokenResponse)
def refresh_token(payload: RefreshRequest, db: Session = Depends(get_db)):
    try:
        decoded = decode_token(payload.refresh_token)
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nieprawidłowy lub wygasły refresh token.")

    if decoded.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nieprawidłowy typ tokenu.")

    user = db.get(Uzytkownik, decoded.get("sub"))
    if user is None or not user.czy_aktywny:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Konto użytkownika nieaktywne.")

    access = create_access_token(user.id, user.rola, user.login)
    new_refresh = create_refresh_token(user.id, user.rola, user.login)
    return TokenResponse(access_token=access, refresh_token=new_refresh, user=UserOut.model_validate(user))


@router.get("/api/auth/me", response_model=UserOut)
def me(user: Uzytkownik = Depends(get_current_user)):
    return user


@router.get("/api/auth/demo-accounts")
def demo_accounts():
    settings = get_settings()
    if not settings.DEMO_MODE:
        raise HTTPException(status_code=404, detail="Tryb demonstracyjny jest wyłączony.")
    return {
        "tryb_demo": True,
        "ostrzezenie": "Konta wyłącznie do lokalnej prezentacji prototypu MVP. Nie używać w środowisku produkcyjnym.",
        "haslo_demo": DEMO_PASSWORD_PLAIN,
        "kod_awarii_wagi_demo": "KIER-AWARIA-2026",
        "konta": [
            {"login": login, "nazwa": name, "rola": role, "wymaga_2fa_docelowo": req_2fa}
            for login, name, role, req_2fa in DEMO_USERS
        ],
    }


@router.get("/api/system/status")
def system_status(db: Session = Depends(get_db)):
    settings = get_settings()
    cfgs = {c.klucz: c.wartosc for c in db.scalars(select(KonfiguracjaSystemowa)).all()}
    return {
        "aplikacja": settings.APP_NAME,
        "wersja": "0.1.0-mvp",
        "tryb_demo": settings.DEMO_MODE,
        "baza_danych": "PostgreSQL" if settings.is_postgres else "SQLite (lokalny tryb demo)",
        "integracje": {
            "waga_najazdowa": "SYMULACJA" if settings.SCALE_SIMULATOR_ENABLED else "WYLACZONA",
            "api_gus": "SYMULACJA" if settings.GUS_SIMULATOR_ENABLED else "WYLACZONA",
        },
        "reguly_konfigurowalne": {
            "prog_wilgotnosci_pct": cfgs.get("prog_wilgotnosci_pct", "15.000"),
            "prog_zanieczyszczen_pct": cfgs.get("prog_zanieczyszczen_pct", "4.000"),
            "tolerancja_bilansu_pct": cfgs.get("tolerancja_bilansu_pct", "0.500"),
            "prog_straty_procesowej_pct": cfgs.get("prog_straty_procesowej_pct", "3.000"),
            "uwaga_prog_wilgotnosci": (
                "Wartość domyślna 15% (README i RF-01.2); materiały UML/Lista 2 zawierają również próg 16,5% — "
                "wymaga zatwierdzenia właściciela procesu i może zostać zmieniona przez ADMIN w konfiguracji."
            ),
        },
        "ograniczenia_prototypu": [
            "Brak aktywnego 2FA w lokalnym trybie demonstracyjnym (oznaczone jako wymaganie docelowe dla KIER_MAG, FAKT_KS, ADMIN).",
            "Dziennik audytu jest append-only na poziomie aplikacji (w produkcji wymagane wycofanie UPDATE/DELETE na poziomie PostgreSQL).",
            "Brak skonfigurowanego tunelu VPN, TLS 1.3, kopii WAL co 15 min oraz testów wydajnościowych dla 100 równoczesnych użytkowników.",
        ],
    }
