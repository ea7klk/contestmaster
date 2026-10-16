"""Readable ruleset summaries and deterministic integer formula examples."""

from __future__ import annotations

from backend.app.rulesets.engine import RuleExecutionError, evaluate_score_step
from backend.app.rulesets.schema import (
    RulesetDefinition,
    ScoreFormulaRule,
    rule_types_in,
)

EXAMPLE_VARIABLES = {
    "points_total": 120,
    "multiplier_count": 8,
    "bonus_points": 10,
    "penalty_points": 5,
    "power_multiplier": 2,
}


def summarize_ruleset(definition: RulesetDefinition) -> str:
    """Describe configured rules and their source in a stable, human-readable form."""
    source = f" Source: {definition.source_url}" if definition.source_url else ""
    edition = f" ({definition.source_edition})" if definition.source_edition else ""
    lines = [f"{definition.ruleset_key} version {definition.version}{edition}.{source}"]
    for configured in definition.rules:
        rule = configured.rule
        condition = " [conditional]" if configured.when is not None else ""
        if rule.kind == "submission":
            summary = f"Late submission policy {rule.late_policy}"
        elif rule.kind == "categories":
            dimensions = ", ".join(
                f"{dimension.label}: {', '.join(choice.label for choice in dimension.choices)}"
                for dimension in rule.dimensions
            )
            summary = f"Categories: {dimensions}"
        elif rule.kind == "exchange":
            fields = ", ".join(f"{field.label} ({field.value_type})" for field in rule.fields)
            summary = f"Exchange fields: {fields}"
        elif rule.kind == "duplicates":
            summary = f"Duplicate scope {', '.join(rule.scope)}; effect {rule.effect}"
        elif rule.kind == "points":
            summary = f"Integer points from {rule.fact}"
        elif rule.kind == "multiplier":
            summary = f"Multiplier from {rule.source_fact}, unique {rule.scope}"
        elif rule.kind == "score_formula":
            summary = f"Integer score formula with {len(rule.steps)} ordered operations"
        elif rule.kind == "operating_constraints":
            summary = "Operating and station limits; unverifiable conditions require review"
        elif rule.kind == "workflow_hook":
            summary = f"{rule.stage} hook {rule.key} ({rule.execution})"
        elif rule.kind == "format_mapping":
            summary = (
                f"{rule.format.upper()} mapping; preserve unknown fields: "
                f"{rule.preserve_unknown_fields}"
            )
        elif rule.kind == "eligibility":
            summary = (
                f"QSO eligibility; {len(rule.allowed_bands)} band and "
                f"{len(rule.allowed_modes)} mode limits"
            )
        elif rule.kind == "bonus":
            summary = f"Bonus: {rule.points} integer points ({rule.basis})"
        elif rule.kind == "penalty":
            summary = f"Penalty {rule.reason_code}: {rule.action}"
        else:
            summary = rule.kind
        lines.append(f"- {configured.id}: {summary}{condition}.")
    return "\n".join(lines)


def worked_score_example(
    definition: RulesetDefinition,
    variables: dict[str, int] | None = None,
) -> dict[str, object]:
    """Apply the configured formula left to right to an integer example input."""
    formula = next(
        (
            configured.rule
            for configured in definition.rules
            if configured.rule.kind == "score_formula"
        ),
        None,
    )
    if not isinstance(formula, ScoreFormulaRule):
        raise RuleExecutionError("Ruleset has no score formula to preview")
    values = dict(EXAMPLE_VARIABLES if variables is None else variables)
    if any(type(value) is not int for value in values.values()):
        raise RuleExecutionError("Worked examples accept integer values only")
    current = formula.start.constant
    if current is None:
        current = values.get(formula.start.variable or "")
    if current is None:
        raise RuleExecutionError(f"Missing example value for {formula.start.variable}")
    steps: list[dict[str, int | str]] = [{"operation": "start", "result": current}]
    for index, step in enumerate(formula.steps, start=1):
        operand = step.operand.constant
        if operand is None:
            operand = values.get(step.operand.variable or "")
        if operand is None:
            raise RuleExecutionError(f"Missing example value for {step.operand.variable}")
        current = evaluate_score_step(current, step, values)
        steps.append(
            {
                "operation": f"{index}: {step.operator} {operand}",
                "result": current,
            }
        )
    if current < 0:
        raise RuleExecutionError("Worked example produced a negative final score")
    return {"variables": values, "steps": steps, "final_score": current}


def validation_report(definition: RulesetDefinition) -> dict[str, object]:
    try:
        example = worked_score_example(definition)
    except RuleExecutionError as exc:
        example = {"error": str(exc)}
    return {
        "valid": True,
        "ruleset_key": definition.ruleset_key,
        "version": definition.version,
        "rule_types": rule_types_in(definition),
        "summary": summarize_ruleset(definition),
        "worked_score_example": example,
    }
