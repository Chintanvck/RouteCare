"""
RouteCare AI - Query pagination helper.

One small function, not a generic repository: callers build their own
SQLAlchemy Query (with whatever tenant/filter/sort clauses the endpoint
needs - see docs/13_Coding_Standards.md) and hand it here just to slice
out a page and get a total count.
"""

from typing import Any

from sqlalchemy.orm import Query

from app.schemas.common import PaginationParams


def paginate(query: Query, params: PaginationParams) -> tuple[list[Any], int]:
    # order_by(None) drops any ORDER BY before counting - ordering is
    # irrelevant to a COUNT(*) and some dialects can't optimize it away themselves.
    total = query.order_by(None).count()
    items = query.offset(params.offset).limit(params.page_size).all()
    return items, total
