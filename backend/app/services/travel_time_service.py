"""
RouteCare AI - Travel-time calculation, the caching/business layer above
app.services.routing.

This is the seam the future optimization engine (Phase 6, per
docs/07_AI_Optimization_Engine.md section 14 - "Routing Integration" /
"Travel Matrix") is meant to call: it never needs to know about OSRM,
Redis, or HTTP at all, just `get_travel_time`/`get_travel_time_matrix`.

Caching keys are coordinate-based, not patient/therapist-id-based - if
a patient's location changes, the old cache entry is simply never hit
again rather than needing explicit invalidation.

Matrix requests use one batched OSRM /table call for the whole matrix
whenever any pair is missing from the cache (simpler than partial
fetches, and OSRM computes the full NxN in one call regardless of which
subset is actually needed) - this is the "avoid one request per pair"
requirement, capped at MAPS_MAX_MATRIX_POINTS so a request never grows
unbounded within a single synchronous call.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.core.cache import cache_get_json, cache_set_json, make_cache_key
from app.core.config import settings
from app.services import routing

METERS_PER_MILE = 1609.344


@dataclass(frozen=True)
class LocationPoint:
    latitude: float
    longitude: float


@dataclass(frozen=True)
class TravelTimeResult:
    distance_miles: float
    duration_minutes: float
    calculated_at: datetime
    cached: bool


class MatrixTooLargeError(ValueError):
    pass


def _to_result(route: routing.RouteResult, *, calculated_at: datetime, cached: bool) -> TravelTimeResult:
    return TravelTimeResult(
        distance_miles=round(route.distance_meters / METERS_PER_MILE, 2),
        duration_minutes=round(route.duration_seconds / 60, 1),
        calculated_at=calculated_at,
        cached=cached,
    )


def _result_from_cache_entry(entry: dict[str, Any]) -> TravelTimeResult:
    return TravelTimeResult(
        distance_miles=entry["distance_miles"],
        duration_minutes=entry["duration_minutes"],
        calculated_at=datetime.fromisoformat(entry["calculated_at"]),
        cached=True,
    )


def _pair_cache_key(clinic_id: uuid.UUID, origin: LocationPoint, destination: LocationPoint) -> str:
    def fmt(point: LocationPoint) -> str:
        return f"{point.latitude:.5f},{point.longitude:.5f}"

    return make_cache_key(str(clinic_id), "traveltime", fmt(origin), fmt(destination))


def get_travel_time(
    *, clinic_id: uuid.UUID, origin: LocationPoint, destination: LocationPoint
) -> TravelTimeResult | None:
    """Distance/duration for one origin -> destination pair, or None if unreachable/unavailable."""
    key = _pair_cache_key(clinic_id, origin, destination)
    cached = cache_get_json(key)
    if cached is not None:
        return _result_from_cache_entry(cached) if cached.get("reachable") else None

    route = routing.get_routing_provider().route(
        origin_lat=origin.latitude,
        origin_lng=origin.longitude,
        dest_lat=destination.latitude,
        dest_lng=destination.longitude,
    )
    now = datetime.now(timezone.utc)
    if route is None:
        cache_set_json(key, {"reachable": False}, ttl_seconds=settings.TRAVEL_TIME_CACHE_TTL_SECONDS)
        return None

    result = _to_result(route, calculated_at=now, cached=False)
    cache_set_json(
        key,
        {
            "reachable": True,
            "distance_miles": result.distance_miles,
            "duration_minutes": result.duration_minutes,
            "calculated_at": now.isoformat(),
        },
        ttl_seconds=settings.TRAVEL_TIME_CACHE_TTL_SECONDS,
    )
    return result


def get_travel_time_matrix(*, clinic_id: uuid.UUID, points: list[LocationPoint]) -> list[list[TravelTimeResult | None]]:
    """Full origin x destination matrix for `points`, same order on both axes. A None cell means
    that pair is unreachable or could not be calculated; the diagonal is always None (no
    self-to-self travel time)."""
    if len(points) < 2:
        raise ValueError("At least 2 points are required to calculate a travel-time matrix.")
    if len(points) > settings.MAPS_MAX_MATRIX_POINTS:
        raise MatrixTooLargeError(
            f"A travel-time matrix request is limited to {settings.MAPS_MAX_MATRIX_POINTS} points at a time."
        )

    size = len(points)
    result_matrix: list[list[TravelTimeResult | None]] = [[None] * size for _ in range(size)]
    missing: list[tuple[int, int]] = []

    for i in range(size):
        for j in range(size):
            if i == j:
                continue
            cached = cache_get_json(_pair_cache_key(clinic_id, points[i], points[j]))
            if cached is None:
                missing.append((i, j))
            elif cached.get("reachable"):
                result_matrix[i][j] = _result_from_cache_entry(cached)

    if not missing:
        return result_matrix

    raw_matrix = routing.get_routing_provider().route_matrix(points=[(p.latitude, p.longitude) for p in points])
    if raw_matrix is None:
        # Whole request failed (network/timeout) - keep whatever was already cached and leave the
        # rest None rather than guessing; a future request will retry the missing pairs.
        return result_matrix

    now = datetime.now(timezone.utc)
    for i, j in missing:
        route = raw_matrix[i][j]
        key = _pair_cache_key(clinic_id, points[i], points[j])
        if route is None:
            cache_set_json(key, {"reachable": False}, ttl_seconds=settings.TRAVEL_TIME_CACHE_TTL_SECONDS)
            continue
        result = _to_result(route, calculated_at=now, cached=False)
        result_matrix[i][j] = result
        cache_set_json(
            key,
            {
                "reachable": True,
                "distance_miles": result.distance_miles,
                "duration_minutes": result.duration_minutes,
                "calculated_at": now.isoformat(),
            },
            ttl_seconds=settings.TRAVEL_TIME_CACHE_TTL_SECONDS,
        )

    return result_matrix
