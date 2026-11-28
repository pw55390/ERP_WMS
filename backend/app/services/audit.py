from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.entities import Uzytkownik, WpisAudytowy


def record_audit(
    db: Session,
    *,
    akcja: str,
    zasob: str,
    zmiana_stanu: dict[str, Any],
    zasob_id: str | None = None,
    user: Uzytkownik | None = None,
    adres_ip: str = "127.0.0.1",
    komentarz: str | None = None,
) -> WpisAudytowy:
    """Append-only zapis zdarzenia audytowego (brak operacji modyfikacji/usuwania)."""
    entry = WpisAudytowy(
        uzytkownik_id=user.id if user else None,
        login=user.login if user else None,
        rola=user.rola if user else None,
        adres_ip=adres_ip,
        akcja=akcja,
        zasob=zasob,
        zasob_id=zasob_id,
        zmiana_stanu=zmiana_stanu,
        komentarz=komentarz,
    )
    db.add(entry)
    return entry


def client_ip_from_request(request: Request | None) -> str:
    if request is None:
        return "internal"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"
