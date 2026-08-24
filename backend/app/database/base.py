"""
RouteCare AI - SQLAlchemy declarative base.

All ORM models (introduced starting Phase 1's database implementation)
inherit from `Base` defined here so Alembic autogenerate can discover
them via a single shared metadata object.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
