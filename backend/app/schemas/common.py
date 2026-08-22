"""
RouteCare AI - Shared response/query schemas for list endpoints.

Any future GET /patients, GET /appointments, GET /therapists, etc.
should use PaginationParams + PaginatedResponse rather than inventing
per-module pagination. See docs/13_Coding_Standards.md for the full
recommended filtering/sorting pattern - it's documentation-only
(typed query params per endpoint), not a generic query-builder, since a
generic one would trade away readability and type safety for a bit of
boilerplate saved.
"""

from typing import Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100

T = TypeVar("T")


class PaginationParams:
    """FastAPI dependency: `pagination: PaginationParams = Depends()`. Caps page_size so a client can never
    pull an unbounded number of rows in one request."""

    def __init__(
        self,
        page: int = Query(1, ge=1, description="1-indexed page number."),
        page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="Rows per page."),
    ) -> None:
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int
    total_pages: int

    @classmethod
    def create(cls, items: list[T], *, page: int, page_size: int, total: int) -> "PaginatedResponse[T]":
        total_pages = (total + page_size - 1) // page_size if page_size else 0
        return cls(items=items, page=page, page_size=page_size, total=total, total_pages=total_pages)
