"""
RouteCare AI - Generic Redis-backed JSON cache.

Thin wrapper over the same `redis` client used by Celery/health checks
(app.core.health.check_redis) - no new infrastructure, just a shared
place to get/set namespaced, TTL'd JSON values.

Caching is always best-effort: any Redis error (connection refused,
timeout, ...) is treated as a cache miss on read and a silent no-op on
write, never a propagated exception. A cold or unavailable cache must
degrade to "always call the provider," not break geocoding/routing.
"""

import json
from functools import lru_cache
from typing import Any

import redis

from app.core.config import settings


@lru_cache
def get_redis_client() -> redis.Redis:
    return redis.from_url(settings.REDIS_URL, socket_connect_timeout=2, socket_timeout=2, decode_responses=True)


def make_cache_key(*parts: str) -> str:
    return "routecare:" + ":".join(parts)


def cache_get_json(key: str) -> Any | None:
    try:
        raw = get_redis_client().get(key)
    except redis.RedisError:
        return None
    if raw is None:
        return None
    try:
        # redis-py's stubs type .get()'s return as a union that includes Awaitable (to cover
        # the async client class too); the sync client from get_redis_client() never actually
        # returns one, so `raw` is always a str here (decode_responses=True).
        return json.loads(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def cache_set_json(key: str, value: Any, *, ttl_seconds: int) -> None:
    try:
        get_redis_client().setex(key, ttl_seconds, json.dumps(value))
    except redis.RedisError:
        return
