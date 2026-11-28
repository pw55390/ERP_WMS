from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import (
    DokumentMagazynowy,
    FakturaVAT,
    KonfiguracjaSystemowa,
    LokalizacjaMagazynowa,
    PartiaMagazynowa,
)

D_ZERO = Decimal("0.000")
Q3 = Decimal("0.001")
Q2 = Decimal("0.01")


def q3(val: Decimal | str | int | float) -> Decimal:
    return Decimal(str(val)).quantize(Q3, rounding=ROUND_HALF_UP)


def q2(val: Decimal | str | int | float) -> Decimal:
    return Decimal(str(val)).quantize(Q2, rounding=ROUND_HALF_UP)


def get_config_decimal(db: Session, klucz: str, default: Decimal) -> Decimal:
    cfg = db.get(KonfiguracjaSystemowa, klucz)
    if cfg is None:
        return default
    return Decimal(cfg.wartosc)


def get_location_occupied_kg(db: Session, lokalizacja_id: str) -> Decimal:
    total = db.scalar(
        select(func.coalesce(func.sum(PartiaMagazynowa.masa_dostepna_kg), 0)).where(
            PartiaMagazynowa.lokalizacja_id == lokalizacja_id,
            PartiaMagazynowa.status.in_(["DOSTEPNA", "WSTRZYMANA", "ZABLOKOWANA"]),
        )
    )
    return q3(total or 0)


def lock_batch_for_update(db: Session, batch_id: str) -> PartiaMagazynowa | None:
    stmt = select(PartiaMagazynowa).where(PartiaMagazynowa.id == batch_id)
    if db.bind and db.bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update()
    return db.scalar(stmt)


def lock_location_for_update(db: Session, location_id: str) -> LokalizacjaMagazynowa | None:
    stmt = select(LokalizacjaMagazynowa).where(LokalizacjaMagazynowa.id == location_id)
    if db.bind and db.bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update()
    return db.scalar(stmt)


def next_document_number(db: Session, prefix: str, model_cls=DokumentMagazynowy) -> str:
    year = datetime.now(timezone.utc).year
    pattern = f"{prefix}/{year}/%"
    if model_cls is DokumentMagazynowy:
        existing = db.scalars(
            select(DokumentMagazynowy.numer).where(DokumentMagazynowy.numer.like(pattern))
        ).all()
    elif model_cls is FakturaVAT:
        existing = db.scalars(
            select(FakturaVAT.numer).where(FakturaVAT.numer.like(pattern))
        ).all()
    else:
        existing = db.scalars(
            select(model_cls.numer).where(model_cls.numer.like(pattern))
        ).all()
    max_seq = 0
    for num in existing:
        try:
            seq = int(num.rsplit("/", 1)[-1])
            if seq > max_seq:
                max_seq = seq
        except ValueError:
            continue
    return f"{prefix}/{year}/{max_seq + 1:04d}"


def next_batch_code(db: Session, prefix: str) -> str:
    year = datetime.now(timezone.utc).year
    pattern = f"{prefix}-{year}-%"
    existing = db.scalars(
        select(PartiaMagazynowa.kod_partii).where(PartiaMagazynowa.kod_partii.like(pattern))
    ).all()
    max_seq = 0
    for code in existing:
        try:
            seq = int(code.rsplit("-", 1)[-1])
            if seq > max_seq:
                max_seq = seq
        except ValueError:
            continue
    return f"{prefix}-{year}-{max_seq + 1:04d}"
