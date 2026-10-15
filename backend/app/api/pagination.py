from typing import Annotated

from fastapi import HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100


class Page(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)
    sort: str = "created_at"
    order: str = Field(default="asc", pattern="^(asc|desc)$")


def pagination_parameters(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    sort: str = "created_at",
    order: Annotated[str, Query(pattern="^(asc|desc)$")] = "asc",
) -> Page:
    return Page(page=page, page_size=page_size, sort=sort, order=order)


def page_meta(page: Page, total: int) -> dict[str, int]:
    return {
        "page": page.page,
        "page_size": page.page_size,
        "total": total,
        "pages": (total + page.page_size - 1) // page.page_size,
    }


def validate_sort(page: Page, allowed_fields: set[str], tie_breaker: str) -> list[tuple[str, str]]:
    """Validate a resource sort key and add a unique secondary key for stable pages."""
    if page.sort not in allowed_fields:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unsupported sort field '{page.sort}'.",
        )
    ordering = [(page.sort, page.order)]
    if tie_breaker != page.sort:
        ordering.append((tie_breaker, "asc"))
    return ordering
