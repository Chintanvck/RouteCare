"""
RouteCare AI - Routing service.

Mirrors app.services.geocoding's shape on purpose: a `RoutingProvider`
Protocol, a real implementation (OSRM, per
docs/03_System_Architecture.md section 9), and a factory function so
the scheduling/optimization code that will eventually consume this
never depends on OSRM specifically. app.services.travel_time_service is
the only caller of `get_routing_provider()` - it owns caching, exactly
like app.services.geocoding.geocode_address owns geocoding's cache.

Distances/durations are returned in metric base units (meters, seconds)
- unit conversion (miles, minutes) is a presentation concern that
belongs in the schema/frontend layer, not baked into the provider
result.
"""

from functools import lru_cache
from typing import Protocol

import httpx

from app.core.config import settings


@lru_cache
def _get_http_client() -> httpx.Client:
    """One pooled, keep-alive httpx.Client reused across every OSRM call in this process, instead
    of the ad-hoc `httpx.get(...)` module function (which opens a brand-new connection - full
    TCP+TLS handshake - on every single call). Safe to share across threads: httpx.Client's
    synchronous API is documented as thread-safe for concurrent requests. One instance per process
    (web worker or Celery worker) - never closed explicitly, same lifetime as
    app.core.cache.get_redis_client()'s connection."""
    return httpx.Client(timeout=settings.ROUTING_TIMEOUT_SECONDS)


class RouteResult:
    def __init__(self, distance_meters: float, duration_seconds: float) -> None:
        self.distance_meters = distance_meters
        self.duration_seconds = duration_seconds


class RoutingProvider(Protocol):
    def route(self, *, origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float) -> RouteResult | None:
        """A single driving route, or None if unreachable/failed (no route between the points,
        network error, timeout, or invalid coordinates - all indistinguishable to the caller)."""
        ...

    def route_matrix(self, *, points: list[tuple[float, float]]) -> list[list[RouteResult | None]] | None:
        """Full origin x destination driving matrix for `points` (each a (lat, lng) pair), in the
        same order as `points` on both axes. A None matrix entry means that specific pair is
        unreachable; a None return means the whole request failed (network/timeout/error)."""
        ...


class NullRoutingProvider:
    """No-op provider - used in tests and as a safe fallback; never makes a network call."""

    def route(self, *, origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float) -> RouteResult | None:
        return None

    def route_matrix(self, *, points: list[tuple[float, float]]) -> list[list[RouteResult | None]] | None:
        return None


class OSRMRoutingProvider:
    """Real routing via OSRM (Open Source Routing Machine), per
    docs/03_System_Architecture.md section 9. Any failure mode - no route found, network error,
    timeout, non-200 response, unparseable body, invalid coordinates - is swallowed and reported
    as `None`, never raised, matching app.services.geocoding's contract.
    """

    def route(self, *, origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float) -> RouteResult | None:
        coords = f"{origin_lng},{origin_lat};{dest_lng},{dest_lat}"
        try:
            response = _get_http_client().get(
                f"{settings.OSRM_BASE_URL}/route/v1/driving/{coords}",
                params={"overview": "false"},
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError):
            return None

        if body.get("code") != "Ok" or not body.get("routes"):
            return None

        try:
            route = body["routes"][0]
            return RouteResult(distance_meters=float(route["distance"]), duration_seconds=float(route["duration"]))
        except (KeyError, TypeError, ValueError):
            return None

    def route_matrix(self, *, points: list[tuple[float, float]]) -> list[list[RouteResult | None]] | None:
        if len(points) < 2:
            return None

        coords = ";".join(f"{lng},{lat}" for lat, lng in points)
        try:
            response = _get_http_client().get(
                f"{settings.OSRM_BASE_URL}/table/v1/driving/{coords}",
                params={"annotations": "duration,distance"},
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError):
            return None

        if body.get("code") != "Ok":
            return None

        try:
            durations = body["durations"]
            distances = body["distances"]
            size = len(points)
            matrix: list[list[RouteResult | None]] = []
            for i in range(size):
                row: list[RouteResult | None] = []
                for j in range(size):
                    duration = durations[i][j]
                    distance = distances[i][j]
                    if duration is None or distance is None:
                        row.append(None)
                    else:
                        row.append(RouteResult(distance_meters=float(distance), duration_seconds=float(duration)))
                matrix.append(row)
            return matrix
        except (KeyError, TypeError, ValueError, IndexError):
            return None


def get_routing_provider() -> RoutingProvider:
    return OSRMRoutingProvider()
