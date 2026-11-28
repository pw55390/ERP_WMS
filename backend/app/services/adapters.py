from __future__ import annotations

import random
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from app.core.config import get_settings


@dataclass(frozen=True)
class ScaleReading:
    masa_kg: Decimal
    protokol: str
    tryb: str
    status_urzadzenia: str
    komunikat: str


@dataclass(frozen=True)
class GusContractorResult:
    znaleziono: bool
    nip: str
    nazwa: str | None
    adres: str | None
    tryb: str
    komunikat: str


class AdapterWagi:
    """Adapter wagi najazdowej (w środowisku MVP działa w jawnym trybie symulacji)."""

    def __init__(self, protokol: str = "TCP/IP (Modbus-Sim)"):
        self.protokol = protokol

    def odczytaj_brutto(self, symuluj_awarie: bool = False) -> ScaleReading:
        settings = get_settings()
        if symuluj_awarie or not settings.SCALE_SIMULATOR_ENABLED:
            return ScaleReading(
                masa_kg=Decimal("0.000"),
                protokol=self.protokol,
                tryb="SYMULACJA",
                status_urzadzenia="AWARIA_ODCZYTU",
                komunikat="Brak odpowiedzi z miernika wagi. Wymagane ręczne wprowadzenie z kodem KIER_MAG (UC-01.5).",
            )
        # Typowa masa brutto zestawu ciężarowego ze zbożem: 36 000 – 42 500 kg
        raw = Decimal(str(random.randint(36500, 42500))).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        return ScaleReading(
            masa_kg=raw,
            protokol=self.protokol,
            tryb="SYMULACJA",
            status_urzadzenia="OK",
            komunikat="Odczyt pobrany z symulatora wagi najazdowej (brak fizycznego miernika RS-232/TCP).",
        )

    def odczytaj_tare(self, masa_brutto_kg: Decimal, symuluj_awarie: bool = False) -> ScaleReading:
        settings = get_settings()
        if symuluj_awarie or not settings.SCALE_SIMULATOR_ENABLED:
            return ScaleReading(
                masa_kg=Decimal("0.000"),
                protokol=self.protokol,
                tryb="SYMULACJA",
                status_urzadzenia="AWARIA_ODCZYTU",
                komunikat="Brak odpowiedzi z miernika wagi przy tarowaniu. Wymagany kod KIER_MAG (UC-01.5).",
            )
        # Typowa tara zestawu ciężarowego: 13 800 – 15 600 kg (zawsze < brutto jeśli brutto > 16t)
        max_tara = min(15600, int(masa_brutto_kg) - 1000) if masa_brutto_kg > 15000 else max(1000, int(masa_brutto_kg * Decimal("0.4")))
        min_tara = min(13800, max_tara)
        tara = Decimal(str(random.randint(min_tara, max_tara))).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        return ScaleReading(
            masa_kg=tara,
            protokol=self.protokol,
            tryb="SYMULACJA",
            status_urzadzenia="OK",
            komunikat="Tara odczytana z symulatora wagi najazdowej.",
        )


class AdapterGUS:
    """Adapter API GUS (REGON/BIR1) działający w jawnym trybie symulacji dla danych demonstracyjnych."""

    _DEMO_REGISTRY: dict[str, tuple[str, str]] = {
        "8991002030": ("Gospodarstwo Rolne Polskie Zboża Sp. z o.o. [DEMO-GUS]", "ul. Polna 14, 55-080 Kąty Wrocławskie"),
        "5250001122": ("Agro-Młyn Dolny Śląsk S.A. [DEMO-GUS]", "ul. Młyńska 8, 50-120 Wrocław"),
        "7771234567": ("Piekarnia Tradycyjna Złoty Kłos [DEMO-GUS]", "ul. Piekarzy 3, 59-220 Legnica"),
        "6112233445": ("Spółdzielnia Rolnicza Odra [DEMO-GUS]", "ul. Główna 42, 49-300 Brzeg"),
    }

    def pobierz_po_nip(self, nip: str) -> GusContractorResult:
        clean_nip = "".join(ch for ch in nip if ch.isdigit())
        settings = get_settings()
        if len(clean_nip) != 10:
            return GusContractorResult(
                znaleziono=False,
                nip=clean_nip,
                nazwa=None,
                adres=None,
                tryb="SYMULACJA",
                komunikat="Niepoprawny format NIP (wymagane 10 cyfr).",
            )
        if not settings.GUS_SIMULATOR_ENABLED:
            return GusContractorResult(
                znaleziono=False,
                nip=clean_nip,
                nazwa=None,
                adres=None,
                tryb="SYMULACJA_WYLACZONA",
                komunikat="Połączenie z produkcyjnym API GUS BIR1 nie jest skonfigurowane; uzupełnij dane ręcznie.",
            )
        if clean_nip in self._DEMO_REGISTRY:
            nazwa, adres = self._DEMO_REGISTRY[clean_nip]
            return GusContractorResult(
                znaleziono=True,
                nip=clean_nip,
                nazwa=nazwa,
                adres=adres,
                tryb="SYMULACJA",
                komunikat="Dane pobrane z lokalnego symulatora API GUS (brak połączenia produkcyjnego GUS BIR1).",
            )
        return GusContractorResult(
            znaleziono=False,
            nip=clean_nip,
            nazwa=None,
            adres=None,
            tryb="SYMULACJA",
            komunikat="Symulator API GUS nie zwrócił podmiotu dla tego NIP. Wprowadź nazwę i adres ręcznie (UC-01.4 ścieżka 3a).",
        )
