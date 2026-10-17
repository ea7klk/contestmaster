"""Ruleset catalog, validation, and privileged immutable-version endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.api.auth import AuthenticatedUser
from backend.app.api.errors import API_ERROR_RESPONSES, error_response
from backend.app.api.pagination import Page, page_meta, pagination_parameters
from backend.app.audit import record_audit_event
from backend.app.contest_deletion import DeletionConflictError, delete_unused_ruleset_version
from backend.app.db import get_session
from backend.app.models import Ruleset, RulesetAdministrator, RulesetVersion, SystemRole, SystemUser
from backend.app.rulesets.catalog_validation import catalog_reference_errors
from backend.app.rulesets.persistence import (
    RulesetConflictError,
    RulesetPersistenceError,
    load_ruleset_version,
    save_ruleset_version,
)
from backend.app.rulesets.registry import rule_catalog
from backend.app.rulesets.schema import RulesetDefinition
from backend.app.rulesets.summary import validation_report
from backend.app.rulesets.validation import RulesetValidationError, validate_ruleset

router = APIRouter(tags=["rulesets"])


def _can_manage_ruleset(session: Session, ruleset: Ruleset | None, actor: object) -> bool:
    if ruleset is None:
        return False
    if getattr(actor, "role", None) is SystemRole.GLOBAL_ADMINISTRATOR:
        return True
    user_id = getattr(actor, "user_id", None)
    if ruleset.owner_user_id == user_id:
        return True
    return session.get(RulesetAdministrator, (ruleset.id, user_id)) is not None


def _can_manage_ruleset_version(session: Session, version: RulesetVersion, actor: object) -> bool:
    if getattr(actor, "role", None) is SystemRole.GLOBAL_ADMINISTRATOR:
        return True
    if version.ruleset_id is None:
        # Compatibility for old/test rows created before stable ruleset roots existed.
        return version.created_by_user_id == getattr(actor, "user_id", None)
    return _can_manage_ruleset(session, session.get(Ruleset, version.ruleset_id), actor)


def _can_manage_ruleset_members(session: Session, ruleset: Ruleset, actor: object) -> bool:
    return getattr(
        actor, "role", None
    ) is SystemRole.GLOBAL_ADMINISTRATOR or ruleset.owner_user_id == getattr(actor, "user_id", None)


class RulesetDeleteConfirmation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    confirm_identity: str = Field(min_length=1, max_length=202)


@router.get("/catalog", responses=API_ERROR_RESPONSES)
def get_rule_catalog() -> dict[str, object]:
    """Return the typed, built-in rule schemas available to the composer."""
    return {"rule_types": rule_catalog()}


@router.post("/validate", responses=API_ERROR_RESPONSES, response_model=None)
def validate_ruleset_payload(
    payload: dict[str, Any],
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> JSONResponse | dict[str, object]:
    """Validate a proposed ruleset and return a readable summary/example without saving it."""
    try:
        definition = validate_ruleset(payload)
        catalog_errors = catalog_reference_errors(session, definition)
        if catalog_errors:
            raise RulesetValidationError(catalog_errors)
    except RulesetValidationError as exc:
        details = [
            {
                "location": [part for part in str(issue["path"]).split(".") if part],
                "message": str(issue["message"]),
                "type": "ruleset_configuration_error",
            }
            for issue in exc.errors
        ]
        return error_response(
            request,
            422,
            "invalid_ruleset",
            "Ruleset configuration is invalid.",
            details,
        )
    return validation_report(definition)


@router.get("/versions", responses=API_ERROR_RESPONSES)
def list_ruleset_versions(
    actor: AuthenticatedUser,
    session: Annotated[Session, Depends(get_session)],
    page: Annotated[Page, Depends(pagination_parameters)],
    q: Annotated[str | None, Query(max_length=120)] = None,
) -> dict[str, object]:
    statement = select(RulesetVersion)
    count_statement = select(func.count()).select_from(RulesetVersion)
    if actor.role is not SystemRole.GLOBAL_ADMINISTRATOR:
        accessible_ids = select(Ruleset.id).where(
            (Ruleset.owner_user_id == actor.user_id)
            | Ruleset.id.in_(
                select(RulesetAdministrator.ruleset_id).where(
                    RulesetAdministrator.user_id == actor.user_id
                )
            )
        )
        accessible_versions = or_(
            RulesetVersion.ruleset_id.in_(accessible_ids),
            (RulesetVersion.ruleset_id.is_(None))
            & (RulesetVersion.created_by_user_id == actor.user_id),
        )
        statement = statement.where(accessible_versions)
        count_statement = count_statement.where(accessible_versions)
    search = (q or "").strip()
    if search:
        pattern = f"%{search}%"
        search_filter = or_(
            RulesetVersion.ruleset_key.ilike(pattern),
            RulesetVersion.version.ilike(pattern),
            RulesetVersion.source_edition.ilike(pattern),
        )
        statement = statement.where(search_filter)
        count_statement = count_statement.where(search_filter)
    total = session.scalar(count_statement) or 0
    versions = list(
        session.scalars(
            statement.order_by(
                RulesetVersion.ruleset_key, RulesetVersion.version, RulesetVersion.id
            )
            .offset((page.page - 1) * page.page_size)
            .limit(page.page_size)
        )
    )
    return {
        "items": [
            {
                "id": version.id,
                "ruleset_id": version.ruleset_id,
                "ruleset_key": version.ruleset_key,
                "version": version.version,
                "source_url": version.source_url,
                "source_edition": version.source_edition,
                "rule_type_keys": version.rule_type_keys,
                "created_by_user_id": version.created_by_user_id,
                "created_at": version.created_at,
                "can_delete": (
                    actor.role is SystemRole.GLOBAL_ADMINISTRATOR
                    or version.created_by_user_id == actor.user_id
                ),
            }
            for version in versions
        ],
        "meta": page_meta(page, total),
    }


@router.get("/versions/{version_id}", responses=API_ERROR_RESPONSES)
def get_ruleset_version(
    version_id: int,
    actor: AuthenticatedUser,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    version = session.get(RulesetVersion, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Ruleset version not found.")
    if not _can_manage_ruleset_version(session, version, actor):
        raise HTTPException(status_code=404, detail="Ruleset version not found.")
    try:
        definition = load_ruleset_version(version)
    except RulesetPersistenceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "id": version.id,
        "ruleset_id": version.ruleset_id,
        "configuration": definition.model_dump(mode="json"),
    }


@router.post("/versions", responses=API_ERROR_RESPONSES, response_model=None)
def persist_ruleset_version(
    payload: RulesetDefinition,
    actor: AuthenticatedUser,
    session: Annotated[Session, Depends(get_session)],
    response: Response,
    request: Request,
) -> dict[str, object] | JSONResponse:
    try:
        definition = validate_ruleset(payload.model_dump(mode="json"))
        catalog_errors = catalog_reference_errors(session, definition)
        if catalog_errors:
            raise RulesetValidationError(catalog_errors)
    except RulesetValidationError as exc:
        details = [
            {
                "location": [part for part in str(issue["path"]).split(".") if part],
                "message": str(issue["message"]),
                "type": "ruleset_configuration_error",
            }
            for issue in exc.errors
        ]
        return error_response(
            request,
            422,
            "invalid_ruleset",
            "Ruleset configuration is invalid.",
            details,
        )
    ruleset = session.scalar(select(Ruleset).where(Ruleset.ruleset_key == definition.ruleset_key))
    if ruleset is not None and not _can_manage_ruleset(session, ruleset, actor):
        raise HTTPException(status_code=404, detail="Ruleset not found.")
    try:
        persisted = save_ruleset_version(session, definition, created_by_user_id=actor.user_id)
        if persisted.created:
            record_audit_event(
                session,
                actor_user_id=actor.user_id,
                action="ruleset_version.created",
                target_type="ruleset_version",
                target_id=persisted.version.id,
                metadata={
                    "ruleset_key": persisted.version.ruleset_key,
                    "version": persisted.version.version,
                },
                request_id=getattr(request.state, "request_id", None),
            )
        session.commit()
    except RulesetConflictError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="This ruleset key and version were concurrently saved with different content.",
        ) from exc
    version = persisted.version
    response.status_code = 201 if persisted.created else 200
    return {
        "id": version.id,
        "ruleset_id": version.ruleset_id,
        "ruleset_key": version.ruleset_key,
        "version": version.version,
        "rule_type_keys": version.rule_type_keys,
        "created": persisted.created,
        "created_at": version.created_at,
    }


@router.delete("/versions/{version_id}", status_code=204, responses=API_ERROR_RESPONSES)
def delete_ruleset_version_endpoint(
    version_id: int,
    payload: RulesetDeleteConfirmation,
    actor: AuthenticatedUser,
    session: Annotated[Session, Depends(get_session)],
    request: Request,
) -> Response:
    version = session.get(RulesetVersion, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Ruleset version not found.")
    if not _can_manage_ruleset_version(session, version, actor):
        raise HTTPException(status_code=404, detail="Ruleset version not found.")
    identity = f"{version.ruleset_key}@{version.version}"
    if payload.confirm_identity != identity:
        raise HTTPException(
            status_code=422,
            detail="Confirmation must exactly match the ruleset key and version.",
        )
    try:
        delete_unused_ruleset_version(session, version)
        record_audit_event(
            session,
            actor_user_id=actor.user_id,
            action="ruleset_version.deleted",
            target_type="ruleset_version",
            target_id=version_id,
            metadata={"ruleset_key": version.ruleset_key, "version": version.version},
            request_id=getattr(request.state, "request_id", None),
        )
        session.commit()
    except DeletionConflictError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="This ruleset version has retained references and cannot be deleted.",
        ) from exc
    return Response(status_code=204)


@router.get("/{ruleset_id}/administrators")
def list_ruleset_administrators(
    ruleset_id: int,
    actor: AuthenticatedUser,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    ruleset = session.get(Ruleset, ruleset_id)
    if ruleset is None or not _can_manage_ruleset(session, ruleset, actor):
        raise HTTPException(status_code=404, detail="Ruleset not found.")
    rows = session.execute(
        select(RulesetAdministrator, SystemUser)
        .join(SystemUser, SystemUser.id == RulesetAdministrator.user_id)
        .where(RulesetAdministrator.ruleset_id == ruleset.id)
        .order_by(SystemUser.display_name, SystemUser.id)
    )
    return {
        "owner_user_id": ruleset.owner_user_id,
        "items": [
            {"user_id": user.id, "username": user.username, "display_name": user.display_name}
            for _link, user in rows
        ],
        "eligible": [
            {"user_id": user.id, "username": user.username, "display_name": user.display_name}
            for user in session.scalars(
                select(SystemUser)
                .where(
                    SystemUser.is_active.is_(True),
                    SystemUser.role == SystemRole.CONTEST_MANAGER,
                    SystemUser.id != ruleset.owner_user_id,
                    SystemUser.id.not_in(
                        select(RulesetAdministrator.user_id).where(
                            RulesetAdministrator.ruleset_id == ruleset.id
                        )
                    ),
                )
                .order_by(SystemUser.display_name, SystemUser.id)
            )
        ],
    }


class RulesetAdministratorWrite(BaseModel):
    user_id: int = Field(strict=True, ge=1)


@router.post("/{ruleset_id}/administrators", status_code=201)
def add_ruleset_administrator(
    ruleset_id: int,
    payload: RulesetAdministratorWrite,
    actor: AuthenticatedUser,
    session: Annotated[Session, Depends(get_session)],
    request: Request,
) -> dict[str, object]:
    ruleset = session.get(Ruleset, ruleset_id)
    if ruleset is None or not _can_manage_ruleset_members(session, ruleset, actor):
        raise HTTPException(status_code=404, detail="Ruleset not found.")
    user = session.get(SystemUser, payload.user_id)
    if user is None or not user.is_active or user.role is not SystemRole.CONTEST_MANAGER:
        raise HTTPException(
            status_code=422, detail="Select an active contest administrator account."
        )
    if user.id == ruleset.owner_user_id:
        raise HTTPException(
            status_code=409, detail="The ruleset owner is already an administrator."
        )
    link = RulesetAdministrator(
        ruleset_id=ruleset.id, user_id=user.id, added_by_user_id=actor.user_id
    )
    session.add(link)
    try:
        session.flush()
        record_audit_event(
            session,
            actor_user_id=actor.user_id,
            action="ruleset.administrator_added",
            target_type="ruleset",
            target_id=ruleset.id,
            metadata={"administrator_user_id": user.id},
            request_id=getattr(request.state, "request_id", None),
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="This user already administers the ruleset."
        ) from exc
    return {"user_id": user.id, "username": user.username, "display_name": user.display_name}


@router.delete("/{ruleset_id}/administrators/{user_id}", status_code=204)
def remove_ruleset_administrator(
    ruleset_id: int,
    user_id: int,
    actor: AuthenticatedUser,
    session: Annotated[Session, Depends(get_session)],
    request: Request,
) -> Response:
    ruleset = session.get(Ruleset, ruleset_id)
    if ruleset is None or not _can_manage_ruleset_members(session, ruleset, actor):
        raise HTTPException(status_code=404, detail="Ruleset not found.")
    link = session.get(RulesetAdministrator, (ruleset_id, user_id))
    if link is None:
        raise HTTPException(status_code=404, detail="Ruleset administrator not found.")
    session.delete(link)
    record_audit_event(
        session,
        actor_user_id=actor.user_id,
        action="ruleset.administrator_removed",
        target_type="ruleset",
        target_id=ruleset.id,
        metadata={"administrator_user_id": user_id},
        request_id=getattr(request.state, "request_id", None),
    )
    session.commit()
    return Response(status_code=204)
