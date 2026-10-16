"""Ruleset catalog, validation, and privileged immutable-version endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.api.auth import AuthenticatedUser
from backend.app.api.errors import API_ERROR_RESPONSES, error_response
from backend.app.audit import record_audit_event
from backend.app.contest_deletion import DeletionConflictError, delete_unused_ruleset_version
from backend.app.db import get_session
from backend.app.models import RulesetVersion, SystemRole
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
) -> dict[str, object]:
    versions = list(
        session.scalars(
            select(RulesetVersion).order_by(
                RulesetVersion.ruleset_key, RulesetVersion.version, RulesetVersion.id
            )
        )
    )
    return {
        "items": [
            {
                "id": version.id,
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
        ]
    }


@router.get("/versions/{version_id}", responses=API_ERROR_RESPONSES)
def get_ruleset_version(
    version_id: int,
    _actor: AuthenticatedUser,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    version = session.get(RulesetVersion, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Ruleset version not found.")
    try:
        definition = load_ruleset_version(version)
    except RulesetPersistenceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"id": version.id, "configuration": definition.model_dump(mode="json")}


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
    if (
        actor.role is not SystemRole.GLOBAL_ADMINISTRATOR
        and version.created_by_user_id != actor.user_id
    ):
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
