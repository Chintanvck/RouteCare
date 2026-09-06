"""
RouteCare AI - Geocoding service tests.

These exercise app.services.geocoding directly (no real HTTP client, no
DB) by monkeypatching its pooled httpx.Client (see
app.services.geocoding._get_http_client) - never touches the real
Nominatim service.
"""

import httpx
import pytest

from app.services import geocoding


class _FakeClient:
    """Stands in for the module's pooled httpx.Client - `get_fn` is exactly the same fake
    request handler these tests used to hand straight to `httpx.get`."""

    def __init__(self, get_fn):
        self.get = get_fn


class _FakeResponse:
    def __init__(self, json_data, status_code: int = 200) -> None:
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://example.invalid")
            raise httpx.HTTPStatusError(
                "error", request=request, response=httpx.Response(self.status_code, request=request)
            )

    def json(self):
        return self._json_data


def test_nominatim_provider_success(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(url, params=None, headers=None):
        assert "User-Agent" in headers
        return _FakeResponse([{"lat": "40.7128", "lon": "-74.0060", "display_name": "New York, NY, USA"}])

    monkeypatch.setattr(geocoding, "_get_http_client", lambda: _FakeClient(fake_get))

    result = geocoding.NominatimGeocodingProvider().geocode(
        address_line_1="123 Main St", city="Hoboken", state="NJ", zip_code="07030"
    )

    assert result is not None
    assert result.latitude == pytest.approx(40.7128)
    assert result.longitude == pytest.approx(-74.0060)
    assert result.normalized_address == "New York, NY, USA"


def test_nominatim_provider_no_results_is_invalid_address(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(geocoding, "_get_http_client", lambda: _FakeClient(lambda *a, **kw: _FakeResponse([])))

    result = geocoding.NominatimGeocodingProvider().geocode(
        address_line_1="Nonexistent Street 99999", city="Nowhere", state="ZZ", zip_code="00000"
    )

    assert result is None


def test_nominatim_provider_incomplete_address_never_calls_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    monkeypatch.setattr(
        geocoding, "_get_http_client", lambda: _FakeClient(lambda *a, **kw: calls.append(1) or _FakeResponse([]))
    )

    result = geocoding.NominatimGeocodingProvider().geocode(address_line_1="", city="", state="", zip_code="")

    assert result is None
    assert calls == []


def test_nominatim_provider_timeout_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(*args, **kwargs):
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(geocoding, "_get_http_client", lambda: _FakeClient(fake_get))

    result = geocoding.NominatimGeocodingProvider().geocode(
        address_line_1="123 Main St", city="Hoboken", state="NJ", zip_code="07030"
    )

    assert result is None


def test_nominatim_provider_http_error_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(geocoding, "_get_http_client", lambda: _FakeClient(lambda *a, **kw: _FakeResponse({}, status_code=503)))

    result = geocoding.NominatimGeocodingProvider().geocode(
        address_line_1="123 Main St", city="Hoboken", state="NJ", zip_code="07030"
    )

    assert result is None


def test_nominatim_provider_malformed_json_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(*args, **kwargs):
        raise httpx.HTTPError("bad body")

    monkeypatch.setattr(geocoding, "_get_http_client", lambda: _FakeClient(fake_get))

    result = geocoding.NominatimGeocodingProvider().geocode(
        address_line_1="123 Main St", city="Hoboken", state="NJ", zip_code="07030"
    )

    assert result is None


def test_nominatim_provider_missing_fields_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        geocoding, "_get_http_client", lambda: _FakeClient(lambda *a, **kw: _FakeResponse([{"unexpected": "shape"}]))
    )

    result = geocoding.NominatimGeocodingProvider().geocode(
        address_line_1="123 Main St", city="Hoboken", state="NJ", zip_code="07030"
    )

    assert result is None


def test_geocode_address_caches_successful_result(monkeypatch: pytest.MonkeyPatch, clinic) -> None:
    calls = []

    class _CountingProvider:
        def geocode(self, **kwargs):
            calls.append(kwargs)
            return geocoding.GeocodeResult(latitude=1.0, longitude=2.0, normalized_address="Somewhere")

    monkeypatch.setattr(geocoding, "get_geocoding_provider", lambda: _CountingProvider())

    first = geocoding.geocode_address(
        clinic_id=clinic.id, address_line_1="1 A St", city="X", state="NY", zip_code="10001"
    )
    second = geocoding.geocode_address(
        clinic_id=clinic.id, address_line_1="1 A St", city="X", state="NY", zip_code="10001"
    )

    assert len(calls) == 1  # second call was served from cache
    assert first is not None and second is not None
    assert first.latitude == second.latitude == 1.0
    assert second.normalized_address == "Somewhere"


def test_geocode_address_caches_negative_result(monkeypatch: pytest.MonkeyPatch, clinic) -> None:
    calls = []
    monkeypatch.setattr(
        geocoding, "get_geocoding_provider", lambda: type("P", (), {"geocode": lambda self, **kw: calls.append(1)})()
    )

    first = geocoding.geocode_address(
        clinic_id=clinic.id, address_line_1="Bad Address", city="X", state="NY", zip_code="10001"
    )
    second = geocoding.geocode_address(
        clinic_id=clinic.id, address_line_1="Bad Address", city="X", state="NY", zip_code="10001"
    )

    assert first is None
    assert second is None
    assert len(calls) == 1


def test_geocode_address_cache_is_scoped_per_clinic(monkeypatch: pytest.MonkeyPatch, clinic, db_session) -> None:
    from app.models.clinic import Clinic

    other_clinic = Clinic(name="Other Clinic")
    db_session.add(other_clinic)
    db_session.commit()
    db_session.refresh(other_clinic)

    calls = []

    class _CountingProvider:
        def geocode(self, **kwargs):
            calls.append(kwargs)
            return geocoding.GeocodeResult(latitude=1.0, longitude=2.0)

    monkeypatch.setattr(geocoding, "get_geocoding_provider", lambda: _CountingProvider())

    geocoding.geocode_address(clinic_id=clinic.id, address_line_1="1 A St", city="X", state="NY", zip_code="10001")
    geocoding.geocode_address(
        clinic_id=other_clinic.id, address_line_1="1 A St", city="X", state="NY", zip_code="10001"
    )

    assert len(calls) == 2  # not shared across clinics, even for the identical address
