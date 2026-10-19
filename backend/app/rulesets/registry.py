"""Built-in, typed registry for the initial reusable contest-rule catalog."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from backend.app.rulesets.schema import (
    BonusRule,
    CategoryRule,
    DistancePointsRule,
    DuplicateRule,
    EligibilityRule,
    ExchangeRule,
    FormatMappingRule,
    MultiplierRule,
    OperatingConstraintRule,
    PenaltyRule,
    PointRule,
    ScoreFormulaRule,
    SubmissionRule,
    WorkflowHookRule,
)
from backend.app.rulesets.validation import REQUIRED_RULE_TYPES


@dataclass(frozen=True)
class RuleType:
    key: str
    label: str
    description: str
    execution: str
    model: type[BaseModel]


RULE_TYPES: tuple[RuleType, ...] = (
    RuleType(
        "submission",
        "Log submission",
        "Choose how late submissions are classified after the contest-level cutoff.",
        "automatic",
        SubmissionRule,
    ),
    RuleType(
        "categories",
        "Categories",
        "Define category dimensions, choices, and compatibility.",
        "automatic",
        CategoryRule,
    ),
    RuleType(
        "exchange",
        "Exchange schema",
        "Define ordered exchange fields and validation.",
        "automatic",
        ExchangeRule,
    ),
    RuleType(
        "eligibility",
        "QSO eligibility",
        "Check bands, modes, contact geography, entry categories/declarations, "
        "and the station callsign.",
        "automatic",
        EligibilityRule,
    ),
    RuleType(
        "duplicates",
        "Duplicate scope",
        "Configure duplicate identity and consequence, including optional multiplier credit.",
        "automatic",
        DuplicateRule,
    ),
    RuleType(
        "points",
        "QSO points",
        "Assign integer point values from supported QSO facts.",
        "automatic",
        PointRule,
    ),
    RuleType(
        "distance_points",
        "Distance points",
        "Award integer points from entrant and received Maidenhead locators.",
        "automatic",
        DistancePointsRule,
    ),
    RuleType(
        "multiplier",
        "Multiplier",
        "Define multiplier source, eligibility, and uniqueness scope.",
        "automatic",
        MultiplierRule,
    ),
    RuleType(
        "bonus",
        "Bonus",
        "Award capped integer bonus points with evidence rules.",
        "declaration",
        BonusRule,
    ),
    RuleType(
        "penalty",
        "Penalty",
        "Apply configured integer consequences to rule violations.",
        "automatic_or_review",
        PenaltyRule,
    ),
    RuleType(
        "score_formula",
        "Score formula",
        "Compose the final score using explicit integer operations.",
        "automatic",
        ScoreFormulaRule,
    ),
    RuleType(
        "operating_constraints",
        "Operating constraints",
        "Check operating/off time and station limitations.",
        "automatic_or_review",
        OperatingConstraintRule,
    ),
    RuleType(
        "format_mapping",
        "Format mapping",
        "Map log headers, QSO fields, and external categories.",
        "boundary_adapter",
        FormatMappingRule,
    ),
    RuleType(
        "workflow_hook",
        "Workflow hook",
        "Declare cross-log, adjudication, publication, or award work.",
        "automatic_or_declaration_or_review",
        WorkflowHookRule,
    ),
)

RULE_TYPE_BY_KEY = {rule_type.key: rule_type for rule_type in RULE_TYPES}


def rule_catalog() -> list[dict[str, object]]:
    return [
        {
            "key": rule_type.key,
            "label": rule_type.label,
            "description": rule_type.description,
            "execution": rule_type.execution,
            "required": rule_type.key in REQUIRED_RULE_TYPES,
            "schema": rule_type.model.model_json_schema(),
        }
        for rule_type in RULE_TYPES
    ]
