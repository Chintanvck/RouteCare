"""
RouteCare AI - Routing service tests.

Exercise app.services.routing directly by monkeypatching httpx.get -
never touches the real OSRM service.
"""

import httpx
import pytest

from app.services import routing


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


def test_osrm_route_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *a, **kw: _FakeResponse({"code": "Ok", "routes": [{"distance": 8047.0, "duration": 900.0}]}),
    )

    result = routing.OSRMRoutingProvider().route(origin_lat=40.7, origin_lng=-74.0, dest_lat=40.8, dest_lng=-74.1)

    assert result is not None
    assert result.distance_meters == 8047.0
    assert result.duration_seconds == 900.0


def test_osrm_route_no_route_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "get", lambda *a, **kw: _FakeResponse({"code": "NoRoute", "routes": []}))

    result = routing.OSRMRoutingProvider().route(origin_lat=0.0, origin_lng=0.0, dest_lat=89.9, dest_lng=179.9)

    assert result is None


def test_osrm_route_timeout_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(*args, **kwargs):
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(httpx, "get", fake_get)

    result = routing.OSRMRoutingProvider().route(origin_lat=40.7, origin_lng=-74.0, dest_lat=40.8, dest_lng=-74.1)

    assert result is None


def test_osrm_route_network_error_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "get", lambda *a, **kw: _FakeResponse({}, status_code=500))

    result = routing.OSRMRoutingProvider().route(origin_lat=40.7, origin_lng=-74.0, dest_lat=40.8, dest_lng=-74.1)

    assert result is None


def test_osrm_route_matrix_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *a, **kw: _FakeResponse(
            {
                "code": "Ok",
                "durations": [[0, 600, 900], [600, 0, 450], [900, 450, 0]],
                "distances": [[0, 5000, 8000], [5000, 0, 4000], [8000, 4000, 0]],
            }
        ),
    )

    matrix = routing.OSRMRoutingProvider().route_matrix(points=[(40.7, -74.0), (40.8, -74.1), (40.6, -74.2)])

    assert matrix is not None
    assert matrix[0][1].duration_seconds == 600
    assert matrix[1][2].distance_meters == 4000
    assert matrix[0][0].duration_seconds == 0  # self-pair still comes back as a real 0, filtering is the caller's job


def test_osrm_route_matrix_with_unreachable_pair(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *a, **kw: _FakeResponse(
            {"code": "Ok", "durations": [[0, None], [None, 0]], "distances": [[0, None], [None, 0]]}
        ),
    )

    matrix = routing.OSRMRoutingProvider().route_matrix(points=[(40.7, -74.0), (0.0, 0.0)])

    assert matrix is not None
    assert matrix[0][1] is None
    assert matrix[1][0] is None


def test_osrm_route_matrix_whole_request_failure_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(*args, **kwargs):
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(httpx, "get", fake_get)

    matrix = routing.OSRMRoutingProvider().route_matrix(points=[(40.7, -74.0), (40.8, -74.1)])

    assert matrix is None


def test_osrm_route_matrix_requires_at_least_two_points() -> None:
    matrix = routing.OSRMRoutingProvider().route_matrix(points=[(40.7, -74.0)])

    assert matrix is None
