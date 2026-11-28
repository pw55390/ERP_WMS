from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db.session import get_db
from app.models.entities import Uzytkownik
from app.services.audit import client_ip_from_request, record_audit

bearer_scheme = HTTPBearer(auto_error=False)

VALID_ROLES = {"OP_WAG", "MAG_WG", "INZ_PROD", "KIER_MAG", "FAKT_KS", "ADMIN"}


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Uzytkownik:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Brak tokenu uwierzytelniającego. Zaloguj się ponownie.",
        )
    try:
        payload = decode_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesja wygasła. Odśwież token lub zaloguj się ponownie.",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nieprawidłowy token dostępu.",
        )

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nieprawidłowy typ tokenu.",
        )

    user = db.get(Uzytkownik, payload.get("sub"))
    if user is None or not user.czy_aktywny:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Konto użytkownika jest nieaktywne lub nie istnieje.",
        )
    return user


def require_roles(*allowed_roles: str):
    allowed = set(allowed_roles)

    def _guard(
        request: Request,
        user: Uzytkownik = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> Uzytkownik:
        if user.rola not in allowed:
            record_audit(
                db,
                akcja="ODMOWA_DOSTEPU_RBAC",
                zasob=request.url.path,
                zmiana_stanu={
                    "wymagane_role": sorted(allowed),
                    "posiadana_rola": user.rola,
                    "metoda": request.method,
                },
                user=user,
                adres_ip=client_ip_from_request(request),
                komentarz="Próba wykonania operacji bez wymaganych uprawnień RBAC",
            )
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Brak uprawnień dla roli {user.rola}. Wymagana jedna z ról: {', '.join(sorted(allowed))}.",
            )
        return user

    return _guard
