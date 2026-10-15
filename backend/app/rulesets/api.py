"""Read-only ruleset catalog and configuration validation endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from backend.app.api.errors import API_ERROR_RESPONSES, error_response
from backend.app.rulesets.registry import rule_catalog
from backend.app.rulesets.summary import validation_report
from backend.app.rulesets.validation import RulesetValidationError, validate_ruleset

router = APIRouter(tags=["rulesets"])


@router.get("/catalog", responses=API_ERROR_RESPONSES)
def get_rule_catalog() -> dict[str, object]:
    """Return the typed, built-in rule schemas available to the composer."""
    return {"rule_types": rule_catalog()}


@router.post("/validate", responses=API_ERROR_RESPONSES, response_model=None)
def validate_ruleset_payload(
    payload: dict[str, Any], request: Request
) -> JSONResponse | dict[str, object]:
    """Validate a proposed ruleset and return a readable summary/example without saving it."""
    try:
        definition = validate_ruleset(payload)
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
