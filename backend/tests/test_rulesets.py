from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError

from backend.app.main import app
from backend.app.rulesets.checks import validate_categories, validate_exchange
from backend.app.rulesets.conditions import evaluate_condition
from backend.app.rulesets.engine import RuleExecutionError, ScoringEntry, score_entry
from backend.app.rulesets.operating import evaluate_operating_constraints
from backend.app.rulesets.schedules import (
    classify_submission,
    resolve_schedule,
    resolve_submission,
)
from backend.app.rulesets.schema import (
    BonusRule,
    CategoryRule,
    Condition,
    ExchangeRule,
    OperatingConstraintRule,
    Recurrence,
    ScheduleRule,
    SubmissionRule,
)
from backend.app.rulesets.validation import RulesetValidationError, validate_ruleset

START = datetime(2026, 1, 1, tzinfo=UTC)
END = datetime(2026, 1, 1, 2, tzinfo=UTC)


def valid_payload() -> dict[str, object]:
    return {
        "ruleset_key": "sample-sprint",
        "version": "2026",
        "source_url": "https://example.test/rules/2026",
        "source_edition": "2026 edition",
        "rules": [
            {
                "id": "schedule",
                "rule": {
                    "kind": "schedule",
                    "timezone": "UTC",
                    "start_time_utc": "00:00:00",
                    "duration_minutes": 120,
                    "fixed_start_utc": "2026-01-01T00:00:00Z",
                },
            },
            {
                "id": "submission",
                "rule": {
                    "kind": "submission",
                    "cutoff_mode": "at_utc",
                    "cutoff_utc": "2026-01-02T00:00:00Z",
                    "late_policy": "checklog",
                    "manager_extension_allowed": True,
                },
            },
            {
                "id": "categories",
                "rule": {
                    "kind": "categories",
                    "dimensions": [
                        {
                            "key": "operator",
                            "label": "Operator",
                            "choices": [{"key": "single", "label": "Single operator"}],
                        }
                    ],
                },
            },
            {
                "id": "exchange",
                "rule": {
                    "kind": "exchange",
                    "fields": [
                        {
                            "key": "serial",
                            "label": "Serial number",
                            "value_type": "serial",
                            "direction": "both",
                            "serial_scope": "entry",
                        },
                        {
                            "key": "section",
                            "label": "Section",
                            "value_type": "text",
                            "direction": "entry",
                        },
                    ],
                },
            },
            {"id": "eligibility", "rule": {"kind": "eligibility"}},
            {
                "id": "duplicates",
                "rule": {
                    "kind": "duplicates",
                    "scope": ["worked_callsign", "band"],
                    "effect": "not_credited",
                },
            },
            {"id": "points", "rule": {"kind": "points", "fact": "fixed", "fixed_points": 2}},
            {
                "id": "score",
                "rule": {
                    "kind": "score_formula",
                    "start": {"variable": "points_total"},
                    "steps": [
                        {"operator": "multiply", "operand": {"variable": "multiplier_count"}},
                        {"operator": "add", "operand": {"variable": "bonus_points"}},
                        {"operator": "subtract", "operand": {"variable": "penalty_points"}},
                    ],
                },
            },
            {
                "id": "format",
                "rule": {"kind": "format_mapping", "format": "cabrillo", "qso_columns": ["band"]},
            },
            {
                "id": "entity-multiplier",
                "rule": {
                    "kind": "multiplier",
                    "source_fact": "qso.entity",
                    "scope": "contest",
                    "label": "Entity",
                },
            },
            {
                "id": "entry-bonus",
                "rule": {
                    "kind": "bonus",
                    "basis": "per_entry",
                    "points": 5,
                    "minimum_eligible_qsos": 1,
                },
            },
        ],
    }


def sample_entry() -> ScoringEntry:
    return ScoringEntry.model_validate(
        {
            "entry_id": 1,
            "station_callsign": "N0CALL",
            "categories": {"operator": "single"},
            "declarations": {"section": "EMA"},
            "qsos": [
                {
                    "qso_id": 2,
                    "occurred_at": datetime(2026, 1, 1, 0, 10, tzinfo=UTC),
                    "worked_callsign": "K1ABC",
                    "band": "40m",
                    "mode": "CW",
                    "entity": "K",
                    "sent_exchange": {"serial": "002"},
                    "received_exchange": {"serial": "9"},
                },
                {
                    "qso_id": 1,
                    "occurred_at": datetime(2026, 1, 1, tzinfo=UTC),
                    "worked_callsign": "K1ABC",
                    "band": "40m",
                    "mode": "CW",
                    "entity": "K",
                    "sent_exchange": {"serial": "001"},
                    "received_exchange": {"serial": "8"},
                },
            ],
        }
    )


def test_catalog_endpoint_exposes_typed_rule_schemas():
    response = TestClient(app).get("/api/v1/rulesets/catalog")

    assert response.status_code == 200
    catalog = response.json()["rule_types"]
    assert {item["key"] for item in catalog} >= {
        "schedule",
        "submission",
        "categories",
        "exchange",
        "eligibility",
        "duplicates",
        "points",
        "multiplier",
        "bonus",
        "penalty",
        "score_formula",
        "operating_constraints",
        "format_mapping",
        "workflow_hook",
    }
    assert "eval" not in str(catalog)
    schedule = next(item for item in catalog if item["key"] == "schedule")["schema"]
    assert schedule["properties"]["timezone"]["const"] == "UTC"
    assert "start_local_time" not in schedule["properties"]
    assert "ambiguous_time_fold" not in schedule["properties"]
    assert "description" in schedule["properties"]["start_time_utc"]


def test_validation_endpoint_returns_summary_and_integer_worked_example():
    response = TestClient(app).post("/api/v1/rulesets/validate", json=valid_payload())

    assert response.status_code == 200
    result = response.json()
    assert result["valid"] is True
    assert result["ruleset_key"] == "sample-sprint"
    assert "Fixed schedule" in result["summary"]
    assert result["worked_score_example"]["final_score"] == 965
    assert all(type(step["result"]) is int for step in result["worked_score_example"]["steps"])


def test_validation_endpoint_reports_cross_rule_errors_as_field_details():
    payload = valid_payload()
    payload["rules"] = [item for item in payload["rules"] if item["id"] != "format"]
    response = TestClient(app).post("/api/v1/rulesets/validate", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_ruleset"
    assert any(
        "format_mapping" in detail["message"] for detail in response.json()["error"]["details"]
    )


def test_ruleset_schema_rejects_unknown_and_fractional_values():
    payload = valid_payload()
    payload["undocumented_default"] = True
    with pytest.raises(RulesetValidationError, match="invalid"):
        validate_ruleset(payload)

    payload = valid_payload()
    next(item for item in payload["rules"] if item["id"] == "points")["rule"]["fixed_points"] = 1.5
    with pytest.raises(RulesetValidationError):
        validate_ruleset(payload)


def test_ruleset_validator_rejects_duplicate_keys_unsafe_patterns_and_bad_fact_paths():
    payload = valid_payload()
    payload["rules"].append(payload["rules"][0])
    with pytest.raises(RulesetValidationError):
        validate_ruleset(payload)

    payload = valid_payload()
    payload["rules"][4]["when"] = {
        "kind": "compare",
        "fact": "qso.band",
        "operator": "matches",
        "value": "(a+)+$",
    }
    with pytest.raises(RulesetValidationError) as error:
        validate_ruleset(payload)
    assert any("safe subset" in str(issue["message"]) for issue in error.value.errors)

    payload["rules"][4]["when"] = {
        "kind": "compare",
        "fact": "qso.iaru_region",
        "operator": "eq",
        "value": "1",
    }
    with pytest.raises(RulesetValidationError) as error:
        validate_ruleset(payload)
    assert any("unsupported fact" in str(issue["message"]) for issue in error.value.errors)

    payload = valid_payload()
    eligibility = next(item for item in payload["rules"] if item["id"] == "eligibility")
    eligibility["rule"]["eligible_if"] = {
        "kind": "compare",
        "fact": "qso.iaru_region",
        "operator": "eq",
        "value": "1",
    }
    with pytest.raises(RulesetValidationError) as error:
        validate_ruleset(payload)
    assert any("unsupported fact" in str(issue["message"]) for issue in error.value.errors)

    payload = valid_payload()
    multiplier = next(item for item in payload["rules"] if item["id"] == "entity-multiplier")
    multiplier["rule"]["source_fact"] = "qso.iaru_region"
    with pytest.raises(RulesetValidationError) as error:
        validate_ruleset(payload)
    assert any(
        "unsupported or undefined fact" in str(issue["message"]) for issue in error.value.errors
    )


def test_condition_groups_are_typed_and_evaluated_without_code_execution():
    condition = TypeAdapter(Condition).validate_python(
        {
            "kind": "all",
            "conditions": [
                {"kind": "compare", "fact": "qso.band", "operator": "eq", "value": "20m"},
                {
                    "kind": "not",
                    "condition": {
                        "kind": "compare",
                        "fact": "entry.categories.operator",
                        "operator": "eq",
                        "value": "multi",
                    },
                },
            ],
        }
    )

    assert evaluate_condition(
        condition, {"qso": {"band": "20m"}, "entry": {"categories": {"operator": "single"}}}
    )
    assert not evaluate_condition(
        condition, {"qso": {"band": "40m"}, "entry": {"categories": {"operator": "single"}}}
    )


def test_eligibility_predicates_apply_to_contact_geography_and_entry_facts():
    payload = valid_payload()
    eligibility = next(item for item in payload["rules"] if item["id"] == "eligibility")
    eligibility["rule"]["eligible_if"] = {
        "kind": "all",
        "conditions": [
            {"kind": "compare", "fact": "qso.entity", "operator": "eq", "value": "K"},
            {
                "kind": "compare",
                "fact": "entry.declarations.section",
                "operator": "eq",
                "value": "EMA",
            },
            {
                "kind": "compare",
                "fact": "station.callsign",
                "operator": "eq",
                "value": "N0CALL",
            },
        ],
    }
    entry = sample_entry()
    entry.qsos[0].entity = "DL"

    result = score_entry(
        validate_ruleset(payload), entry, contest_starts_at=START, contest_ends_at=END
    )

    assert result.qso_scores[0].status == "credited"
    assert result.qso_scores[1].status == "not_credited"
    assert "eligibility_condition_failed" in result.qso_scores[1].reasons


def test_scoring_emits_structured_pending_workflow_actions():
    payload = valid_payload()
    payload["rules"].extend(
        [
            {
                "id": "cross-check",
                "rule": {
                    "kind": "workflow_hook",
                    "stage": "cross_log",
                    "key": "counterpart_match",
                    "execution": "automatic",
                    "parameters": {"timestamp_tolerance_seconds": 300},
                },
                "when": {
                    "kind": "compare",
                    "fact": "qso.band",
                    "operator": "eq",
                    "value": "40m",
                },
            },
            {
                "id": "review",
                "rule": {
                    "kind": "workflow_hook",
                    "stage": "adjudication",
                    "key": "manual_review",
                    "execution": "human_review",
                },
            },
            {
                "id": "publish",
                "rule": {
                    "kind": "workflow_hook",
                    "stage": "publication",
                    "key": "public_results",
                    "execution": "automatic",
                },
            },
            {
                "id": "awards",
                "rule": {
                    "kind": "workflow_hook",
                    "stage": "award",
                    "key": "award_eligibility",
                    "execution": "declaration",
                },
            },
        ]
    )

    result = score_entry(
        validate_ruleset(payload), sample_entry(), contest_starts_at=START, contest_ends_at=END
    )

    assert [(action.stage, action.qso_id) for action in result.workflow_actions] == [
        ("cross_log", 1),
        ("cross_log", 2),
        ("adjudication", None),
        ("publication", None),
        ("award", None),
    ]
    assert all(action.status == "pending" for action in result.workflow_actions)
    assert result.outcome == "needs_review"


def test_schedule_recurrence_is_resolved_in_utc_without_local_time_or_dst_fold():
    rule = ScheduleRule.model_validate(
        {
            "kind": "schedule",
            "timezone": "UTC",
            "start_time_utc": "08:00:00",
            "duration_minutes": 90,
            "recurrence": {"frequency": "first_full_weekend", "month": 1},
        }
    )
    resolved = resolve_schedule(rule, 2025)
    assert resolved.starts_at == datetime(2025, 1, 4, 8, tzinfo=UTC)
    assert resolved.ends_at == datetime(2025, 1, 4, 9, 30, tzinfo=UTC)

    annual = ScheduleRule.model_validate(
        {
            "kind": "schedule",
            "timezone": "UTC",
            "start_time_utc": "02:30:00",
            "duration_minutes": 60,
            "recurrence": {"frequency": "annual_date", "month": 10, "day": 26},
        }
    )
    assert resolve_schedule(annual, 2025).starts_at == datetime(2025, 10, 26, 2, 30, tzinfo=UTC)
    with pytest.raises(ValidationError, match="UTC"):
        ScheduleRule.model_validate(
            {
                "kind": "schedule",
                "timezone": "Europe/Berlin",
                "start_time_utc": "02:30:00",
                "duration_minutes": 60,
                "recurrence": {"frequency": "annual_date", "month": 10, "day": 26},
            }
        )
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ScheduleRule.model_validate(
            {
                "kind": "schedule",
                "start_local_time": "02:30:00",
                "ambiguous_time_fold": 1,
                "duration_minutes": 60,
                "recurrence": {"frequency": "annual_date", "month": 10, "day": 26},
            }
        )


def test_schedule_preview_api_returns_utc_instants_for_selected_recurrence():
    response = TestClient(app).post(
        "/api/v1/rulesets/schedule-preview",
        json={
            "year": 2026,
            "schedule": {
                "kind": "schedule",
                "timezone": "UTC",
                "start_time_utc": "08:00:00",
                "duration_minutes": 90,
                "recurrence": {"frequency": "first_full_weekend", "month": 1},
            },
        },
    )
    assert response.status_code == 200
    assert response.json() == {
        "starts_at": "2026-01-03T08:00:00Z",
        "ends_at": "2026-01-03T09:30:00Z",
    }
    invalid = TestClient(app).post(
        "/api/v1/rulesets/schedule-preview",
        json={
            "year": 2026,
            "schedule": {
                "kind": "schedule",
                "timezone": "UTC+1",
                "start_time_utc": "08:00:00",
                "duration_minutes": 90,
                "recurrence": {"frequency": "annual_date", "month": 1, "day": 3},
            },
        },
    )
    assert invalid.status_code == 422


def test_recurrence_rejects_zero_occurrence_at_schema_boundary():
    with pytest.raises(ValidationError, match="occurrence must be"):
        Recurrence.model_validate(
            {"frequency": "nth_weekday", "month": 1, "weekday": 0, "occurrence": 0}
        )


def test_common_exchange_keys_reject_incompatible_value_types():
    with pytest.raises(
        ValidationError, match="standard exchange field serial requires type serial"
    ):
        ExchangeRule.model_validate(
            {
                "kind": "exchange",
                "fields": [{"key": "serial", "label": "Serial", "value_type": "text"}],
            }
        )


def test_cutoff_is_separate_and_extensions_follow_manager_policy():
    schedule = resolve_schedule(
        ScheduleRule.model_validate(
            {
                "kind": "schedule",
                "timezone": "UTC",
                "start_time_utc": "00:00:00",
                "duration_minutes": 60,
                "fixed_start_utc": "2026-01-01T00:00:00Z",
            }
        )
    )
    submission = resolve_submission(
        SubmissionRule.model_validate(
            {
                "kind": "submission",
                "cutoff_mode": "at_utc",
                "cutoff_utc": "2026-01-05T00:00:00Z",
                "late_policy": "accept_late",
                "manager_extension_allowed": True,
            }
        ),
        schedule,
    )
    assert submission.cutoff_at == datetime(2026, 1, 5, tzinfo=UTC)
    assert (
        classify_submission(submission.cutoff_at, submission.cutoff_at, "accept_late") == "on_time"
    )
    assert (
        classify_submission(
            datetime(2026, 1, 6, tzinfo=UTC),
            submission.cutoff_at,
            submission.late_policy,
            manager_extension_until=datetime(2026, 1, 7, tzinfo=UTC),
            manager_extension_allowed=submission.manager_extension_allowed,
        )
        == "on_time"
    )
    with pytest.raises(ValueError, match="does not allow"):
        classify_submission(
            datetime(2026, 1, 6, tzinfo=UTC),
            submission.cutoff_at,
            "reject",
            manager_extension_until=datetime(2026, 1, 7, tzinfo=UTC),
        )


def test_category_and_exchange_validation_preserve_raw_values_and_report_paths():
    categories = CategoryRule.model_validate(
        {
            "kind": "categories",
            "dimensions": [
                {
                    "key": "operator",
                    "label": "Operator",
                    "choices": [{"key": "single", "label": "Single"}],
                },
                {
                    "key": "overlay",
                    "label": "Overlay",
                    "required": False,
                    "choices": [{"key": "rookie", "label": "Rookie"}],
                },
            ],
            "mutually_exclusive": [["operator", "overlay"]],
        }
    )
    assert {
        issue.code
        for issue in validate_categories(categories, {"operator": "bad", "overlay": "rookie"})
    } == {
        "invalid_choice",
        "incompatible_categories",
    }

    exchange = ExchangeRule.model_validate(
        {
            "kind": "exchange",
            "fields": [
                {
                    "key": "serial",
                    "label": "Serial",
                    "value_type": "serial",
                    "direction": "both",
                    "serial_scope": "entry",
                },
                {
                    "key": "section",
                    "label": "Section",
                    "value_type": "text",
                    "direction": "entry",
                    "pattern": "[A-Z]+",
                },
            ],
        }
    )
    raw_sent = {"serial": " 007 "}
    checked = validate_exchange(
        exchange, sent=raw_sent, received={"serial": "bad"}, entry={"section": "EMA"}
    )
    assert raw_sent == {"serial": " 007 "}
    assert checked.normalized["sent"]["serial"] == 7
    assert checked.normalized["entry"]["section"] == "EMA"
    assert [(issue.path, issue.code) for issue in checked.issues] == [
        ("exchange.received.serial", "invalid_value")
    ]


def test_scoring_is_deterministic_integer_only_and_keeps_explanations():
    result = score_entry(
        validate_ruleset(valid_payload()),
        sample_entry(),
        contest_starts_at=START,
        contest_ends_at=END,
    )

    assert result.outcome == "scored"
    assert result.points_total == 2
    assert result.multiplier_count == 1
    assert result.bonus_points == 5
    assert result.final_score == 7
    assert [qso.qso_id for qso in result.qso_scores] == [1, 2]
    assert [qso.status for qso in result.qso_scores] == ["credited", "not_credited"]
    assert all(
        type(value) is int
        for value in (result.points_total, result.penalty_points, result.final_score)
    )
    rerun = score_entry(
        validate_ruleset(valid_payload()),
        sample_entry(),
        contest_starts_at=START,
        contest_ends_at=END,
    )
    assert result.model_dump(mode="json") == rerun.model_dump(mode="json")


def test_bonus_evidence_key_replaces_legacy_required_boolean_in_json():
    payload = valid_payload()
    legacy = next(item for item in payload["rules"] if item["id"] == "entry-bonus")
    legacy["rule"]["evidence_required"] = True
    legacy["rule"]["evidence_key"] = "proof"
    ruleset = validate_ruleset(payload)
    bonus = next(item.rule for item in ruleset.rules if item.id == "entry-bonus")

    assert bonus.evidence_key == "proof"
    assert "evidence_required" not in bonus.model_dump()
    assert "evidence_required" not in BonusRule.model_json_schema()["properties"]
    with pytest.raises(ValidationError, match="must agree"):
        BonusRule.model_validate(
            {
                "kind": "bonus",
                "basis": "per_entry",
                "points": 5,
                "evidence_required": False,
                "evidence_key": "proof",
            }
        )


def test_bonus_evidence_key_alone_controls_evidence_requirement():
    payload = valid_payload()
    bonus = next(item for item in payload["rules"] if item["id"] == "entry-bonus")
    bonus["rule"]["evidence_key"] = "proof"
    ruleset = validate_ruleset(payload)

    without_evidence = score_entry(
        ruleset, sample_entry(), contest_starts_at=START, contest_ends_at=END
    )
    entry_with_evidence = sample_entry().model_copy(
        update={"declarations": {"section": "EMA", "proof": "uploaded"}}
    )
    with_evidence = score_entry(
        ruleset, entry_with_evidence, contest_starts_at=START, contest_ends_at=END
    )

    assert without_evidence.bonus_points == 0
    assert with_evidence.bonus_points == 5


def test_scoring_applies_penalty_caps_and_surfaces_missing_mappings_for_review():
    payload = valid_payload()
    payload["rules"].append(
        {
            "id": "broken-call",
            "rule": {
                "kind": "penalty",
                "reason_code": "broken_exchange",
                "action": "deduct_points",
                "points": 1,
                "maximum_occurrences": 1,
            },
            "when": {"kind": "compare", "fact": "qso.band", "operator": "eq", "value": "40m"},
        }
    )
    result = score_entry(
        validate_ruleset(payload), sample_entry(), contest_starts_at=START, contest_ends_at=END
    )
    assert result.penalty_points == 1
    assert result.final_score == 6
    assert result.qso_scores[0].reasons.count("broken_exchange") == 1

    payload = valid_payload()
    points = next(item for item in payload["rules"] if item["id"] == "points")["rule"]
    points.update({"fact": "band", "fixed_points": None, "values": {"20m": 2}})
    entry = sample_entry().model_copy(
        update={"qsos": [sample_entry().qsos[0].model_copy(update={"band": "80m"})]}
    )
    result = score_entry(
        validate_ruleset(payload), entry, contest_starts_at=START, contest_ends_at=END
    )
    assert result.outcome == "needs_review"
    assert result.qso_scores[0].status == "needs_review"
    assert result.points_total == 0


def test_operating_constraint_gaps_and_declarations_are_reviewable():
    entry = ScoringEntry.model_validate(
        {
            "entry_id": 2,
            "station_callsign": "N0CALL",
            "declarations": {"transmitter_count": 1},
            "qsos": [
                {
                    "qso_id": 1,
                    "occurred_at": datetime(2026, 1, 1, tzinfo=UTC),
                    "worked_callsign": "A1",
                    "band": "20m",
                    "transmitter": "A",
                },
                {
                    "qso_id": 2,
                    "occurred_at": datetime(2026, 1, 1, 0, 20, tzinfo=UTC),
                    "worked_callsign": "B1",
                    "band": "40m",
                    "transmitter": "A",
                },
                {
                    "qso_id": 3,
                    "occurred_at": datetime(2026, 1, 1, 2, tzinfo=UTC),
                    "worked_callsign": "C1",
                    "band": "20m",
                    "transmitter": "A",
                },
            ],
        }
    )
    rule = OperatingConstraintRule.model_validate(
        {
            "kind": "operating_constraints",
            "max_operating_minutes": 10,
            "operating_session_gap_minutes": 30,
            "minimum_off_time_minutes": 100,
            "required_off_periods": 1,
            "off_period_gap_minutes": 60,
            "maximum_band_changes": 1,
            "band_change_window_minutes": 200,
            "minimum_band_dwell_minutes": 30,
            "maximum_transmitters": 1,
            "declaration_fields": ["transmitter_count"],
        }
    )
    findings = evaluate_operating_constraints(
        rule,
        entry,
        contest_starts_at=START,
        contest_ends_at=datetime(2026, 1, 1, 3, tzinfo=UTC),
    )
    assert {finding.code for finding in findings} == {
        "maximum_operating_time_exceeded",
        "band_change_limit_exceeded",
        "minimum_band_dwell_not_met",
        "declaration_review:transmitter_count",
    }


def test_score_formula_rejects_negative_final_score_and_divide_by_zero():
    payload = valid_payload()
    formula = next(item for item in payload["rules"] if item["id"] == "score")["rule"]
    formula["steps"] = [{"operator": "subtract", "operand": {"constant": 999}}]
    with pytest.raises(RuleExecutionError, match="negative result"):
        score_entry(
            validate_ruleset(payload), sample_entry(), contest_starts_at=START, contest_ends_at=END
        )

    formula["steps"] = [{"operator": "floor_divide", "operand": {"constant": 0}}]
    with pytest.raises(RulesetValidationError):
        validate_ruleset(payload)
