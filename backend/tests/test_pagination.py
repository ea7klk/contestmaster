import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.app.api.pagination import Page, page_meta, pagination_parameters, validate_sort


def test_pagination_metadata_and_defaults():
    assert page_meta(Page(), 101) == {"page": 1, "page_size": 50, "total": 101, "pages": 3}


def test_sort_whitelist_and_unique_tie_breaker_make_paging_stable():
    assert validate_sort(Page(sort="score", order="desc"), {"score", "callsign"}, "id") == [
        ("score", "desc"),
        ("id", "asc"),
    ]


def test_sort_rejects_fields_not_whitelisted_by_resource():
    with pytest.raises(HTTPException) as error:
        validate_sort(Page(sort="database_expression"), {"score", "callsign"}, "id")
    assert error.value.status_code == 422


@pytest.mark.parametrize("query", ["page=0", "page_size=0", "page_size=101", "order=sideways"])
def test_pagination_rejects_invalid_bounds_and_order(query):
    app = FastAPI()

    @app.get("/items")
    def items(params=Depends(pagination_parameters)):  # noqa: B008
        return params.model_dump()

    assert TestClient(app).get(f"/items?{query}").status_code == 422
