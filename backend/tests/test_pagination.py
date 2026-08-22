"""Tests for PaginationParams, PaginatedResponse, and the paginate() query helper."""

import uuid

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.database.pagination import paginate
from app.schemas.common import MAX_PAGE_SIZE, PaginatedResponse, PaginationParams


class _Widget(Base):
    __tablename__ = "test_pagination_widgets"
    id = Column(Integer, primary_key=True)
    name = Column(String)


def test_paginated_response_create_computes_total_pages() -> None:
    response = PaginatedResponse[int].create([1, 2, 3], page=1, page_size=25, total=53)
    assert response.total_pages == 3


def test_paginated_response_create_handles_exact_multiple() -> None:
    response = PaginatedResponse[int].create([1, 2], page=1, page_size=25, total=50)
    assert response.total_pages == 2


def test_paginated_response_create_handles_zero_total() -> None:
    response = PaginatedResponse[int].create([], page=1, page_size=25, total=0)
    assert response.total_pages == 0


@pytest.fixture()
def widget_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine, tables=[_Widget.__table__])
    session = sessionmaker(bind=engine)()
    for i in range(30):
        session.add(_Widget(id=i + 1, name=f"widget-{i}"))
    session.commit()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine, tables=[_Widget.__table__])


def test_paginate_returns_correct_slice_and_total(widget_session: Session) -> None:
    params = PaginationParams(page=2, page_size=10)
    items, total = paginate(widget_session.query(_Widget), params)

    assert total == 30
    assert len(items) == 10
    assert items[0].id == 11


def test_paginate_last_page_partial(widget_session: Session) -> None:
    params = PaginationParams(page=2, page_size=25)
    items, total = paginate(widget_session.query(_Widget), params)

    assert total == 30
    assert len(items) == 5


def test_pagination_params_offset() -> None:
    assert PaginationParams(page=1, page_size=25).offset == 0
    assert PaginationParams(page=3, page_size=10).offset == 20


# --- HTTP-level: page_size is capped, never unbounded ---


def _build_probe_app() -> FastAPI:
    app = FastAPI()

    @app.get("/items")
    def list_items(pagination: PaginationParams = Depends()):
        return {"page": pagination.page, "page_size": pagination.page_size}

    return app


@pytest.fixture()
def probe_client() -> TestClient:
    return TestClient(_build_probe_app())


def test_default_page_size(probe_client: TestClient) -> None:
    response = probe_client.get("/items")
    assert response.status_code == 200
    assert response.json()["page_size"] == 25


def test_page_size_over_max_is_rejected(probe_client: TestClient) -> None:
    response = probe_client.get(f"/items?page_size={MAX_PAGE_SIZE + 1}")
    assert response.status_code == 422


def test_page_size_at_max_is_accepted(probe_client: TestClient) -> None:
    response = probe_client.get(f"/items?page_size={MAX_PAGE_SIZE}")
    assert response.status_code == 200
    assert response.json()["page_size"] == MAX_PAGE_SIZE


def test_page_below_one_is_rejected(probe_client: TestClient) -> None:
    response = probe_client.get("/items?page=0")
    assert response.status_code == 422


def test_paginated_response_works_with_pydantic_model_items() -> None:
    from pydantic import BaseModel

    class Widget(BaseModel):
        id: uuid.UUID
        name: str

    widget = Widget(id=uuid.uuid4(), name="drill")
    response = PaginatedResponse[Widget].create([widget], page=1, page_size=25, total=1)

    assert response.items[0].name == "drill"
    assert response.total_pages == 1
