"""
RouteCare AI - Geocoding service.

Patient/therapist CRUD never calls an external geocoding provider or the
cache directly - everything goes through `geocode_address()` below,
which is the single seam Phase 2 already promised ("implement
GeocodingProvider and change get_geocoding_provider()'s return value.
Nothing in app.services.patient_service needs to change" - see git
history). Phase 5 keeps that promise: `get_geocoding_provider()` now
returns a real `NominatimGeocodingProvider` per
docs/03_System_Architecture.md section 9, and `geocode_address()` adds
a caching layer in front of it, but callers are unaffected either way.

Nominatim's usage policy (https://operations.osmfoundation.org/policies/nominatim/)
requires a real identifying User-Agent and caps the public demo server
at roughly one request per second - `_RateLimiter` enforces the second
part regardless of which server is configured; NOMINATIM_USER_AGENT
(app.core.config) covers the first.
"""

import hashlib
import threading
import time
import uuid
from functools import lru_cache
from typing import Any, Protocol

import httpx

from app.core.cache import cache_get_json, cache_set_json, make_cache_key
from app.core.config import settings


@lru_cache
def _get_http_client() -> httpx.Client:
    """Pooled, keep-alive httpx.Client reused across every Nominatim call in this process - see
    app.services.routing._get_http_client's docstring for the full rationale (identical here)."""
    return httpx.Client(timeout=settings.GEOCODING_TIMEOUT_SECONDS)


class GeocodeResult:
    def __init__(self, latitude: float, longitude: float, normalized_address: str | None = None) -> None:
        self.latitude = latitude
        self.longitude = longitude
        self.normalized_address = normalized_address

    def to_dict(self) -> dict[str, Any]:
        return {"latitude": self.latitude, "longitude": self.longitude, "normalized_address": self.normalized_address}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GeocodeResult":
        return cls(
            latitude=data["latitude"], longitude=data["longitude"], normalized_address=data.get("normalized_address")
        )


class GeocodingProvider(Protocol):
    def geocode(self, *, address_line_1: str, city: str, state: str, zip_code: str) -> GeocodeResult | None:
        """Resolve an address to coordinates, or None if it can't be resolved (invalid/incomplete
        address, provider error, rate limit, or timeout - callers can't and don't need to tell
        these apart; all of them just mean "no reliable coordinates right now, try again later")."""
        ...


class NullGeocodingProvider:
    """No-op provider - used in tests and as a safe fallback; never makes a network call."""

    def geocode(self, *, address_line_1: str, city: str, state: str, zip_code: str) -> GeocodeResult | None:
        return None


class _RateLimiter:
    """Enforces a minimum gap between calls across threads - Nominatim's public server rejects
    (or silently degrades) bursts faster than ~1/second."""

    def __init__(self, min_interval_seconds: float) -> None:
        self._min_interval = min_interval_seconds
        self._lock = threading.Lock()
        self._last_call = 0.0

    def wait(self) -> None:
        with self._lock:
            elapsed = time.monotonic() - self._last_call
            remaining = self._min_interval - elapsed
            if remaining > 0:
                time.sleep(remaining)
            self._last_call = time.monotonic()


_nominatim_rate_limiter = _RateLimiter(settings.NOMINATIM_MIN_REQUEST_INTERVAL_SECONDS)


class NominatimGeocodingProvider:
    """Real geocoding via Nominatim (OpenStreetMap), per docs/03_System_Architecture.md section 9.

    Any failure mode - invalid/incomplete address (no results), network error, timeout, non-200
    response, unparseable body - is swallowed and reported as `None`, never raised. Geocoding must
    never block or fail patient/therapist creation; a `None` result just leaves the record in
    `FAILED`/`PENDING` status, retryable later via the explicit re-geocode endpoint.
    """

    def geocode(self, *, address_line_1: str, city: str, state: str, zip_code: str) -> GeocodeResult | None:
        query = ", ".join(part for part in (address_line_1, city, state, zip_code) if part.strip())
        if not query.strip():
            return None

        _nominatim_rate_limiter.wait()
        try:
            response = _get_http_client().get(
                f"{settings.NOMINATIM_BASE_URL}/search",
                params={"q": query, "format": "jsonv2", "addressdetails": 0, "limit": 1},
                headers={"User-Agent": settings.NOMINATIM_USER_AGENT},
            )
            response.raise_for_status()
            results = response.json()
        except (httpx.HTTPError, ValueError):
            return None

        if not results:
            return None

        try:
            first = results[0]
            return GeocodeResult(
                latitude=float(first["lat"]),
                longitude=float(first["lon"]),
                normalized_address=first.get("display_name"),
            )
        except (KeyError, TypeError, ValueError):
            return None


def get_geocoding_provider() -> GeocodingProvider:
    return NominatimGeocodingProvider()


def _address_cache_key(clinic_id: uuid.UUID, address_line_1: str, city: str, state: str, zip_code: str) -> str:
    # Cache keys are scoped per clinic even though a geocoded address's coordinates aren't
    # inherently clinic-specific data - deliberately conservative, per the explicit instruction
    # not to let caching create any cross-tenant data path, at the modest cost of not sharing a
    # cache hit between two clinics that happen to have a client at the same address.
    normalized = "|".join(part.strip().lower() for part in (address_line_1, city, state, zip_code))
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return make_cache_key(str(clinic_id), "geocode", digest)


def geocode_address(
    *, clinic_id: uuid.UUID, address_line_1: str, city: str, state: str, zip_code: str
) -> GeocodeResult | None:
    """Cached facade in front of the configured provider - the only entry point
    app.services.patient_service/therapist_service should call."""
    key = _address_cache_key(clinic_id, address_line_1, city, state, zip_code)
    cached = cache_get_json(key)
    if cached is not None:
        return GeocodeResult.from_dict(cached["result"]) if cached.get("found") else None

    result = get_geocoding_provider().geocode(address_line_1=address_line_1, city=city, state=state, zip_code=zip_code)
    cache_set_json(
        key,
        {"found": result is not None, "result": result.to_dict() if result else None},
        ttl_seconds=settings.GEOCODE_CACHE_TTL_SECONDS,
    )
    return result
