"""Global-admin management for separate band and mode catalogs."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.auth import GlobalAdministrator
from backend.app.audit import record_audit_event
from backend.app.db import get_session
from backend.app.models import BandCatalogItem, ModeCatalogItem, RulesetVersion

router = APIRouter(tags=["operating-catalog"])
type CatalogModel = type[BandCatalogItem] | type[ModeCatalogItem]


class CatalogItemFields(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    key: str = Field(min_length=1, max_length=40, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
    label: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    sort_order: int = Field(default=0, ge=0, le=10000)
    is_active: bool = True


class BandCatalogInput(CatalogItemFields):
    frequency_range: str | None = Field(default=None, max_length=120)
    contest_free: bool = False


class ModeCatalogInput(CatalogItemFields):
    pass


class LegacyCatalogInput(CatalogItemFields):
    """Compatibility request shape for the former kind-discriminated endpoint."""

    kind: Literal["band", "mode"]
    frequency_range: str | None = Field(default=None, max_length=120)
    contest_free: bool = False


def catalog_kind(model: CatalogModel) -> Literal["band", "mode"]:
    return "band" if model is BandCatalogItem else "mode"


def serialize(item: BandCatalogItem | ModeCatalogItem) -> dict[str, object]:
    result: dict[str, object] = {
        "id": item.id,
        "kind": catalog_kind(type(item)),
        "key": item.key,
        "label": item.label,
        "description": item.description,
        "sort_order": item.sort_order,
        "is_active": item.is_active,
    }
    if isinstance(item, BandCatalogItem):
        result["frequency_range"] = item.frequency_range
        result["contest_free"] = item.contest_free
    return result


def _configuration_uses(session: Session, *, kind: str, key: str) -> bool:
    field = "allowed_bands" if kind == "band" else "allowed_modes"
    for version in session.scalars(select(RulesetVersion)):
        for configured in version.configuration.get("rules", []):
            rule = configured.get("rule", {})
            if rule.get("kind") == "eligibility" and key in rule.get(field, []):
                return True
    return False


def _ordered(model: CatalogModel, *, active_only: bool = False):
    statement = select(model)
    if active_only:
        statement = statement.where(model.is_active.is_(True))
    return statement.order_by(model.sort_order, model.label)


def _list_kind(
    session: Session, model: CatalogModel, *, active_only: bool
) -> list[dict[str, object]]:
    return [serialize(item) for item in session.scalars(_ordered(model, active_only=active_only))]


def _create(
    payload: CatalogItemFields,
    model: CatalogModel,
    actor: GlobalAdministrator,
    session: Session,
    request: Request,
) -> dict[str, object]:
    kind = catalog_kind(model)
    if session.scalar(select(model.id).where(model.key == payload.key)) is not None:
        raise HTTPException(status_code=409, detail=f"That {kind} key already exists.")
    item = model(**payload.model_dump())
    session.add(item)
    session.flush()
    record_audit_event(
        session,
        actor_user_id=actor.user_id,
        action=f"operating_catalog.{kind}_created",
        target_type=f"{kind}_catalog_item",
        target_id=item.id,
        metadata={"key": item.key},
        request_id=getattr(request.state, "request_id", None),
    )
    session.commit()
    return serialize(item)


def _update(
    item_id: int,
    payload: CatalogItemFields,
    model: CatalogModel,
    actor: GlobalAdministrator,
    session: Session,
    request: Request,
) -> dict[str, object]:
    kind = catalog_kind(model)
    item = session.get(model, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"{kind.title()} not found.")
    if item.key != payload.key and _configuration_uses(session, kind=kind, key=item.key):
        raise HTTPException(
            status_code=409, detail="A catalog key used by a saved ruleset cannot be changed."
        )
    duplicate = session.scalar(
        select(model.id).where(model.key == payload.key, model.id != item_id)
    )
    if duplicate is not None:
        raise HTTPException(status_code=409, detail=f"That {kind} key already exists.")
    before = {"key": item.key, "is_active": item.is_active}
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    session.flush()
    record_audit_event(
        session,
        actor_user_id=actor.user_id,
        action=f"operating_catalog.{kind}_updated",
        target_type=f"{kind}_catalog_item",
        target_id=item.id,
        metadata={
            "before": before,
            "after": {"key": item.key, "is_active": item.is_active},
        },
        request_id=getattr(request.state, "request_id", None),
    )
    session.commit()
    return serialize(item)


def _delete(
    item_id: int,
    model: CatalogModel,
    actor: GlobalAdministrator,
    session: Session,
    request: Request,
) -> Response:
    kind = catalog_kind(model)
    item = session.get(model, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"{kind.title()} not found.")
    if _configuration_uses(session, kind=kind, key=item.key):
        raise HTTPException(
            status_code=409,
            detail="This catalog value is referenced by a saved ruleset; deactivate it instead.",
        )
    key = item.key
    session.delete(item)
    record_audit_event(
        session,
        actor_user_id=actor.user_id,
        action=f"operating_catalog.{kind}_deleted",
        target_type=f"{kind}_catalog_item",
        target_id=item_id,
        metadata={"key": key},
        request_id=getattr(request.state, "request_id", None),
    )
    session.commit()
    return Response(status_code=204)


@router.get("/bands")
def list_active_bands(session: Annotated[Session, Depends(get_session)]) -> dict[str, object]:
    return {"items": _list_kind(session, BandCatalogItem, active_only=True)}


@router.get("/modes")
def list_active_modes(session: Annotated[Session, Depends(get_session)]) -> dict[str, object]:
    return {"items": _list_kind(session, ModeCatalogItem, active_only=True)}


@router.get("/admin/bands")
def list_admin_bands(
    _actor: GlobalAdministrator,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    return {"items": _list_kind(session, BandCatalogItem, active_only=False)}


@router.get("/admin/modes")
def list_admin_modes(
    _actor: GlobalAdministrator,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    return {"items": _list_kind(session, ModeCatalogItem, active_only=False)}


@router.post("/admin/bands", status_code=201)
def create_band(
    payload: BandCatalogInput,
    actor: GlobalAdministrator,
    session: Annotated[Session, Depends(get_session)],
    request: Request,
) -> dict[str, object]:
    return _create(payload, BandCatalogItem, actor, session, request)


@router.put("/admin/bands/{item_id}")
def update_band(
    item_id: int,
    payload: BandCatalogInput,
    actor: GlobalAdministrator,
    session: Annotated[Session, Depends(get_session)],
    request: Request,
) -> dict[str, object]:
    return _update(item_id, payload, BandCatalogItem, actor, session, request)


@router.delete("/admin/bands/{item_id}", status_code=204)
def delete_band(
    item_id: int,
    actor: GlobalAdministrator,
    session: Annotated[Session, Depends(get_session)],
    request: Request,
) -> Response:
    return _delete(item_id, BandCatalogItem, actor, session, request)


@router.post("/admin/modes", status_code=201)
def create_mode(
    payload: ModeCatalogInput,
    actor: GlobalAdministrator,
    session: Annotated[Session, Depends(get_session)],
    request: Request,
) -> dict[str, object]:
    return _create(payload, ModeCatalogItem, actor, session, request)


@router.put("/admin/modes/{item_id}")
def update_mode(
    item_id: int,
    payload: ModeCatalogInput,
    actor: GlobalAdministrator,
    session: Annotated[Session, Depends(get_session)],
    request: Request,
) -> dict[str, object]:
    return _update(item_id, payload, ModeCatalogItem, actor, session, request)


@router.delete("/admin/modes/{item_id}", status_code=204)
def delete_mode(
    item_id: int,
    actor: GlobalAdministrator,
    session: Annotated[Session, Depends(get_session)],
    request: Request,
) -> Response:
    return _delete(item_id, ModeCatalogItem, actor, session, request)


@router.get("/operating-catalog")
def list_active_catalog(session: Annotated[Session, Depends(get_session)]) -> dict[str, object]:
    """Legacy combined read retained for clients migrating to split resources."""
    items = _list_kind(session, BandCatalogItem, active_only=True)
    items.extend(_list_kind(session, ModeCatalogItem, active_only=True))
    return {"items": items}


@router.get("/admin/operating-catalog")
def list_admin_catalog(
    _actor: GlobalAdministrator,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    """Legacy combined read retained for clients migrating to split resources."""
    items = _list_kind(session, BandCatalogItem, active_only=False)
    items.extend(_list_kind(session, ModeCatalogItem, active_only=False))
    return {"items": items}


def _legacy_payload(payload: LegacyCatalogInput) -> tuple[CatalogModel, CatalogItemFields]:
    values = payload.model_dump(exclude={"kind"})
    if payload.kind == "band":
        return BandCatalogItem, BandCatalogInput(**values)
    mode_values = {key: values[key] for key in CatalogItemFields.model_fields}
    return ModeCatalogItem, ModeCatalogInput(**mode_values)


@router.post("/admin/operating-catalog", status_code=201)
def create_legacy_catalog_item(
    payload: LegacyCatalogInput,
    actor: GlobalAdministrator,
    session: Annotated[Session, Depends(get_session)],
    request: Request,
) -> dict[str, object]:
    model, fields = _legacy_payload(payload)
    return _create(fields, model, actor, session, request)


@router.put("/admin/operating-catalog/{item_id}")
def update_legacy_catalog_item(
    item_id: int,
    payload: LegacyCatalogInput,
    actor: GlobalAdministrator,
    session: Annotated[Session, Depends(get_session)],
    request: Request,
) -> dict[str, object]:
    model, fields = _legacy_payload(payload)
    return _update(item_id, fields, model, actor, session, request)


@router.delete("/admin/operating-catalog/{item_id}", status_code=204)
def delete_legacy_catalog_item(
    item_id: int,
    actor: GlobalAdministrator,
    session: Annotated[Session, Depends(get_session)],
    request: Request,
) -> Response:
    band_exists = session.get(BandCatalogItem, item_id) is not None
    mode_exists = session.get(ModeCatalogItem, item_id) is not None
    if band_exists and mode_exists:
        raise HTTPException(
            status_code=409,
            detail="This legacy ID is ambiguous; use the separate band or mode resource.",
        )
    if band_exists:
        return _delete(item_id, BandCatalogItem, actor, session, request)
    if mode_exists:
        return _delete(item_id, ModeCatalogItem, actor, session, request)
    raise HTTPException(status_code=404, detail="Catalog item not found.")
