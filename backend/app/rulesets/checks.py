"""Category and exchange validation independent of FastAPI or database models."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from backend.app.rulesets.conditions import is_safe_pattern
from backend.app.rulesets.schema import CategoryRule, ExchangeRule


@dataclass(frozen=True)
class RuleIssue:
    path: str
    code: str
    message: str


@dataclass(frozen=True)
class ExchangeValidation:
    issues: tuple[RuleIssue, ...]
    normalized: dict[str, dict[str, Any]]


def validate_categories(rule: CategoryRule, selected: dict[str, str]) -> list[RuleIssue]:
    issues: list[RuleIssue] = []
    known = {dimension.key: dimension for dimension in rule.dimensions}
    for key in selected:
        if key not in known:
            issues.append(
                RuleIssue(
                    f"categories.{key}",
                    "unknown_dimension",
                    "Category dimension is not configured.",
                )
            )
    for key, dimension in known.items():
        value = selected.get(key)
        if value is None:
            if dimension.required:
                issues.append(
                    RuleIssue(f"categories.{key}", "required", "A category value is required.")
                )
            continue
        if value not in {choice.key for choice in dimension.choices}:
            issues.append(
                RuleIssue(
                    f"categories.{key}", "invalid_choice", "Category choice is not configured."
                )
            )
    selected_dimensions = {key for key, value in selected.items() if value and key in known}
    for group in rule.mutually_exclusive:
        active = sorted(selected_dimensions.intersection(group))
        if len(active) > 1:
            issues.append(
                RuleIssue(
                    "categories",
                    "incompatible_categories",
                    "These category dimensions cannot be selected together: " + ", ".join(active),
                )
            )
    return issues


def _normalize_field(value: Any, field) -> tuple[Any | None, str | None]:
    if not isinstance(value, str) and field.value_type in {
        "text",
        "callsign",
        "serial",
        "grid",
        "zone",
    }:
        if not (field.value_type == "text" and isinstance(value, (int, bool))):
            return None, "Value must be text."
    if isinstance(value, str) and len(value) > field.max_length:
        return None, f"Value cannot exceed {field.max_length} characters."
    if field.value_type in {"integer", "serial"}:
        if isinstance(value, bool):
            return None, "Value must be an integer."
        try:
            if isinstance(value, int):
                result = value
            elif isinstance(value, str) and re.fullmatch(r"[+-]?[0-9]+", value.strip()):
                result = int(value.strip())
            else:
                return None, "Value must be an integer."
        except ValueError:
            return None, "Value must be an integer."
        if field.value_type == "serial" and result < 1:
            return None, "Serial numbers must be positive integers."
        if field.min_integer is not None and result < field.min_integer:
            return None, f"Value must be at least {field.min_integer}."
        if field.max_integer is not None and result > field.max_integer:
            return None, f"Value must be at most {field.max_integer}."
        return result, None

    normalized = str(value).strip()
    if not normalized:
        return None, "Value cannot be blank."
    if field.value_type in {"callsign", "grid", "zone", "enum"}:
        normalized = normalized.upper()
    if field.value_type == "enum" and normalized not in {
        choice.upper() for choice in field.choices
    }:
        return None, "Value is not one of the configured choices."
    if field.pattern is not None:
        if not is_safe_pattern(field.pattern):
            return None, "Configured field pattern is outside the supported safe subset."
        if len(normalized) > 512 or re.fullmatch(field.pattern, normalized) is None:
            return None, "Value does not match the configured format."
    return normalized, None


def validate_exchange(
    rule: ExchangeRule,
    *,
    sent: dict[str, Any],
    received: dict[str, Any],
    entry: dict[str, Any],
) -> ExchangeValidation:
    """Validate configured values while returning raw mappings unchanged for audit."""
    sources = {"sent": sent, "received": received, "entry": entry}
    normalized: dict[str, dict[str, Any]] = {key: {} for key in sources}
    issues: list[RuleIssue] = []
    for field in rule.fields:
        destinations = ("sent", "received") if field.direction == "both" else (field.direction,)
        for destination in destinations:
            source = sources[destination]
            value = source.get(field.key)
            path = f"exchange.{destination}.{field.key}"
            if value is None:
                if field.required:
                    issues.append(RuleIssue(path, "required", "Exchange value is required."))
                continue
            normal_value, error = _normalize_field(value, field)
            if error:
                issues.append(RuleIssue(path, "invalid_value", error))
            else:
                normalized[destination][field.key] = normal_value
    return ExchangeValidation(tuple(issues), normalized)
