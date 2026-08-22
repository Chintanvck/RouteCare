"""
RouteCare AI - Geocoding service boundary.

Patient CRUD never calls an external geocoding provider directly - it
depends on this abstraction instead (same "define the seam before you
need the implementation" pattern as app.core.rate_limiting). Latitude/
longitude are stored only when the caller already supplies them; no
external geocoding call happens in Phase 2.

To wire in a real provider later (Nominatim per docs/03_System_Architecture.md
section 9, added in Phase 5 alongside the map/route work): implement
GeocodingProvider and change get_geocoding_provider()'s return value.
Nothing in app.services.patient_service needs to change.
"""

from typing import Protocol


class GeocodeResult:
    def __init__(self, latitude: float, longitude: float) -> None:
        self.latitude = latitude
        self.longitude = longitude


class GeocodingProvider(Protocol):
    def geocode(self, *, address_line_1: str, city: str, state: str, zip_code: str) -> GeocodeResult | None:
        """Resolve an address to coordinates, or None if it can't be resolved."""
        ...


class NullGeocodingProvider:
    """No-op provider - Phase 2 has no external geocoding integration yet."""

    def geocode(self, *, address_line_1: str, city: str, state: str, zip_code: str) -> GeocodeResult | None:
        return None


def get_geocoding_provider() -> GeocodingProvider:
    return NullGeocodingProvider()
