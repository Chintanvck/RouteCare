"""Tests for TimestampMixin/SoftDeleteMixin, via a throwaway table (never a real domain model)."""

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.database.types import GUID
from app.models.mixins import SoftDeleteMixin, TimestampMixin


class _Gadget(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "test_mixin_gadgets"
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(default="unnamed")


@pytest.fixture()
def gadget_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine, tables=[_Gadget.__table__])
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine, tables=[_Gadget.__table__])


def test_timestamps_are_set_on_insert(gadget_session: Session) -> None:
    gadget = _Gadget(name="widget")
    gadget_session.add(gadget)
    gadget_session.commit()
    gadget_session.refresh(gadget)

    assert gadget.created_at is not None
    assert gadget.updated_at is not None


def test_updated_at_changes_on_update(gadget_session: Session) -> None:
    gadget = _Gadget(name="widget")
    gadget_session.add(gadget)
    gadget_session.commit()
    gadget_session.refresh(gadget)
    first_updated_at = gadget.updated_at

    gadget.name = "renamed"
    gadget_session.commit()
    gadget_session.refresh(gadget)

    assert gadget.updated_at >= first_updated_at


def test_is_deleted_false_by_default(gadget_session: Session) -> None:
    gadget = _Gadget(name="widget")
    gadget_session.add(gadget)
    gadget_session.commit()

    assert gadget.is_deleted is False
    assert gadget.deleted_at is None


def test_is_deleted_true_after_soft_delete(gadget_session: Session) -> None:
    from datetime import datetime, timezone

    gadget = _Gadget(name="widget")
    gadget_session.add(gadget)
    gadget_session.commit()

    gadget.deleted_at = datetime.now(timezone.utc)
    gadget_session.commit()

    assert gadget.is_deleted is True
