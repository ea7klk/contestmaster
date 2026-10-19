"""Safe evaluation of declarative ruleset conditions; no Python code is executed."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from backend.app.rulesets.schema import (
    AllCondition,
    AnyCondition,
    Condition,
    NotCondition,
)

_MISSING = object()
_UNSAFE_REGEX_TOKENS = ("(?", "\\1", "\\2", "{", "}", "|", "(", ")")


def is_safe_pattern(pattern: str) -> bool:
    """Accept a small regex subset that excludes grouping and backtracking features."""
    if len(pattern) > 64 or any(token in pattern for token in _UNSAFE_REGEX_TOKENS):
        return False
    try:
        re.compile(pattern)
    except re.error:
        return False
    return True


def _resolve_fact(context: Mapping[str, Any], path: str) -> Any:
    value: Any = context
    for part in path.split("."):
        if not isinstance(value, Mapping) or part not in value:
            return _MISSING
        value = value[part]
    return value


def evaluate_condition(condition: Condition, context: Mapping[str, Any]) -> bool:
    """Return true only when the typed predicate is known to match."""
    return evaluate_condition_result(condition, context) is True


def evaluate_condition_result(condition: Condition, context: Mapping[str, Any]) -> bool | None:
    """Evaluate a predicate with None representing missing/ambiguous fact data."""
    if isinstance(condition, AllCondition):
        results = [evaluate_condition_result(child, context) for child in condition.conditions]
        if False in results:
            return False
        return None if None in results else True
    if isinstance(condition, AnyCondition):
        results = [evaluate_condition_result(child, context) for child in condition.conditions]
        if True in results:
            return True
        return None if None in results else False
    if isinstance(condition, NotCondition):
        result = evaluate_condition_result(condition.condition, context)
        return None if result is None else not result

    actual = _resolve_fact(context, condition.fact)
    expected = condition.value
    if condition.operator == "exists":
        return actual is not _MISSING and actual is not None
    if actual is _MISSING or actual is None:
        return None
    if condition.operator == "eq":
        return type(actual) is type(expected) and actual == expected
    if condition.operator == "ne":
        return type(actual) is type(expected) and actual != expected
    if condition.operator == "in":
        return isinstance(expected, list) and any(
            type(actual) is type(item) and actual == item for item in expected
        )
    if condition.operator == "not_in":
        return isinstance(expected, list) and all(
            type(actual) is not type(item) or actual != item for item in expected
        )
    if condition.operator == "matches":
        if (
            not isinstance(actual, str)
            or len(actual) > 512
            or not isinstance(expected, str)
            or not is_safe_pattern(expected)
        ):
            return False
        return re.fullmatch(expected, actual) is not None
    try:
        if condition.operator == "lt":
            return actual < expected
        if condition.operator == "lte":
            return actual <= expected
        if condition.operator == "gt":
            return actual > expected
        if condition.operator == "gte":
            return actual >= expected
    except TypeError:
        return False
    return False


def condition_has_missing_data(condition: Condition, context: Mapping[str, Any]) -> bool:
    """Identify whether a failed condition references a fact that is absent or unresolved."""
    if isinstance(condition, (AllCondition, AnyCondition)):
        return any(condition_has_missing_data(child, context) for child in condition.conditions)
    if isinstance(condition, NotCondition):
        return condition_has_missing_data(condition.condition, context)
    actual = _resolve_fact(context, condition.fact)
    return actual is _MISSING or actual is None or actual == ""
