"""Cross-rule validation and safe declarative-condition checks."""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import ValidationError

from backend.app.logs.cabrillo import DEFAULT_QSO_COLUMNS
from backend.app.rulesets.conditions import is_safe_pattern
from backend.app.rulesets.schema import (
    AllCondition,
    AnyCondition,
    CompareCondition,
    Condition,
    ConfiguredRule,
    NotCondition,
    RulesetDefinition,
    rule_types_in,
)

REQUIRED_RULE_TYPES = frozenset(
    {
        "submission",
        "categories",
        "exchange",
        "eligibility",
        "duplicates",
        "points",
        "score_formula",
        "format_mapping",
    }
)


class RulesetValidationError(ValueError):
    def __init__(self, errors: list[dict[str, object]]) -> None:
        self.errors = errors
        super().__init__("Ruleset configuration is invalid")


def _all_conditions(
    rules: Iterable[ConfiguredRule],
) -> Iterable[tuple[int, str, Condition]]:
    for index, configured in enumerate(rules):
        if configured.when is not None:
            yield index, f"rules[{index}].when", configured.when
        if configured.rule.kind == "eligibility" and configured.rule.eligible_if is not None:
            yield index, f"rules[{index}].rule.eligible_if", configured.rule.eligible_if


def _condition_depth(condition: Condition) -> int:
    if isinstance(condition, (CompareCondition,)):
        return 1
    if isinstance(condition, NotCondition):
        return 1 + _condition_depth(condition.condition)
    if isinstance(condition, (AllCondition, AnyCondition)):
        return 1 + max(_condition_depth(item) for item in condition.conditions)
    return 1


def _walk_conditions(condition: Condition) -> Iterable[CompareCondition]:
    if isinstance(condition, CompareCondition):
        yield condition
    elif isinstance(condition, NotCondition):
        yield from _walk_conditions(condition.condition)
    elif isinstance(condition, (AllCondition, AnyCondition)):
        for child in condition.conditions:
            yield from _walk_conditions(child)


def _condition_errors(definition: RulesetDefinition) -> list[dict[str, object]]:
    errors: list[dict[str, object]] = []
    for _index, path, condition in _all_conditions(definition.rules):
        if _condition_depth(condition) > 8:
            errors.append({"path": path, "message": "Condition nesting exceeds 8 levels."})
        for comparison in _walk_conditions(condition):
            if comparison.operator in {"in", "not_in"} and not isinstance(comparison.value, list):
                errors.append(
                    {
                        "path": path,
                        "message": "in/not_in comparisons require a list value.",
                    }
                )
            if comparison.operator == "matches":
                if not isinstance(comparison.value, str) or not is_safe_pattern(comparison.value):
                    errors.append(
                        {
                            "path": path,
                            "message": "matches requires a valid pattern in the supported "
                            "safe subset.",
                        }
                    )
    return errors


def _cross_reference_errors(
    definition: RulesetDefinition, *, check_import_mapping_consistency: bool
) -> list[dict[str, object]]:
    errors: list[dict[str, object]] = []
    rules = [item.rule for item in definition.rules]
    kinds = [rule.kind for rule in rules]
    missing = sorted(REQUIRED_RULE_TYPES - set(kinds))
    if missing:
        errors.append(
            {"path": "rules", "message": "Missing required rule types: " + ", ".join(missing)}
        )
    if kinds.count("score_formula") != 1:
        errors.append(
            {"path": "rules", "message": "A ruleset must define exactly one score_formula."}
        )
    if kinds.count("submission") > 1:
        errors.append(
            {
                "path": "rules",
                "message": "A ruleset may define only one submission rule.",
            }
        )
    for singleton in ("categories",):
        if kinds.count(singleton) != 1:
            errors.append(
                {"path": "rules", "message": f"A ruleset must define exactly one {singleton} rule."}
            )
    if kinds.count("format_mapping") == 0:
        errors.append(
            {"path": "rules", "message": "A ruleset must define at least one format_mapping rule."}
        )
    else:
        formats = [rule.format for rule in rules if rule.kind == "format_mapping"]
        if len(formats) != len(set(formats)):
            errors.append(
                {"path": "rules", "message": "A ruleset may define each import format only once."}
            )
    for index, configured in enumerate(definition.rules):
        if (
            configured.rule.kind in {"submission", "categories", "format_mapping", "score_formula"}
            and configured.when is not None
        ):
            errors.append(
                {
                    "path": f"rules[{index}].when",
                    "message": f"{configured.rule.kind} rules cannot be conditional.",
                }
            )

    category_dimensions = {
        dimension.key: {choice.key for choice in dimension.choices}
        for rule in rules
        if rule.kind == "categories"
        for dimension in rule.dimensions
    }
    exchange_fields = {
        field.key: field for rule in rules if rule.kind == "exchange" for field in rule.fields
    }
    for index, rule in enumerate(rules):
        if (
            rule.kind == "points"
            and rule.fact == "exchange"
            and rule.exchange_field not in exchange_fields
        ):
            errors.append(
                {
                    "path": f"rules[{index}].exchange_field",
                    "message": "Point rule references an undefined exchange field.",
                }
            )
        elif rule.kind == "points" and rule.fact == "exchange":
            field = exchange_fields.get(rule.exchange_field or "")
            if field is not None and field.direction not in {"received", "both"}:
                errors.append(
                    {
                        "path": f"rules[{index}].exchange_field",
                        "message": "Point rules can reference only received exchange fields.",
                    }
                )
        elif rule.kind == "multiplier":
            parts = rule.source_fact.split(".")
            valid_qso = (
                len(parts) == 2
                and parts[0] == "qso"
                and parts[1]
                in {
                    "id",
                    "occurred_at",
                    "worked_callsign",
                    "band",
                    "mode",
                    "grid",
                    "transmitter",
                    "continent",
                    "entity",
                    "cq_zone",
                    "itu_zone",
                }
            )
            valid_entry = (
                len(parts) == 2 and parts[0] == "entry" and parts[1] in {"id", "power_multiplier"}
            ) or (
                len(parts) == 3
                and parts[0] == "entry"
                and parts[1] in {"categories", "declarations"}
                and parts[2]
                in (
                    category_dimensions
                    if parts[1] == "categories"
                    else {
                        field.key
                        for r in rules
                        if r.kind == "exchange"
                        for field in r.fields
                        if field.direction == "entry"
                    }
                )
            )
            valid_exchange = False
            if parts[0] == "exchange" and len(parts) == 2:
                field = exchange_fields.get(parts[1])
                valid_exchange = field is not None and field.direction in {"received", "both"}
            elif (
                parts[0] == "exchange"
                and len(parts) == 3
                and parts[1] in {"sent", "received", "entry"}
            ):
                field = exchange_fields.get(parts[2])
                valid_exchange = field is not None and field.direction in {parts[1], "both"}
            if not (valid_qso or valid_entry or valid_exchange):
                errors.append(
                    {
                        "path": f"rules[{index}].source_fact",
                        "message": "Multiplier references an unsupported or undefined fact.",
                    }
                )
        elif rule.kind == "format_mapping":
            if check_import_mapping_consistency:
                if rule.format == "cabrillo" and rule.qso_columns:
                    configured_columns = tuple(rule.qso_columns)
                    if configured_columns != DEFAULT_QSO_COLUMNS:
                        errors.append(
                            {
                                "path": f"rules[{index}].qso_columns",
                                "message": (
                                    "Cabrillo QSO fields must follow the WWROF-defined field "
                                    "order: " + ", ".join(DEFAULT_QSO_COLUMNS) + "."
                                ),
                            }
                        )

                mapped_dimensions = {
                    dimension_key
                    for mapping in rule.category_mappings
                    for dimension_key in mapping.category_values
                }
                required_dimensions = {
                    dimension.key
                    for category_rule in rules
                    if category_rule.kind == "categories"
                    for dimension in category_rule.dimensions
                    if dimension.required
                }
                unmapped_required = sorted(required_dimensions - mapped_dimensions)
                if unmapped_required:
                    errors.append(
                        {
                            "path": f"rules[{index}].category_mappings",
                            "message": (
                                f"The {rule.format} format does not map required category "
                                "dimension(s): " + ", ".join(unmapped_required) + "."
                            ),
                        }
                    )
            for mapping_index, mapping in enumerate(rule.category_mappings):
                for dimension_key, choice_key in mapping.category_values.items():
                    if (
                        dimension_key not in category_dimensions
                        or choice_key not in category_dimensions[dimension_key]
                    ):
                        errors.append(
                            {
                                "path": f"rules[{index}].category_mappings[{mapping_index}]",
                                "message": f"Unknown category value {dimension_key}={choice_key}.",
                            }
                        )
    return errors


def _condition_reference_errors(definition: RulesetDefinition) -> list[dict[str, object]]:
    category_keys = {
        dimension.key
        for configured in definition.rules
        if configured.rule.kind == "categories"
        for dimension in configured.rule.dimensions
    }
    declaration_keys = {
        field.key
        for configured in definition.rules
        if configured.rule.kind == "exchange"
        for field in configured.rule.fields
        if field.direction == "entry"
    }
    exchange_keys = {
        field.key
        for configured in definition.rules
        if configured.rule.kind == "exchange"
        for field in configured.rule.fields
    }
    qso_fields = {
        "id",
        "occurred_at",
        "worked_callsign",
        "band",
        "mode",
        "grid",
        "transmitter",
        "continent",
        "entity",
        "cq_zone",
        "itu_zone",
        "exchange_sent",
        "exchange_received",
    }
    errors: list[dict[str, object]] = []
    for _rule_index, path, condition in _all_conditions(definition.rules):
        for comparison in _walk_conditions(condition):
            parts = comparison.fact.split(".")
            valid = (
                (len(parts) == 2 and parts[0] == "qso" and parts[1] in qso_fields)
                or (len(parts) == 2 and parts[0] == "station" and parts[1] == "callsign")
                or (
                    len(parts) == 3
                    and parts[0] == "entry"
                    and parts[1] == "categories"
                    and parts[2] in category_keys
                )
                or (
                    len(parts) == 3
                    and parts[0] == "entry"
                    and parts[1] == "declarations"
                    and parts[2] in declaration_keys
                )
                or (
                    len(parts) == 2
                    and parts[0] == "entry"
                    and parts[1] in {"id", "power_multiplier"}
                )
                or (len(parts) == 2 and parts[0] == "exchange" and parts[1] in exchange_keys)
                or (
                    len(parts) == 3
                    and parts[0] == "exchange"
                    and parts[1] in {"sent", "received", "entry"}
                    and parts[2] in exchange_keys
                )
            )
            if not valid:
                errors.append(
                    {
                        "path": path,
                        "message": f"Condition references unsupported fact {comparison.fact}.",
                    }
                )
    return errors


def validate_ruleset(
    payload: object, *, check_import_mapping_consistency: bool = True
) -> RulesetDefinition:
    """Parse a strict ruleset document and enforce system-level cross-rule invariants."""
    try:
        definition = RulesetDefinition.model_validate(payload)
    except ValidationError as exc:
        errors = [
            {"path": ".".join(str(part) for part in detail["loc"]), "message": detail["msg"]}
            for detail in exc.errors()
        ]
        raise RulesetValidationError(errors) from exc
    errors = (
        _condition_errors(definition)
        + _cross_reference_errors(
            definition, check_import_mapping_consistency=check_import_mapping_consistency
        )
        + _condition_reference_errors(definition)
    )
    if errors:
        raise RulesetValidationError(errors)
    return definition


def configured_rule_types(definition: RulesetDefinition) -> list[str]:
    return rule_types_in(definition)
