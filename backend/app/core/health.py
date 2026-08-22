"""
RouteCare AI - Infrastructure health checks used by GET /health/ready.

Each check returns (ok, error_class_name) rather than (ok, str(exc)) -
a real DB/Redis failure often embeds the connection string (including
credentials) in its exception message, and that must never reach an
API client. The class name alone is enough to know "database is down"
without leaking anything sensitive.

These connect directly to the configured DATABASE_URL/REDIS_URL rather
than going through FastAPI's `get_db` dependency, since readiness needs
to check the real configured infrastructure, not whatever a test/dev
override might have substituted.
"""

import redis
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.database.session import SessionLocal


def check_database() -> tuple[bool, str | None]:
    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
        return True, None
    except SQLAlchemyError as exc:
        return False, type(exc).__name__


def check_redis() -> tuple[bool, str | None]:
    try:
        client = redis.from_url(settings.REDIS_URL, socket_connect_timeout=2, socket_timeout=2)
        client.ping()
        return True, None
    except redis.RedisError as exc:
        return False, type(exc).__name__
