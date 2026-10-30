"""Distance-based estimates for petroleum diesel combustion CO2 only."""

from math import isfinite
from numbers import Real

from marine_routes import KM_PER_NAUTICAL_MILE


EPA_SOURCE_URL = "https://www.epa.gov/system/files/documents/2025-01/ghg-emission-factors-hub-2025.pdf"
EPA_SOURCE_DATE = "15 Ocak 2025"
NIST_SOURCE_URL = "https://www.nist.gov/document/2025-nist-handbook-130-vi"
DIESEL_KG_CO2_PER_US_GALLON = 10.21
LITERS_PER_US_GALLON = 3.785411784
# Preserve the full quotient; the UI alone rounds the displayed value.
DIESEL_KG_CO2_PER_LITER = DIESEL_KG_CO2_PER_US_GALLON / LITERS_PER_US_GALLON


def _validated(value, name: str, *, allow_zero: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not isfinite(value):
        raise ValueError(f"{name} sonlu bir sayı olmalıdır.")
    if value < 0 or (value == 0 and not allow_zero):
        requirement = "sıfır veya pozitif" if allow_zero else "sıfırdan büyük"
        raise ValueError(f"{name} {requirement} olmalıdır.")
    return float(value)


def compare_fuel_co2(
    current_km: float,
    recommended_km: float,
    liters_per_nautical_mile: float,
    kg_co2_per_liter: float = DIESEL_KG_CO2_PER_LITER,
) -> dict:
    """Use unrounded distances and the same constant consumption for both routes."""
    distances = (
        _validated(current_km, "Mevcut rota mesafesi", allow_zero=True),
        _validated(recommended_km, "Önerilen rota mesafesi", allow_zero=True),
    )
    consumption = _validated(liters_per_nautical_mile, "Tekne tüketimi")
    factor = _validated(kg_co2_per_liter, "CO₂ emisyon katsayısı")
    result = {}
    for prefix, distance in zip(("current", "recommended"), distances):
        nautical_miles = distance / KM_PER_NAUTICAL_MILE
        fuel_l = nautical_miles * consumption
        co2_kg = fuel_l * factor
        if not all(isfinite(x) for x in (nautical_miles, fuel_l, co2_kg)):
            raise ValueError("Hesaplanan sonuç sayısal sınırları aşıyor; girdileri küçültün.")
        result[prefix] = dict(distance_nm=nautical_miles, fuel_l=fuel_l, co2_kg=co2_kg)
    result["difference"] = {
        key: result["current"][key] - result["recommended"][key]
        for key in ("fuel_l", "co2_kg")
    }
    return result
