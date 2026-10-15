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
    """Evaluate a typed predicate against plain mapping data."""
    if isinstance(condition, AllCondition):
        return all(evaluate_condition(child, context) for child in condition.conditions)
    if isinstance(condition, AnyCondition):
        return any(evaluate_condition(child, context) for child in condition.conditions)
    if isinstance(condition, NotCondition):
        return not evaluate_condition(condition.condition, context)

    actual = _resolve_fact(context, condition.fact)
    expected = condition.value
    if condition.operator == "exists":
        return actual is not _MISSING and actual is not None
    if actual is _MISSING:
        return False
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
