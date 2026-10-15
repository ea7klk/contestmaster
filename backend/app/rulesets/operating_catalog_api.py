"""Global-admin management for the shared eligibility band and mode catalogs."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.auth import GlobalAdministrator
from backend.app.audit import record_audit_event
from backend.app.db import get_session
from backend.app.models import OperatingCatalogItem, RulesetVersion

router = APIRouter(tags=["operating-catalog"])


class CatalogItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    kind: Literal["band", "mode"]
    key: str = Field(min_length=1, max_length=40, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
    label: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    frequency_range: str | None = Field(default=None, max_length=120)
    sort_order: int = Field(default=0, ge=0, le=10000)
    is_active: bool = True
    contest_free: bool = False


def serialize(item: OperatingCatalogItem) -> dict[str, object]:
    return {
        "id": item.id,
        "kind": item.kind,
        "key": item.key,
        "label": item.label,
        "description": item.description,
        "frequency_range": item.frequency_range,
        "sort_order": item.sort_order,
        "is_active": item.is_active,
        "contest_free": item.contest_free,
    }


def _configuration_uses(session: Session, *, kind: str, key: str) -> bool:
    field = "allowed_bands" if kind == "band" else "allowed_modes"
    for version in session.scalars(select(RulesetVersion)):
        for configured in version.configuration.get("rules", []):
            rule = configured.get("rule", {})
            if rule.get("kind") == "eligibility" and key in rule.get(field, []):
                return True
    return False


@router.get("/operating-catalog")
def list_active_catalog(
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    items = list(
        session.scalars(
            select(OperatingCatalogItem)
            .where(OperatingCatalogItem.is_active.is_(True))
            .order_by(
                OperatingCatalogItem.kind,
                OperatingCatalogItem.sort_order,
                OperatingCatalogItem.label,
            )
        )
    )
    return {"items": [serialize(item) for item in items]}


@router.get("/admin/operating-catalog")
def list_admin_catalog(
    _actor: GlobalAdministrator,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    items = list(
        session.scalars(
            select(OperatingCatalogItem).order_by(
                OperatingCatalogItem.kind,
                OperatingCatalogItem.sort_order,
                OperatingCatalogItem.label,
            )
        )
    )
    return {"items": [serialize(item) for item in items]}


@router.post("/admin/operating-catalog", status_code=201)
def create_catalog_item(
    payload: CatalogItemInput,
    actor: GlobalAdministrator,
    session: Annotated[Session, Depends(get_session)],
    request: Request,
) -> dict[str, object]:
    if (
        session.scalar(
            select(OperatingCatalogItem.id).where(
                OperatingCatalogItem.kind == payload.kind,
                OperatingCatalogItem.key == payload.key,
            )
        )
        is not None
    ):
        raise HTTPException(status_code=409, detail="That key already exists in this catalog.")
    item = OperatingCatalogItem(**payload.model_dump())
    session.add(item)
    session.flush()
    record_audit_event(
        session,
        actor_user_id=actor.user_id,
        action="operating_catalog.item_created",
        target_type="operating_catalog_item",
        target_id=item.id,
        metadata={"kind": item.kind, "key": item.key},
        request_id=getattr(request.state, "request_id", None),
    )
    session.commit()
    return serialize(item)


@router.put("/admin/operating-catalog/{item_id}")
def update_catalog_item(
    item_id: int,
    payload: CatalogItemInput,
    actor: GlobalAdministrator,
    session: Annotated[Session, Depends(get_session)],
    request: Request,
) -> dict[str, object]:
    item = session.get(OperatingCatalogItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Catalog item not found.")
    if (item.kind, item.key) != (payload.kind, payload.key) and _configuration_uses(
        session, kind=item.kind, key=item.key
    ):
        raise HTTPException(
            status_code=409, detail="A catalog key used by a saved ruleset cannot be changed."
        )
    duplicate = session.scalar(
        select(OperatingCatalogItem.id).where(
            OperatingCatalogItem.kind == payload.kind,
            OperatingCatalogItem.key == payload.key,
            OperatingCatalogItem.id != item_id,
        )
    )
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="That key already exists in this catalog.")
    before = {
        "kind": item.kind,
        "key": item.key,
        "is_active": item.is_active,
        "contest_free": item.contest_free,
    }
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    session.flush()
    record_audit_event(
        session,
        actor_user_id=actor.user_id,
        action="operating_catalog.item_updated",
        target_type="operating_catalog_item",
        target_id=item.id,
        metadata={
            "before": before,
            "after": {
                "kind": item.kind,
                "key": item.key,
                "is_active": item.is_active,
                "contest_free": item.contest_free,
            },
        },
        request_id=getattr(request.state, "request_id", None),
    )
    session.commit()
    return serialize(item)


@router.delete("/admin/operating-catalog/{item_id}", status_code=204)
def delete_catalog_item(
    item_id: int,
    actor: GlobalAdministrator,
    session: Annotated[Session, Depends(get_session)],
    request: Request,
) -> Response:
    item = session.get(OperatingCatalogItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Catalog item not found.")
    if _configuration_uses(session, kind=item.kind, key=item.key):
        raise HTTPException(
            status_code=409,
            detail="This catalog value is referenced by a saved ruleset; deactivate it instead.",
        )
    snapshot = {"kind": item.kind, "key": item.key}
    session.delete(item)
    record_audit_event(
        session,
        actor_user_id=actor.user_id,
        action="operating_catalog.item_deleted",
        target_type="operating_catalog_item",
        target_id=item_id,
        metadata=snapshot,
        request_id=getattr(request.state, "request_id", None),
    )
    session.commit()
    return Response(status_code=204)
