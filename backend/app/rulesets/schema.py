"""Typed, declarative ruleset configuration accepted by the rules engine."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    StringConstraints,
    model_validator,
)

RuleId = Annotated[
    str, StringConstraints(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_.-]*$")
]
Identifier = Annotated[
    str,
    StringConstraints(min_length=1, max_length=120, pattern=r"^[a-z][a-z0-9_.-]*$"),
]
Integer = Annotated[int, Field(strict=True)]
NonNegativeInteger = Annotated[int, Field(strict=True, ge=0)]
PositiveInteger = Annotated[int, Field(strict=True, ge=1)]
ConditionValue = (
    StrictStr | StrictInt | StrictBool | None | list[StrictStr | StrictInt | StrictBool]
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class CompareCondition(StrictModel):
    kind: Literal["compare"]
    fact: Annotated[
        str,
        StringConstraints(
            min_length=1,
            max_length=160,
            pattern=r"^(qso|entry|station|exchange)(\.[a-zA-Z0-9_-]+)+$",
        ),
    ]
    operator: Literal["eq", "ne", "in", "not_in", "lt", "lte", "gt", "gte", "matches", "exists"]
    value: ConditionValue = None


class AllCondition(StrictModel):
    kind: Literal["all"]
    conditions: list[Condition] = Field(min_length=1, max_length=32)


class AnyCondition(StrictModel):
    kind: Literal["any"]
    conditions: list[Condition] = Field(min_length=1, max_length=32)


class NotCondition(StrictModel):
    kind: Literal["not"]
    condition: Condition


Condition = Annotated[
    CompareCondition | AllCondition | AnyCondition | NotCondition, Field(discriminator="kind")
]
AllCondition.model_rebuild(_types_namespace={"Condition": Condition})
AnyCondition.model_rebuild(_types_namespace={"Condition": Condition})
NotCondition.model_rebuild(_types_namespace={"Condition": Condition})


class SubmissionRule(StrictModel):
    kind: Literal["submission"]
    late_policy: Literal["reject", "accept_late", "checklog"] = Field(
        description=(
            "How a submission after the cutoff is classified. A manager extension is "
            "separately controlled below."
        )
    )
    manager_extension_allowed: bool = Field(
        default=False,
        description="Whether a contest manager may explicitly extend the configured cutoff.",
    )


class CategoryChoice(StrictModel):
    key: Identifier
    label: Annotated[str, StringConstraints(min_length=1, max_length=160)]
    description: Annotated[str, StringConstraints(max_length=600)] | None = Field(
        default=None,
        description="Optional contest-specific explanation of this category choice.",
    )
    requires_declaration: bool = False


class CategoryDimension(StrictModel):
    key: Identifier = Field(
        description=(
            "Stable identifier for this entry-classification dimension, such as operator or power."
        )
    )
    label: Annotated[str, StringConstraints(min_length=1, max_length=160)] = Field(
        description=(
            "Human-readable name shown to participants; changing it does not change the stable key."
        )
    )
    description: Annotated[str, StringConstraints(max_length=800)] | None = Field(
        default=None,
        description=(
            "Optional explanation of this classification dimension, including any "
            "contest-specific limits or definitions."
        ),
    )
    required: bool = True
    choices: list[CategoryChoice] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def unique_choice_keys(self) -> CategoryDimension:
        if len({choice.key for choice in self.choices}) != len(self.choices):
            raise ValueError("category choice keys must be unique within a dimension")
        return self


class CategoryRule(StrictModel):
    kind: Literal["categories"]
    dimensions: list[CategoryDimension] = Field(
        min_length=1,
        max_length=40,
        description=(
            "Each dimension is one classification axis (for example operator, power, "
            "or band); choices are the values allowed on that axis."
        ),
    )
    mutually_exclusive: list[list[Identifier]] = Field(
        default_factory=list,
        max_length=40,
        description="Groups of dimension keys that cannot be configured together.",
    )

    @model_validator(mode="after")
    def validate_dimensions(self) -> CategoryRule:
        keys = {dimension.key for dimension in self.dimensions}
        if len(keys) != len(self.dimensions):
            raise ValueError("category dimension keys must be unique")
        for group in self.mutually_exclusive:
            if len(group) < 2 or len(set(group)) != len(group) or not set(group) <= keys:
                raise ValueError("mutually exclusive groups need distinct known dimension keys")
        return self


class ExchangeField(StrictModel):
    key: Identifier = Field(
        description="Stable key used to store and reference this exchange value."
    )
    label: Annotated[str, StringConstraints(min_length=1, max_length=160)] = Field(
        description="Human-readable field name; editing the label does not change the key."
    )
    value_type: Literal["text", "integer", "callsign", "serial", "enum", "grid", "zone"] = Field(
        description="Validation type for the submitted exchange value."
    )
    direction: Literal["sent", "received", "both", "entry"] = Field(
        default="both",
        description=(
            "Whether this value is sent, received, exchanged both ways, or declared "
            "once for the entry."
        ),
    )
    required: bool = True
    pattern: Annotated[str, StringConstraints(max_length=256)] | None = None
    max_length: Annotated[int, Field(strict=True, ge=1, le=2048)] = 256
    choices: list[Annotated[str, StringConstraints(min_length=1, max_length=120)]] = Field(
        default_factory=list, max_length=500
    )
    min_integer: Integer | None = None
    max_integer: Integer | None = None
    serial_scope: Literal["entry", "band", "mode", "transmitter"] | None = None

    @model_validator(mode="after")
    def validate_field(self) -> ExchangeField:
        standard_types = {
            "rst": ("text", {"sent", "received", "both"}),
            "serial": ("serial", {"sent", "received", "both"}),
            "cq_zone": ("zone", {"received", "both"}),
            "itu_zone": ("zone", {"received", "both"}),
            "section": ("text", {"received", "both", "entry"}),
            "grid": ("grid", {"received", "both"}),
            "state": ("text", {"received", "both", "entry"}),
            "province": ("text", {"received", "both", "entry"}),
            "check": ("integer", {"received", "both", "entry"}),
            "precedence": ("enum", {"received", "both", "entry"}),
            "call_area": ("text", {"received", "both", "entry"}),
            "power": ("enum", {"received", "both", "entry"}),
        }
        if self.key in standard_types:
            expected_type, allowed_directions = standard_types[self.key]
            if self.value_type != expected_type or self.direction not in allowed_directions:
                raise ValueError(
                    f"standard exchange field {self.key} requires type {expected_type} "
                    f"and direction in {sorted(allowed_directions)}"
                )
        if self.value_type == "enum" and not self.choices:
            raise ValueError("enum exchange fields require choices")
        if self.value_type != "enum" and self.choices:
            raise ValueError("choices are supported only for enum exchange fields")
        if self.min_integer is not None and self.max_integer is not None:
            if self.min_integer > self.max_integer:
                raise ValueError("min_integer cannot exceed max_integer")
        if self.value_type == "serial" and self.serial_scope is None:
            raise ValueError("serial fields require a serial_scope")
        return self


class ExchangeRule(StrictModel):
    kind: Literal["exchange"]
    fields: list[ExchangeField] = Field(
        min_length=1,
        max_length=80,
        description="Ordered fields that make up the contest exchange and their validation rules.",
    )

    @model_validator(mode="after")
    def unique_fields(self) -> ExchangeRule:
        if len({item.key for item in self.fields}) != len(self.fields):
            raise ValueError("exchange field keys must be unique")
        return self


class EligibilityRule(StrictModel):
    kind: Literal["eligibility"]
    eligible_if: Condition | None = None
    allowed_bands: list[str] = Field(
        default_factory=list,
        max_length=100,
        description=(
            "When non-empty, only these catalog bands are eligible. An empty list "
            "means no band restriction."
        ),
    )
    allowed_modes: list[str] = Field(
        default_factory=list,
        max_length=100,
        description=(
            "When non-empty, only these catalog modes are eligible. An empty list "
            "means no mode restriction."
        ),
    )
    reject_self_contacts: bool = True
    reject_out_of_period: bool = True
    reject_missing_required_exchange: bool = True
    action: Literal["not_credited", "needs_review"] = "not_credited"


class DuplicateRule(StrictModel):
    kind: Literal["duplicates"]
    scope: list[Literal["worked_callsign", "band", "mode", "grid", "transmitter"]] = Field(
        min_length=1, max_length=5
    )
    effect: Literal["ignore", "not_credited", "penalty", "needs_review"]
    penalty_points: NonNegativeInteger = 0
    count_for_multipliers: bool = Field(
        default=False,
        description=(
            "Whether a duplicate contact that otherwise passes eligibility may supply "
            "multiplier credit while still receiving no QSO points."
        ),
    )

    @model_validator(mode="after")
    def penalty_requires_points(self) -> DuplicateRule:
        if "worked_callsign" not in self.scope:
            raise ValueError("duplicate scope must include worked_callsign")
        if self.effect == "penalty" and self.penalty_points <= 0:
            raise ValueError("duplicate penalty requires positive integer penalty_points")
        if self.effect != "penalty" and self.penalty_points:
            raise ValueError("penalty_points is valid only when effect is penalty")
        return self


class PointRule(StrictModel):
    kind: Literal["points"]
    fact: Literal["fixed", "band", "mode", "continent", "entity", "cq_zone", "itu_zone", "exchange"]
    fixed_points: NonNegativeInteger | None = None
    exchange_field: Identifier | None = None
    values: dict[str, NonNegativeInteger] = Field(default_factory=dict, max_length=500)
    default_points: NonNegativeInteger | None = None

    @model_validator(mode="after")
    def validate_points_source(self) -> PointRule:
        if self.fact == "fixed":
            if self.fixed_points is None or self.values or self.exchange_field is not None:
                raise ValueError("fixed point rules require only fixed_points")
        else:
            if self.fixed_points is not None or not self.values:
                raise ValueError("lookup point rules require values and cannot set fixed_points")
        if (self.fact == "exchange") != (self.exchange_field is not None):
            raise ValueError("exchange point rules require exchange_field")
        return self


class MultiplierRule(StrictModel):
    kind: Literal["multiplier"]
    source_fact: Annotated[
        str,
        StringConstraints(
            min_length=1,
            max_length=160,
            pattern=r"^(qso|entry|exchange)(\.[a-zA-Z0-9_-]+)+$",
        ),
    ]
    scope: Literal["contest", "band", "mode", "band_mode", "grid", "transmitter"]
    label: Annotated[str, StringConstraints(min_length=1, max_length=160)]


class BonusRule(StrictModel):
    kind: Literal["bonus"]
    basis: Literal["per_eligible_qso", "per_entry"]
    points: PositiveInteger
    cap: NonNegativeInteger | None = None
    minimum_eligible_qsos: NonNegativeInteger = 0
    evidence_key: Identifier | None = Field(
        default=None,
        description=(
            "When set, award this bonus only when the entry includes the named evidence "
            "declaration. Its presence enables the evidence requirement."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_evidence_flag(cls, value: Any) -> Any:
        """Accept and discard the v1 field that duplicated evidence_key presence."""
        if not isinstance(value, dict) or "evidence_required" not in value:
            return value
        normalized = dict(value)
        legacy_required = normalized.pop("evidence_required")
        evidence_key = normalized.get("evidence_key")
        if type(legacy_required) is not bool:
            raise ValueError("legacy evidence_required must be a boolean")
        if legacy_required != (evidence_key is not None):
            raise ValueError("legacy evidence_required must agree with evidence_key presence")
        return normalized


class PenaltyRule(StrictModel):
    kind: Literal["penalty"]
    reason_code: Identifier
    action: Literal["remove_contact", "deduct_points", "reclassify", "disqualify", "needs_review"]
    points: NonNegativeInteger = 0
    maximum_occurrences: PositiveInteger = 1

    @model_validator(mode="after")
    def validate_action(self) -> PenaltyRule:
        if self.action == "deduct_points" and self.points == 0:
            raise ValueError("deduct_points requires positive integer points")
        if self.action != "deduct_points" and self.points:
            raise ValueError("points are supported only for deduct_points")
        return self


class ScoreOperand(StrictModel):
    variable: (
        Literal[
            "points_total", "multiplier_count", "bonus_points", "penalty_points", "power_multiplier"
        ]
        | None
    ) = None
    constant: Integer | None = None

    @model_validator(mode="after")
    def exactly_one_source(self) -> ScoreOperand:
        if (self.variable is None) == (self.constant is None):
            raise ValueError("score operand requires exactly one of variable or constant")
        return self


class ScoreStep(StrictModel):
    operator: Literal["add", "subtract", "multiply", "floor_divide", "round_divide"]
    operand: ScoreOperand
    rounding: Literal["half_up", "half_even", "floor", "ceiling"] | None = None

    @model_validator(mode="after")
    def validate_division_rounding(self) -> ScoreStep:
        if self.operator == "round_divide" and self.rounding is None:
            raise ValueError("round_divide requires an explicit rounding rule")
        if self.operator != "round_divide" and self.rounding is not None:
            raise ValueError("rounding is only valid for round_divide")
        if self.operand.constant == 0 and self.operator in {"floor_divide", "round_divide"}:
            raise ValueError("division by zero is not allowed")
        return self


class ScoreFormulaRule(StrictModel):
    kind: Literal["score_formula"]
    start: ScoreOperand
    steps: list[ScoreStep] = Field(default_factory=list, max_length=32)


class OperatingConstraintRule(StrictModel):
    kind: Literal["operating_constraints"]
    max_operating_minutes: PositiveInteger | None = None
    operating_session_gap_minutes: PositiveInteger | None = None
    minimum_off_time_minutes: NonNegativeInteger = 0
    required_off_periods: NonNegativeInteger = 0
    off_period_gap_minutes: PositiveInteger | None = None
    maximum_band_changes: NonNegativeInteger | None = None
    band_change_window_minutes: PositiveInteger = 60
    minimum_band_dwell_minutes: NonNegativeInteger | None = None
    maximum_transmitters: PositiveInteger | None = None
    one_transmitted_signal_per_band: bool = False
    declaration_fields: list[Identifier] = Field(default_factory=list, max_length=80)

    @model_validator(mode="after")
    def validate_operating_time(self) -> OperatingConstraintRule:
        if self.max_operating_minutes and self.operating_session_gap_minutes is None:
            raise ValueError(
                "maximum operating time needs an operating_session_gap_minutes threshold"
            )
        if (
            self.minimum_off_time_minutes or self.required_off_periods
        ) and self.off_period_gap_minutes is None:
            raise ValueError("off-time rules need an off_period_gap_minutes threshold")
        return self


class CategoryMapping(StrictModel):
    external_value: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    category_values: dict[Identifier, Identifier] = Field(min_length=1, max_length=40)


class FormatMappingRule(StrictModel):
    kind: Literal["format_mapping"]
    format: Literal["cabrillo", "adif", "csv", "native"]
    category_mappings: list[CategoryMapping] = Field(default_factory=list, max_length=500)
    header_fields: dict[Identifier, str] = Field(default_factory=dict, max_length=100)
    qso_columns: list[Identifier] = Field(default_factory=list, max_length=100)
    preserve_unknown_fields: bool = True

    @model_validator(mode="after")
    def unique_external_categories(self) -> FormatMappingRule:
        keys = [mapping.external_value.casefold() for mapping in self.category_mappings]
        if len(keys) != len(set(keys)):
            raise ValueError("external category mappings must be unique, case-insensitively")
        return self


class WorkflowHookRule(StrictModel):
    kind: Literal["workflow_hook"]
    stage: Literal["cross_log", "adjudication", "publication", "award"]
    key: Identifier
    execution: Literal["automatic", "declaration", "human_review"]
    parameters: dict[
        Identifier,
        StrictStr
        | StrictInt
        | StrictBool
        | None
        | list[StrictStr | StrictInt | StrictBool]
        | dict[Identifier, StrictInt],
    ] = Field(default_factory=dict, max_length=80)

    @model_validator(mode="after")
    def validate_publication_policy(self) -> WorkflowHookRule:
        if self.stage != "publication":
            return self
        supported = {
            "include_late",
            "include_checklog",
            "include_needs_review",
            "include_reclassified",
            "include_disqualified",
        }
        unknown = set(self.parameters) - supported
        if unknown:
            raise ValueError(
                "publication workflow hook has unsupported visibility settings: "
                + ", ".join(sorted(unknown))
            )
        if any(type(value) is not bool for value in self.parameters.values()):
            raise ValueError("publication visibility settings must be booleans")
        return self


RuleDefinition = Annotated[
    SubmissionRule
    | CategoryRule
    | ExchangeRule
    | EligibilityRule
    | DuplicateRule
    | PointRule
    | MultiplierRule
    | BonusRule
    | PenaltyRule
    | ScoreFormulaRule
    | OperatingConstraintRule
    | FormatMappingRule
    | WorkflowHookRule,
    Field(discriminator="kind"),
]


class ConfiguredRule(StrictModel):
    id: RuleId
    rule: RuleDefinition
    when: Condition | None = None


class RulesetDefinition(StrictModel):
    schema_version: Literal[2] = 2
    ruleset_key: Annotated[
        str,
        StringConstraints(min_length=1, max_length=120, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$"),
    ]
    version: Annotated[
        str,
        StringConstraints(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.+-]*$"),
    ]
    source_url: AnyHttpUrl | None = None
    source_edition: Annotated[str, StringConstraints(max_length=120)] | None = None
    rules: list[ConfiguredRule] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def unique_rule_ids(self) -> RulesetDefinition:
        ids = [rule.id for rule in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("configured rule ids must be unique")
        return self


def rule_types_in(definition: RulesetDefinition) -> list[str]:
    return sorted({configured.rule.kind for configured in definition.rules})
