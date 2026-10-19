"""Deterministic integer-only QSO eligibility, duplicate, multiplier, and score engine."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from backend.app.rulesets.call_signs import callsign_suffix, wpx_prefix_for_callsign
from backend.app.rulesets.checks import validate_categories, validate_exchange
from backend.app.rulesets.conditions import (
    condition_has_missing_data,
    evaluate_condition,
    evaluate_condition_result,
)
from backend.app.rulesets.grid import distance_kilometers, normalize_locator
from backend.app.rulesets.operating import evaluate_operating_constraints
from backend.app.rulesets.schema import (
    AllCondition,
    AnyCondition,
    BonusRule,
    CompareCondition,
    ConfiguredRule,
    DistancePointsRule,
    DuplicateRule,
    EligibilityRule,
    ExchangeRule,
    MultiplierRule,
    NotCondition,
    PenaltyRule,
    PointRule,
    RulesetDefinition,
    ScoreFormulaRule,
    ScoreOperand,
    ScoreStep,
    SessionResetRule,
    WorkflowHookRule,
)
from backend.app.rulesets.validation import RulesetValidationError, validate_ruleset


class RuleExecutionError(ValueError):
    pass


def _condition_comparisons(condition) -> Iterable[CompareCondition]:
    if isinstance(condition, CompareCondition):
        yield condition
    elif isinstance(condition, NotCondition):
        yield from _condition_comparisons(condition.condition)
    elif isinstance(condition, (AllCondition, AnyCondition)):
        for child in condition.conditions:
            yield from _condition_comparisons(child)


class ScoringQso(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    qso_id: int = Field(gt=0)
    occurred_at: datetime
    worked_callsign: str = Field(min_length=1, max_length=32)
    band: str | None = None
    mode: str | None = None
    grid: str | None = None
    transmitter: str | None = None
    continent: str | None = None
    entity: str | None = None
    cq_zone: str | None = None
    itu_zone: str | None = None
    sent_exchange: dict[str, Any] = Field(default_factory=dict)
    received_exchange: dict[str, Any] = Field(default_factory=dict)
    exchange_schema_resolved: bool = True

    @model_validator(mode="after")
    def require_aware_time(self) -> ScoringQso:
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("QSO time must be timezone-aware")
        return self


class ScoringEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    entry_id: int = Field(gt=0)
    station_callsign: str = Field(min_length=1, max_length=32)
    station_grid: str | None = Field(default=None, max_length=32)
    station_entity: str | None = None
    station_continent: str | None = None
    categories: dict[str, str] = Field(default_factory=dict)
    declarations: dict[str, Any] = Field(default_factory=dict)
    power_multiplier: StrictInt = Field(default=1, ge=1)
    qsos: list[ScoringQso] = Field(max_length=500_000)

    @model_validator(mode="after")
    def unique_qso_ids(self) -> ScoringEntry:
        qso_ids = [qso.qso_id for qso in self.qsos]
        if len(qso_ids) != len(set(qso_ids)):
            raise ValueError("QSO ids must be unique in a scoring input")
        return self


class QsoScoreResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    qso_id: StrictInt
    session_number: StrictInt | None = None
    status: Literal["credited", "not_credited", "needs_review"]
    points: StrictInt = Field(ge=0)
    bonus_points: StrictInt = Field(default=0, ge=0)
    penalty_points: StrictInt = Field(ge=0)
    multiplier_keys: list[str]
    reasons: list[str]


class WorkflowAction(BaseModel):
    """Validated handoff request for a trusted downstream workflow handler."""

    model_config = ConfigDict(extra="forbid", strict=True)

    rule_id: str
    entry_id: StrictInt
    qso_id: StrictInt | None = None
    stage: Literal["cross_log", "adjudication", "publication", "award"]
    key: str
    execution: Literal["automatic", "declaration", "human_review"]
    parameters: dict[str, Any]
    status: Literal["pending"] = "pending"


class EntryScoreResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    entry_id: StrictInt
    outcome: Literal["scored", "needs_review", "reclassified", "disqualified"]
    qso_count: StrictInt
    credited_qso_count: StrictInt
    points_total: StrictInt = Field(ge=0)
    multiplier_count: StrictInt = Field(ge=0)
    multiplier_counts: dict[str, StrictInt]
    bonus_counts: dict[str, StrictInt]
    bonus_points: StrictInt = Field(ge=0)
    penalty_points: StrictInt = Field(ge=0)
    final_score: StrictInt = Field(ge=0)
    qso_scores: list[QsoScoreResult]
    workflow_actions: list[WorkflowAction] = Field(default_factory=list)
    review_reasons: list[str] = Field(default_factory=list)
    explanation: list[str]


def _safe_value(path: str, context: Mapping[str, Any]) -> Any:
    value: Any = context
    for part in path.split("."):
        if not isinstance(value, Mapping) or part not in value:
            return None
        value = value[part]
    return value


def _condition_applies(configured: ConfiguredRule, context: Mapping[str, Any]) -> bool:
    return configured.when is None or evaluate_condition(configured.when, context)


def build_rule_context(entry: ScoringEntry, qso: ScoringQso | None) -> dict[str, Any]:
    qso_data: dict[str, Any] = {}
    if qso is not None:
        same_entity = (
            entry.station_entity == qso.entity
            if entry.station_entity is not None and qso.entity is not None
            else None
        )
        same_continent = (
            entry.station_continent == qso.continent
            if entry.station_continent is not None and qso.continent is not None
            else None
        )
        qso_data = {
            "id": qso.qso_id,
            "occurred_at": qso.occurred_at.astimezone(UTC).isoformat(),
            "worked_callsign": qso.worked_callsign,
            "wpx_prefix": wpx_prefix_for_callsign(qso.worked_callsign),
            "callsign_suffix": callsign_suffix(qso.worked_callsign),
            "band": qso.band,
            "mode": qso.mode,
            "grid": qso.grid,
            "transmitter": qso.transmitter,
            "continent": qso.continent,
            "entity": qso.entity,
            "cq_zone": qso.cq_zone,
            "itu_zone": qso.itu_zone,
            "same_entity": same_entity,
            "same_continent": same_continent,
            "different_continent": not same_continent if same_continent is not None else None,
            "exchange_sent": qso.sent_exchange,
            "exchange_received": qso.received_exchange,
        }
    return {
        "qso": qso_data,
        "entry": {
            "id": entry.entry_id,
            "categories": entry.categories,
            "declarations": entry.declarations,
            "power_multiplier": entry.power_multiplier,
        },
        "station": {
            "callsign": entry.station_callsign,
            "grid": entry.station_grid,
            "entity": entry.station_entity,
            "continent": entry.station_continent,
        },
        "contest": {},
        "exchange": {
            "sent": qso.sent_exchange if qso is not None else {},
            "received": qso.received_exchange if qso is not None else {},
            "entry": entry.declarations,
            **(qso.received_exchange if qso is not None else {}),
        },
    }


def _scope_value(rule: DuplicateRule | MultiplierRule, qso: ScoringQso) -> tuple[str, ...] | None:
    if isinstance(rule, MultiplierRule):
        parts = rule.scope.split("_")
    else:
        parts = rule.scope
    values: list[str] = []
    for part in parts:
        if part in {"contest", "worked_callsign"}:
            value = qso.worked_callsign.strip().upper()
        elif part.startswith("exchange."):
            _prefix, direction, field_key = part.split(".", 2)
            exchange_values = (
                qso.sent_exchange if direction == "sent" else qso.received_exchange
            )
            value = exchange_values.get(field_key)
        else:
            value = getattr(qso, part, None)
        if value is None or value == "":
            return None
        values.append(str(value).strip().upper())
    return tuple(values)


def _bonus_scope_value(scope: str, qso: ScoringQso) -> tuple[str, ...] | None:
    if scope == "contest":
        return ("*",)
    values = {
        "band": (qso.band,),
        "mode": (qso.mode,),
        "band_mode": (qso.band, qso.mode),
    }.get(scope)
    if values is None or any(value is None or value == "" for value in values):
        return None
    return tuple(str(value).strip().upper() for value in values)


def _point_value(rule: PointRule, qso: ScoringQso) -> int | None:
    if rule.fact == "fixed":
        return rule.fixed_points
    if rule.fact == "exchange":
        value = qso.received_exchange.get(rule.exchange_field or "")
    else:
        value = getattr(qso, rule.fact, None)
    if value is None:
        return rule.default_points
    mapped = rule.values.get(str(value))
    return mapped if mapped is not None else rule.default_points


def _operand_value(operand: ScoreOperand, variables: dict[str, int]) -> int:
    if operand.constant is not None:
        return operand.constant
    if operand.variable is None:
        raise RuleExecutionError("Score formula operand is missing")
    return variables[operand.variable]


def _round_division(numerator: int, denominator: int, rounding: str | None) -> int:
    if denominator == 0:
        raise RuleExecutionError("Score formula attempted division by zero")
    if rounding is None:
        raise RuleExecutionError("Score formula division has no rounding rule")
    sign = -1 if (numerator < 0) != (denominator < 0) else 1
    quotient, remainder = divmod(abs(numerator), abs(denominator))
    divisor = abs(denominator)
    if rounding == "floor":
        return numerator // denominator
    if rounding == "ceiling":
        return -((-numerator) // denominator)
    if rounding == "half_up" and remainder * 2 >= divisor:
        quotient += 1
    elif rounding == "half_even" and (
        remainder * 2 > divisor or (remainder * 2 == divisor and quotient % 2 == 1)
    ):
        quotient += 1
    return sign * quotient


def _apply_formula(rule: ScoreFormulaRule, variables: dict[str, int]) -> int:
    total = _operand_value(rule.start, variables)
    for step in rule.steps:
        right = _operand_value(step.operand, variables)
        if step.operator == "add":
            total += right
        elif step.operator == "subtract":
            total -= right
        elif step.operator == "multiply":
            total *= right
        elif step.operator == "floor_divide":
            if right == 0:
                raise RuleExecutionError("Score formula attempted division by zero")
            total //= right
        else:
            total = _round_division(total, right, step.rounding)
    if total < 0:
        raise RuleExecutionError(
            "Score formula produced a negative result; configure an explicit nonnegative formula"
        )
    return total


def score_entry(
    definition: RulesetDefinition,
    entry: ScoringEntry,
    *,
    contest_starts_at: datetime,
    contest_ends_at: datetime,
    qso_overrides: Mapping[int, Mapping[str, Any]] | None = None,
) -> EntryScoreResult:
    """Calculate one immutable result explanation using only validated rules and integer math."""
    try:
        definition = validate_ruleset(definition.model_dump(mode="json"))
    except RulesetValidationError as exc:
        raise RuleExecutionError("Cannot execute an invalid ruleset") from exc
    if contest_starts_at.tzinfo is None or contest_ends_at.tzinfo is None:
        raise RuleExecutionError("Contest boundaries must be timezone-aware")
    start = contest_starts_at.astimezone(UTC)
    end = contest_ends_at.astimezone(UTC)
    if start >= end:
        raise RuleExecutionError("Contest start must precede contest end")

    configured = definition.rules
    category_rule = next(item.rule for item in configured if item.rule.kind == "categories")
    category_issues = validate_categories(category_rule, entry.categories)
    if category_issues:
        raise RuleExecutionError(
            "Entry categories are invalid: " + "; ".join(item.message for item in category_issues)
        )

    exchange_rules = [item for item in configured if item.rule.kind == "exchange"]
    eligibility_rules = [item for item in configured if item.rule.kind == "eligibility"]
    duplicate_rules = [item for item in configured if item.rule.kind == "duplicates"]
    point_rules = [item for item in configured if item.rule.kind == "points"]
    distance_rules = [item for item in configured if item.rule.kind == "distance_points"]
    multiplier_rules = [item for item in configured if item.rule.kind == "multiplier"]
    bonus_rules = [item for item in configured if item.rule.kind == "bonus"]
    penalty_rules = [item for item in configured if item.rule.kind == "penalty"]
    session_reset = next(
        (item for item in configured if isinstance(item.rule, SessionResetRule)), None
    )
    formula = next(item.rule for item in configured if item.rule.kind == "score_formula")
    if not isinstance(formula, ScoreFormulaRule):
        raise RuleExecutionError("Ruleset has no usable score formula")
    session_seconds = (
        session_reset.rule.period_minutes * 60
        if session_reset is not None and isinstance(session_reset.rule, SessionResetRule)
        else None
    )
    if session_seconds is not None and session_seconds >= int((end - start).total_seconds()):
        raise RuleExecutionError(
            "Scoring session length must be shorter than the configured contest duration"
        )

    results: dict[int, dict[str, Any]] = {}
    seen: dict[str, set[tuple[str, ...]]] = {item.id: set() for item in duplicate_rules}
    multiplier_keys: set[str] = set()
    sent_serial_progress: dict[tuple[str, ...], int] = {}
    penalty_occurrences: dict[str, int] = {item.id: 0 for item in penalty_rules}
    qso_overrides = qso_overrides or {}
    eligible_contexts: list[tuple[ScoringQso, dict[str, Any]]] = []
    entry_context = build_rule_context(entry, None)
    for qso in sorted(entry.qsos, key=lambda item: (item.occurred_at.astimezone(UTC), item.qso_id)):
        context = build_rule_context(entry, qso)
        status: Literal["credited", "not_credited", "needs_review"] = "credited"
        reasons: list[str] = []
        qso_penalties = 0
        if not qso.exchange_schema_resolved:
            status = "needs_review"
            reasons.append("exchange_schema_unresolved")
        instant = qso.occurred_at.astimezone(UTC)
        session_number = (
            int((instant - start).total_seconds() // session_seconds) + 1
            if session_seconds is not None and start <= instant < end
            else None
        )
        if instant < start or instant >= end:
            status = "not_credited"
            reasons.append("out_of_period")
            results[qso.qso_id] = {
                "qso_id": qso.qso_id,
                "session_number": None,
                "status": status,
                "points": 0,
                "penalty_points": 0,
                "multiplier_keys": [],
                "reasons": reasons,
            }
            continue

        for configured_rule in eligibility_rules:
            rule = configured_rule.rule
            if not isinstance(rule, EligibilityRule):
                continue
            if configured_rule.when is not None:
                activation = evaluate_condition_result(configured_rule.when, context)
                if activation is False:
                    continue
                if activation is None:
                    missing_action = rule.missing_fact_action
                    if status == "credited":
                        status = (
                            "not_credited" if missing_action == "not_credited" else "needs_review"
                        )
                    reasons.extend(
                        [
                            "eligibility_rule_condition_unknown",
                            "eligibility_condition_fact_missing",
                        ]
                    )
                    continue
            invalid = False
            missing_condition_fact = False
            if rule.eligible_if is not None:
                condition_result = evaluate_condition_result(rule.eligible_if, context)
                if condition_result is not True:
                    invalid = True
                    missing_condition_fact = condition_has_missing_data(rule.eligible_if, context)
                    reasons.append("eligibility_condition_failed")
                    if missing_condition_fact:
                        reasons.append("eligibility_condition_fact_missing")
            if rule.reject_out_of_period and (instant < start or instant >= end):
                invalid = True
            if rule.allowed_bands and (qso.band or "").upper() not in {
                value.upper() for value in rule.allowed_bands
            }:
                invalid = True
            if rule.allowed_modes and (qso.mode or "").upper() not in {
                value.upper() for value in rule.allowed_modes
            }:
                invalid = True
            if (
                rule.reject_self_contacts
                and qso.worked_callsign.strip().upper() == entry.station_callsign.strip().upper()
            ):
                invalid = True
            if rule.reject_missing_required_exchange:
                for exchange_rule in exchange_rules:
                    exchange = exchange_rule.rule
                    if not isinstance(exchange, ExchangeRule) or not _condition_applies(
                        exchange_rule, context
                    ):
                        continue
                    check = validate_exchange(
                        exchange,
                        sent=qso.sent_exchange,
                        received=qso.received_exchange,
                        entry=entry.declarations,
                    )
                    if check.issues:
                        invalid = True
                        reasons.extend(issue.code for issue in check.issues)
            if invalid and status == "credited":
                action = rule.missing_fact_action if missing_condition_fact else rule.action
                status = "not_credited" if action == "not_credited" else "needs_review"
                reasons.append("eligibility_rule_failed")

        if (
            session_number is not None
            and session_reset is not None
            and isinstance(session_reset.rule, SessionResetRule)
            and session_reset.rule.reset_serials
        ):
            active_serial_fields_by_key = {
                (field.key, field.serial_scope): field
                for configured_exchange in exchange_rules
                if isinstance(configured_exchange.rule, ExchangeRule)
                and _condition_applies(configured_exchange, context)
                for field in configured_exchange.rule.fields
                if field.value_type == "serial" and field.direction in {"sent", "both"}
            }
            active_serial_fields = list(active_serial_fields_by_key.values())
            serial_field = active_serial_fields[0] if len(active_serial_fields) == 1 else None
            raw_serial = (
                qso.sent_exchange.get(serial_field.key) if serial_field is not None else None
            )
            if isinstance(raw_serial, int) and not isinstance(raw_serial, bool):
                serial_number = raw_serial
            elif isinstance(raw_serial, str) and raw_serial.strip().isdecimal():
                serial_number = int(raw_serial.strip())
            else:
                serial_number = None
            if serial_field is None or serial_number is None or serial_number < 1:
                if status == "credited":
                    status = "needs_review"
                reasons.append("sent_serial_sequence_unverifiable")
            else:
                serial_scope = serial_field.serial_scope or "entry"
                serial_scope_value = (
                    ("entry",)
                    if serial_scope == "entry"
                    else (getattr(qso, serial_scope),)
                )
                if any(value is None or value == "" for value in serial_scope_value):
                    if status == "credited":
                        status = "needs_review"
                    reasons.append("sent_serial_scope_unverifiable")
                else:
                    sequence_key = (
                        serial_field.key,
                        *(str(value).strip().upper() for value in serial_scope_value),
                        str(session_number),
                    )
                    expected_serial = sent_serial_progress.get(
                        sequence_key, session_reset.rule.serial_start_value
                    )
                    if serial_number != expected_serial:
                        if status == "credited":
                            status = "needs_review"
                        reasons.append(
                            f"sent_serial_sequence_mismatch:{expected_serial}:{serial_number}"
                        )
                    sent_serial_progress[sequence_key] = expected_serial + 1

        eligible_before_duplicates = status == "credited"
        duplicate_detected = False
        duplicate_multiplier_allowed = True
        for configured_rule in duplicate_rules:
            rule = configured_rule.rule
            if not isinstance(rule, DuplicateRule) or not _condition_applies(
                configured_rule, context
            ):
                continue
            key = _scope_value(rule, qso)
            if (
                key is not None
                and session_number is not None
                and session_reset is not None
                and isinstance(session_reset.rule, SessionResetRule)
                and session_reset.rule.reset_duplicates
            ):
                key = (*key, str(session_number))
            if key is None:
                duplicate_multiplier_allowed = False
                if status == "credited":
                    status = "needs_review"
                reasons.append("duplicate_key_incomplete")
                continue
            if key in seen[configured_rule.id]:
                duplicate_detected = True
                duplicate_multiplier_allowed = (
                    duplicate_multiplier_allowed and rule.count_for_multipliers
                )
                reasons.append("duplicate")
                if rule.effect in {"ignore", "not_credited"}:
                    status = "not_credited"
                elif rule.effect == "needs_review" and status == "credited":
                    status = "needs_review"
                elif rule.effect == "penalty":
                    qso_penalties += rule.penalty_points
                    status = "not_credited"
            else:
                seen[configured_rule.id].add(key)

        multiplier_eligible = status == "credited" or (
            eligible_before_duplicates and duplicate_detected and duplicate_multiplier_allowed
        )
        for configured_rule in penalty_rules:
            rule = configured_rule.rule
            if not isinstance(rule, PenaltyRule) or not _condition_applies(
                configured_rule, context
            ):
                continue
            occurrence = penalty_occurrences[configured_rule.id]
            if occurrence >= rule.maximum_occurrences:
                continue
            penalty_occurrences[configured_rule.id] += 1
            reasons.append(rule.reason_code)
            if rule.action == "deduct_points":
                qso_penalties += rule.points
            elif rule.action == "remove_contact":
                status = "not_credited"
                multiplier_eligible = False
            elif rule.action in {"needs_review", "reclassify"}:
                if status == "credited":
                    status = "needs_review"
                multiplier_eligible = False
            elif rule.action == "disqualify":
                status = "not_credited"
                multiplier_eligible = False

        # The latest persisted adjudication decision is an explicit human ruling. It is
        # applied after automatic rule checks and before score components are calculated.
        override = qso_overrides.get(qso.qso_id)
        if override is not None:
            override_status = override.get("status")
            if override_status not in {"credited", "not_credited", "needs_review"}:
                raise RuleExecutionError("QSO decision override has an unsupported status")
            status = override_status
            multiplier_eligible = override_status == "credited" and (
                not duplicate_detected
                or (eligible_before_duplicates and duplicate_multiplier_allowed)
            )
            reasons.append(str(override.get("reason_code", "review_override")))

        points = 0
        qso_multiplier_keys: list[str] = []
        if status == "credited" and not duplicate_detected:
            for configured_rule in point_rules:
                rule = configured_rule.rule
                if not isinstance(rule, PointRule) or not _condition_applies(
                    configured_rule, context
                ):
                    continue
                point_value = _point_value(rule, qso)
                if point_value is None:
                    status = "needs_review"
                    multiplier_eligible = False
                    reasons.append(f"missing_point_mapping:{configured_rule.id}")
                    points = 0
                    break
                points += point_value
            if status == "credited":
                for configured_rule in distance_rules:
                    rule = configured_rule.rule
                    if not isinstance(rule, DistancePointsRule) or not _condition_applies(
                        configured_rule, context
                    ):
                        continue
                    raw_worked_grid = qso.received_exchange.get(rule.grid_field)
                    raw_entrant_grid = qso.sent_exchange.get("grid", entry.station_grid)
                    entrant_grid = (
                        normalize_locator(raw_entrant_grid, rule.precision)
                        if isinstance(raw_entrant_grid, str)
                        else None
                    )
                    worked_grid = (
                        normalize_locator(raw_worked_grid, rule.precision)
                        if isinstance(raw_worked_grid, str)
                        else None
                    )
                    distance = (
                        distance_kilometers(entrant_grid, worked_grid, rule.precision)
                        if entrant_grid is not None and worked_grid is not None
                        else None
                    )
                    if distance is None:
                        status = rule.missing_grid_action
                        multiplier_eligible = False
                        reasons.append(f"distance_grid_missing_or_invalid:{configured_rule.id}")
                        points = 0
                        break
                    same_grid = entrant_grid == worked_grid
                    awarded = (
                        rule.same_grid_points if same_grid else distance * rule.points_per_kilometer
                    )
                    points += awarded
                    reasons.append(f"distance_points:{configured_rule.id}:{distance}km:{awarded}")
        if multiplier_eligible:
            for configured_rule in multiplier_rules:
                rule = configured_rule.rule
                if not isinstance(rule, MultiplierRule) or not _condition_applies(
                    configured_rule, context
                ):
                    continue
                value = _safe_value(rule.source_fact, context)
                scope = _scope_value(rule, qso) if rule.scope != "contest" else ("*",)
                if (
                    scope is not None
                    and session_number is not None
                    and session_reset is not None
                    and isinstance(session_reset.rule, SessionResetRule)
                    and session_reset.rule.reset_multipliers
                ):
                    scope = (*scope, f"session-{session_number}")
                if value is None or scope is None:
                    status = "needs_review"
                    multiplier_eligible = False
                    reasons.append(f"missing_multiplier_value:{configured_rule.id}")
                    # A QSO is all-or-nothing across the multiplier rules that
                    # apply to it. Do not return candidate keys if another
                    # required multiplier value is missing.
                    qso_multiplier_keys.clear()
                    break
                unique_key = f"{configured_rule.id}:{'|'.join(scope)}:{str(value).strip().upper()}"
                if unique_key not in multiplier_keys:
                    qso_multiplier_keys.append(unique_key)

        if multiplier_eligible:
            multiplier_keys.update(qso_multiplier_keys)

        if status == "credited" and not duplicate_detected:
            eligible_contexts.append((qso, context))

        results[qso.qso_id] = {
            "qso_id": qso.qso_id,
            "session_number": session_number,
            "status": status,
            "points": points if status == "credited" else 0,
            "penalty_points": qso_penalties,
            "multiplier_keys": qso_multiplier_keys,
            "reasons": reasons,
        }

    bonus_total = 0
    bonus_counts: dict[str, int] = {}
    bonus_by_qso: dict[int, int] = {}
    bonus_review_reasons: list[str] = []
    grouped_bonus_values: dict[str, set[tuple[str, ...]]] = {}
    ordered_eligible_contexts = sorted(
        eligible_contexts,
        key=lambda item: (item[0].occurred_at.astimezone(UTC), item[0].qso_id),
    )
    for configured_rule in bonus_rules:
        rule = configured_rule.rule
        if not isinstance(rule, BonusRule):
            continue
        amount = 0
        award_count = 0
        if rule.basis == "per_distinct_value":
            distinct_values: set[tuple[str, ...]] = set()
            evidence_present = not rule.evidence_key or bool(
                entry.declarations.get(rule.evidence_key)
            )
            if evidence_present and len(ordered_eligible_contexts) >= rule.minimum_eligible_qsos:
                for qso, context in ordered_eligible_contexts:
                    if not _condition_applies(configured_rule, context):
                        continue
                    value = _safe_value(rule.source_fact or "", context)
                    scope = _bonus_scope_value(rule.scope or "", qso)
                    if value is None or scope is None:
                        reason = f"missing_bonus_value:{configured_rule.id}"
                        if rule.missing_fact_action == "needs_review":
                            bonus_review_reasons.append(reason)
                            results[qso.qso_id]["reasons"].append(reason)
                        continue
                    normalized_value = (
                        " ".join(value.split()).upper() if isinstance(value, str) else str(value)
                    )
                    unique_key = (*scope, normalized_value)
                    if unique_key in distinct_values:
                        continue
                    distinct_values.add(unique_key)
                    if rule.award_group and unique_key in grouped_bonus_values.setdefault(
                        rule.award_group, set()
                    ):
                        continue
                    award = rule.points
                    if rule.cap is not None:
                        award = min(award, max(rule.cap - amount, 0))
                    if award <= 0:
                        continue
                    amount += award
                    award_count += 1
                    bonus_by_qso[qso.qso_id] = bonus_by_qso.get(qso.qso_id, 0) + award
                    if rule.award_group:
                        grouped_bonus_values[rule.award_group].add(unique_key)
        elif (
            rule.basis == "per_eligible_qso"
            and len(ordered_eligible_contexts) >= rule.minimum_eligible_qsos
        ):
            for qso, context in ordered_eligible_contexts:
                if _condition_applies(configured_rule, context):
                    if rule.evidence_key and not entry.declarations.get(rule.evidence_key):
                        continue
                    amount += rule.points
                    award_count += 1
                    bonus_by_qso[qso.qso_id] = bonus_by_qso.get(qso.qso_id, 0) + rule.points
        elif (
            rule.basis == "per_entry"
            and _condition_applies(configured_rule, entry_context)
            and len(ordered_eligible_contexts) >= rule.minimum_eligible_qsos
        ):
            if not rule.evidence_key or entry.declarations.get(rule.evidence_key):
                amount = rule.points
                award_count = 1
        if rule.cap is not None:
            amount = min(amount, rule.cap)
        bonus_total += amount
        bonus_counts[configured_rule.id] = award_count

    qso_scores = [
        QsoScoreResult.model_validate(
            {**results[qso.qso_id], "bonus_points": bonus_by_qso.get(qso.qso_id, 0)}
        )
        for qso in sorted(
            entry.qsos,
            key=lambda item: (item.occurred_at.astimezone(UTC), item.qso_id),
        )
    ]
    points_total = sum(result.points for result in qso_scores)
    penalty_points = sum(result.penalty_points for result in qso_scores)
    multiplier_count = len(multiplier_keys)
    multiplier_counts = {
        configured_rule.id: sum(key.startswith(f"{configured_rule.id}:") for key in multiplier_keys)
        for configured_rule in multiplier_rules
    }
    disqualified = any(
        rule.action == "disqualify"
        and any(rule.reason_code in score.reasons for score in qso_scores)
        for configured_rule in penalty_rules
        if isinstance((rule := configured_rule.rule), PenaltyRule)
    )
    reclassified = any(
        rule.action == "reclassify"
        and any(rule.reason_code in score.reasons for score in qso_scores)
        for configured_rule in penalty_rules
        if isinstance((rule := configured_rule.rule), PenaltyRule)
    )
    variables = {
        "points_total": points_total,
        "multiplier_count": multiplier_count,
        "bonus_points": bonus_total,
        "penalty_points": penalty_points,
        "power_multiplier": entry.power_multiplier,
        **{f"multiplier.{rule_id}": count for rule_id, count in multiplier_counts.items()},
    }
    final_score = 0 if disqualified else _apply_formula(formula, variables)
    review_reasons = [
        f"qso:{score.qso_id}:{reason}"
        for score in qso_scores
        if score.status == "needs_review"
        for reason in score.reasons
    ]
    review_reasons.extend(sorted(set(bonus_review_reasons)))
    workflow_actions: list[WorkflowAction] = []
    for configured_rule in configured:
        if isinstance(configured_rule.rule, WorkflowHookRule):
            uses_qso_facts = configured_rule.when is not None and any(
                comparison.fact.startswith("qso.")
                for comparison in _condition_comparisons(configured_rule.when)
            )
            candidates = (
                [
                    (qso.qso_id, build_rule_context(entry, qso))
                    for qso in sorted(
                        entry.qsos,
                        key=lambda item: (item.occurred_at.astimezone(UTC), item.qso_id),
                    )
                    if _condition_applies(configured_rule, build_rule_context(entry, qso))
                ]
                if uses_qso_facts
                else [(None, entry_context)]
            )
            if not uses_qso_facts and not _condition_applies(configured_rule, entry_context):
                candidates = []
            for qso_id, _context in candidates:
                workflow_actions.append(
                    WorkflowAction(
                        rule_id=configured_rule.id,
                        entry_id=entry.entry_id,
                        qso_id=qso_id,
                        stage=configured_rule.rule.stage,
                        key=configured_rule.rule.key,
                        execution=configured_rule.rule.execution,
                        parameters=configured_rule.rule.parameters,
                    )
                )
                if configured_rule.rule.stage in {"cross_log", "adjudication"}:
                    review_reasons.append(
                        f"workflow:{configured_rule.rule.stage}:{configured_rule.rule.key}:"
                        f"{configured_rule.rule.execution}"
                    )
        elif configured_rule.rule.kind == "operating_constraints" and _condition_applies(
            configured_rule, entry_context
        ):
            findings = evaluate_operating_constraints(
                configured_rule.rule,
                entry,
                contest_starts_at=start,
                contest_ends_at=end,
            )
            review_reasons.extend(f"constraint:{finding.code}" for finding in findings)
    outcome: Literal["scored", "needs_review", "reclassified", "disqualified"] = (
        "disqualified"
        if disqualified
        else "reclassified"
        if reclassified
        else "needs_review"
        if review_reasons
        else "scored"
    )
    explanation = [
        f"QSO points total: {points_total}.",
        f"Unique multiplier count: {multiplier_count}.",
        *[
            f"Multiplier {rule_id}: {count}."
            for rule_id, count in sorted(multiplier_counts.items())
        ],
        f"Bonus points: {bonus_total}.",
        *[
            f"Bonus {rule_id}: {count} qualifying award(s)."
            for rule_id, count in sorted(bonus_counts.items())
        ],
        f"Penalty points: {penalty_points}.",
        "Score formula evaluated left to right in configured operation order using integers.",
        f"Final score: {final_score}.",
        *[f"Pending adjudication: {reason}." for reason in review_reasons],
    ]
    return EntryScoreResult(
        entry_id=entry.entry_id,
        outcome=outcome,
        qso_count=len(entry.qsos),
        credited_qso_count=sum(result.status == "credited" for result in qso_scores),
        points_total=points_total,
        multiplier_count=multiplier_count,
        multiplier_counts=multiplier_counts,
        bonus_counts=bonus_counts,
        bonus_points=bonus_total,
        penalty_points=penalty_points,
        final_score=final_score,
        qso_scores=qso_scores,
        workflow_actions=workflow_actions,
        review_reasons=review_reasons,
        explanation=explanation,
    )


def evaluate_score_step(current: int, step: ScoreStep, variables: dict[str, int]) -> int:
    """Public integer operation helper for worked examples and rule-summary previews."""
    operand = (
        step.operand.constant
        if step.operand.constant is not None
        else variables.get(step.operand.variable or "")
    )
    if operand is None:
        raise RuleExecutionError(f"Unknown score variable: {step.operand.variable}")
    if step.operator == "add":
        return current + operand
    if step.operator == "subtract":
        return current - operand
    if step.operator == "multiply":
        return current * operand
    if step.operator == "floor_divide":
        if operand == 0:
            raise RuleExecutionError("Score formula attempted division by zero")
        return current // operand
    return _round_division(current, operand, step.rounding)
