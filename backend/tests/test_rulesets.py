import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError

from backend.app.main import app
from backend.app.models import RulesetVersion
from backend.app.rulesets.checks import validate_categories, validate_exchange
from backend.app.rulesets.conditions import evaluate_condition
from backend.app.rulesets.engine import RuleExecutionError, ScoringEntry, score_entry
from backend.app.rulesets.operating import evaluate_operating_constraints
from backend.app.rulesets.persistence import load_ruleset_version, save_ruleset_version
from backend.app.rulesets.schema import (
    BonusRule,
    CategoryRule,
    Condition,
    ExchangeRule,
    OperatingConstraintRule,
    RulesetDefinition,
    SubmissionRule,
)
from backend.app.rulesets.submission import (
    classify_submission,
)
from backend.app.rulesets.summary import summarize_ruleset
from backend.app.rulesets.validation import RulesetValidationError, validate_ruleset
from backend.app.scheduling import Recurrence, resolve_contest_schedule

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
                "id": "submission",
                "rule": {
                    "kind": "submission",
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
                "rule": {
                    "kind": "format_mapping",
                    "format": "cabrillo",
                    "qso_columns": [
                        "frequency",
                        "mode",
                        "date",
                        "time",
                        "callsign_sent",
                        "rst_sent",
                        "exchange_sent",
                        "callsign_received",
                        "rst_received",
                        "exchange_received",
                    ],
                    "category_mappings": [
                        {
                            "external_value": "SINGLE-OP",
                            "category_values": {"operator": "single"},
                        }
                    ],
                },
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
        "submission",
        "categories",
        "exchange",
        "eligibility",
        "duplicates",
        "points",
        "distance_points",
        "multiplier",
        "bonus",
        "penalty",
        "score_formula",
        "operating_constraints",
        "format_mapping",
        "workflow_hook",
    }
    assert "eval" not in str(catalog)
    assert "schedule" not in {item["key"] for item in catalog}


def test_ruleset_summary_includes_contest_specific_category_explanations():
    payload = valid_payload()
    categories = next(item for item in payload["rules"] if item["id"] == "categories")
    dimension = categories["rule"]["dimensions"][0]
    dimension["description"] = "Operators may rotate at the station."
    dimension["choices"][0]["description"] = "One operator may transmit at a time."

    summary = summarize_ruleset(validate_ruleset(payload))

    assert "Operators may rotate at the station." in summary
    assert "Single operator — One operator may transmit at a time." in summary


def _distance_ruleset_payload():
    payload = valid_payload()
    exchange = next(item for item in payload["rules"] if item["id"] == "exchange")["rule"]
    exchange["fields"].append(
        {
            "key": "grid",
            "label": "Locator",
            "value_type": "grid",
            "direction": "received",
            "required": False,
        }
    )
    payload["rules"].append(
        {
            "id": "distance",
            "rule": {
                "kind": "distance_points",
                "grid_field": "grid",
                "precision": 6,
                "points_per_kilometer": 1,
                "same_grid_points": 1,
            },
        }
    )
    return payload


def _single_grid_qso_entry(worked_grid: str | None) -> ScoringEntry:
    qso = (
        sample_entry()
        .qsos[1]
        .model_copy(
            update={
                "received_exchange": {
                    "serial": "8",
                    **({"grid": worked_grid} if worked_grid else {}),
                }
            }
        )
    )
    return sample_entry().model_copy(update={"station_grid": "IO91AA", "qsos": [qso]})


def test_distance_points_score_same_locator_and_commenced_kilometer_integer_values():
    definition = validate_ruleset(_distance_ruleset_payload())

    same_grid = score_entry(
        definition,
        _single_grid_qso_entry("IO91AA"),
        contest_starts_at=START,
        contest_ends_at=END,
    )
    adjacent_subsquare = score_entry(
        definition,
        _single_grid_qso_entry("IO91AB"),
        contest_starts_at=START,
        contest_ends_at=END,
    )

    assert same_grid.qso_scores[0].points == 3
    assert same_grid.qso_scores[0].reasons[-1] == "distance_points:distance:0km:1"
    assert adjacent_subsquare.qso_scores[0].points == 7
    assert adjacent_subsquare.qso_scores[0].reasons[-1] == "distance_points:distance:5km:5"
    assert type(adjacent_subsquare.points_total) is int

    qso_location = (
        _single_grid_qso_entry("IO91AA")
        .qsos[0]
        .model_copy(update={"sent_exchange": {"serial": "1", "grid": "IO91AA"}})
    )
    per_qso_location = score_entry(
        definition,
        sample_entry().model_copy(update={"station_grid": None, "qsos": [qso_location]}),
        contest_starts_at=START,
        contest_ends_at=END,
    )
    assert per_qso_location.qso_scores[0].points == 3


@pytest.mark.parametrize(
    ("station_grid", "worked_grid", "action", "expected_status"),
    [
        (None, "IO91AA", "needs_review", "needs_review"),
        ("IO91AA", "bad-grid", "needs_review", "needs_review"),
        ("IO91AA", None, "not_credited", "not_credited"),
    ],
)
def test_distance_points_missing_or_invalid_grid_has_explicit_outcome(
    station_grid, worked_grid, action, expected_status
):
    payload = _distance_ruleset_payload()
    distance = next(item for item in payload["rules"] if item["id"] == "distance")["rule"]
    distance["missing_grid_action"] = action
    entry = _single_grid_qso_entry(worked_grid).model_copy(update={"station_grid": station_grid})

    result = score_entry(
        validate_ruleset(payload), entry, contest_starts_at=START, contest_ends_at=END
    )

    assert result.qso_scores[0].status == expected_status
    assert result.qso_scores[0].points == 0
    assert "distance_grid_missing_or_invalid:distance" in result.qso_scores[0].reasons


def test_distance_points_rule_requires_a_received_grid_exchange_field():
    payload = _distance_ruleset_payload()
    exchange = next(item for item in payload["rules"] if item["id"] == "exchange")["rule"]
    exchange["fields"] = [field for field in exchange["fields"] if field["key"] != "grid"]

    with pytest.raises(RulesetValidationError) as exc_info:
        validate_ruleset(payload)
    assert "undefined received grid exchange field" in str(exc_info.value.errors)


def test_validation_endpoint_returns_summary_and_integer_worked_example():
    response = TestClient(app).post("/api/v1/rulesets/validate", json=valid_payload())

    assert response.status_code == 200
    result = response.json()
    assert result["valid"] is True
    assert result["ruleset_key"] == "sample-sprint"
    assert "schedule" not in result["summary"].lower()
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


def test_validation_endpoint_reports_import_conflicts_with_field_paths():
    payload = valid_payload()
    format_rule = next(item["rule"] for item in payload["rules"] if item["id"] == "format")
    format_rule["qso_columns"] = ["mode", "frequency", *format_rule["qso_columns"][2:-1]]
    format_rule["category_mappings"] = []

    response = TestClient(app).post("/api/v1/rulesets/validate", json=payload)

    assert response.status_code == 422
    details = response.json()["error"]["details"]
    assert any(
        detail["location"][-1] == "qso_columns" and "WWROF" in detail["message"]
        for detail in details
    )
    assert any(
        detail["location"][-1] == "category_mappings" and "operator" in detail["message"]
        for detail in details
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


def test_ruleset_can_enable_multiple_distinct_log_formats_only_once_each():
    payload = valid_payload()
    payload["rules"].append(
        {
            "id": "adif-format",
            "rule": {
                "kind": "format_mapping",
                "format": "adif",
                "category_mappings": [
                    {"external_value": "SINGLE-OP", "category_values": {"operator": "single"}}
                ],
            },
        }
    )
    assert validate_ruleset(payload).ruleset_key == "sample-sprint"

    payload["rules"].append(
        {"id": "adif-format-again", "rule": {"kind": "format_mapping", "format": "adif"}}
    )
    with pytest.raises(RulesetValidationError) as error:
        validate_ruleset(payload)
    assert any("only once" in str(issue["message"]) for issue in error.value.errors)


def test_ruleset_validation_accepts_wwrof_fields_in_contest_template_order():
    payload = valid_payload()
    format_rule = next(item["rule"] for item in payload["rules"] if item["id"] == "format")
    original_columns = format_rule["qso_columns"]
    format_rule["qso_columns"] = ["mode", "frequency", *original_columns[2:]]

    assert validate_ruleset(payload).ruleset_key == "sample-sprint"


def test_ruleset_validation_rejects_cabrillo_columns_missing_required_fields():
    payload = valid_payload()
    format_rule = next(item["rule"] for item in payload["rules"] if item["id"] == "format")
    format_rule["qso_columns"] = format_rule["qso_columns"][:-1]

    with pytest.raises(RulesetValidationError) as error:
        validate_ruleset(payload)

    assert any(
        issue["path"].endswith("qso_columns") and "required WWROF field" in issue["message"]
        for issue in error.value.errors
    )


def test_ruleset_validation_rejects_omitted_cabrillo_qso_columns():
    payload = valid_payload()
    format_rule = next(item["rule"] for item in payload["rules"] if item["id"] == "format")
    format_rule["qso_columns"] = []

    with pytest.raises(RulesetValidationError) as error:
        validate_ruleset(payload)

    assert any(
        issue["path"].endswith("qso_columns")
        and "explicitly include" in issue["message"]
        and "WWROF field" in issue["message"]
        for issue in error.value.errors
    )


def test_format_mapping_rejects_duplicate_qso_columns_at_schema_boundary():
    payload = valid_payload()
    format_rule = next(item["rule"] for item in payload["rules"] if item["id"] == "format")
    format_rule["qso_columns"].append("frequency")

    with pytest.raises(ValidationError, match="duplicate fields"):
        RulesetDefinition.model_validate(payload)


def test_format_mapping_rejects_non_wwrof_category_values():
    payload = valid_payload()
    format_rule = next(item["rule"] for item in payload["rules"] if item["id"] == "format")
    format_rule["category_mappings"][0]["external_value"] = "SINGLE OPERATOR"

    with pytest.raises(ValidationError):
        RulesetDefinition.model_validate(payload)


def test_format_mapping_reports_duplicate_category_values_within_the_same_tag():
    payload = valid_payload()
    format_rule = next(item["rule"] for item in payload["rules"] if item["id"] == "format")
    duplicate = format_rule["category_mappings"][0].copy()
    duplicate["category_values"] = {"operator": "multi_operator"}
    format_rule["category_mappings"].append(duplicate)

    with pytest.raises(
        ValidationError,
        match="SINGLE-OP.*CATEGORY-OPERATOR.*case-insensitive",
    ):
        RulesetDefinition.model_validate(payload)


def test_format_mapping_binds_category_values_to_the_selected_wwrof_header():
    payload = valid_payload()
    format_rule = next(item["rule"] for item in payload["rules"] if item["id"] == "format")
    format_rule["category_mappings"][0]["external_field"] = "CATEGORY-POWER"

    with pytest.raises(ValidationError, match="not a valid WWROF value"):
        RulesetDefinition.model_validate(payload)


def test_format_mapping_destinations_must_be_declared_contest_dimension_choices():
    payload = valid_payload()
    format_rule = next(item["rule"] for item in payload["rules"] if item["id"] == "format")

    format_rule["category_mappings"][0]["category_values"] = {"operator": "unconfigured"}
    with pytest.raises(RulesetValidationError) as error:
        validate_ruleset(payload)
    assert any(
        "Unknown category value operator=unconfigured" in str(issue["message"])
        for issue in error.value.errors
    )

    format_rule["category_mappings"][0]["category_values"] = {"unconfigured_dimension": "single"}
    with pytest.raises(RulesetValidationError) as error:
        validate_ruleset(payload)
    assert any(
        "Unknown category value unconfigured_dimension=single" in str(issue["message"])
        for issue in error.value.errors
    )


def test_ruleset_persistence_rejects_omitted_cabrillo_qso_columns_before_saving():
    payload = valid_payload()
    format_rule = next(item["rule"] for item in payload["rules"] if item["id"] == "format")
    format_rule["qso_columns"] = []
    definition = RulesetDefinition.model_validate(payload)

    with pytest.raises(RulesetValidationError):
        save_ruleset_version(None, definition, created_by_user_id=None)


def test_ruleset_validation_accepts_optional_transmitter_column_after_required_fields():
    payload = valid_payload()
    format_rule = next(item["rule"] for item in payload["rules"] if item["id"] == "format")
    format_rule["qso_columns"].append("transmitter")

    assert validate_ruleset(payload).ruleset_key == "sample-sprint"


@pytest.mark.parametrize(
    "columns",
    [
        [
            "frequency",
            "mode",
            "date",
            "time",
            "callsign_sent",
            "rst_sent",
            "exchange_sent",
            "callsign_received",
            "rst_received",
            "exchange_received",
            "transmitter",
            "band",
        ],
        [
            "frequency",
            "mode",
            "date",
            "time",
            "callsign_sent",
            "rst_sent",
            "exchange_sent",
            "callsign_received",
            "rst_received",
            "exchange_received",
            "transmitter",
            "transmitter",
        ],
        [
            "frequency",
            "mode",
            "date",
            "time",
            "callsign_sent",
            "rst_sent",
            "exchange_sent",
            "callsign_received",
            "rst_received",
            "transmitter",
            "exchange_received",
        ],
    ],
)
def test_ruleset_validation_rejects_unsupported_or_duplicate_cabrillo_columns(columns):
    payload = valid_payload()
    format_rule = next(item["rule"] for item in payload["rules"] if item["id"] == "format")
    format_rule["qso_columns"] = columns

    with pytest.raises(RulesetValidationError) as error:
        validate_ruleset(payload)

    assert any(issue["path"].endswith("qso_columns") for issue in error.value.errors)


def test_ruleset_validation_rejects_required_categories_not_mapped_for_an_import_format():
    payload = valid_payload()
    format_rule = next(item["rule"] for item in payload["rules"] if item["id"] == "format")
    format_rule["category_mappings"] = []

    with pytest.raises(RulesetValidationError) as error:
        validate_ruleset(payload)

    assert any(
        issue["path"].endswith("category_mappings") and "operator" in issue["message"]
        for issue in error.value.errors
    )


def test_legacy_import_mapping_conflict_can_be_loaded_but_not_revalidated_for_save():
    payload = valid_payload()
    format_rule = next(item["rule"] for item in payload["rules"] if item["id"] == "format")
    format_rule["category_mappings"] = []

    loaded_definition = validate_ruleset(payload, check_import_mapping_consistency=False)
    assert loaded_definition.ruleset_key == "sample-sprint"
    stored = RulesetVersion(
        ruleset_key="sample-sprint",
        version="2026",
        source_url="https://example.test/rules/2026",
        source_edition="2026 edition",
        rule_type_keys=sorted({item["rule"]["kind"] for item in payload["rules"]}),
        configuration=payload,
    )
    assert load_ruleset_version(stored).ruleset_key == "sample-sprint"
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


def test_contest_recurrence_is_resolved_in_utc_from_configured_duration():
    recurrence = Recurrence.model_validate({"frequency": "first_full_weekend", "month": 1})
    resolved = resolve_contest_schedule(
        recurrence,
        2025,
        datetime(2026, 1, 1, 8, tzinfo=UTC),
        datetime(2026, 1, 1, 9, 30, tzinfo=UTC),
    )
    assert resolved.starts_at == datetime(2025, 1, 4, 8, tzinfo=UTC)
    assert resolved.ends_at == datetime(2025, 1, 4, 9, 30, tzinfo=UTC)

    annual = Recurrence.model_validate({"frequency": "annual_date", "month": 10, "day": 26})
    resolved = resolve_contest_schedule(
        annual,
        2025,
        datetime(2026, 1, 1, 2, 30, tzinfo=UTC),
        datetime(2026, 1, 1, 3, 30, tzinfo=UTC),
    )
    assert resolved.starts_at == datetime(2025, 10, 26, 2, 30, tzinfo=UTC)


def test_contest_schedule_preview_api_uses_contest_configuration():
    response = TestClient(app).post(
        "/api/v1/contests/schedule-preview",
        json={
            "year": 2026,
            "starts_at": "2026-01-01T08:00:00Z",
            "ends_at": "2026-01-01T09:30:00Z",
            "periodicity": {"frequency": "first_full_weekend", "month": 1},
        },
    )
    assert response.status_code == 200
    assert response.json() == {
        "starts_at": "2026-01-03T08:00:00Z",
        "ends_at": "2026-01-03T09:30:00Z",
        "occurrences": [
            {"starts_at": "2026-01-03T08:00:00Z", "ends_at": "2026-01-03T09:30:00Z"},
            {"starts_at": "2027-01-02T08:00:00Z", "ends_at": "2027-01-02T09:30:00Z"},
            {"starts_at": "2028-01-01T08:00:00Z", "ends_at": "2028-01-01T09:30:00Z"},
            {"starts_at": "2029-01-06T08:00:00Z", "ends_at": "2029-01-06T09:30:00Z"},
            {"starts_at": "2030-01-05T08:00:00Z", "ends_at": "2030-01-05T09:30:00Z"},
        ],
    }
    invalid = TestClient(app).post(
        "/api/v1/contests/schedule-preview",
        json={
            "year": 2026,
            "starts_at": "2026-01-01T08:00:00Z",
            "ends_at": "2026-01-01T09:30:00Z",
            "periodicity": {"frequency": "annual_date", "month": 2, "day": 30},
        },
    )
    assert invalid.status_code == 422


def test_contest_schedule_preview_supports_multiple_months_and_weekdays():
    response = TestClient(app).post(
        "/api/v1/contests/schedule-preview",
        json={
            "year": 2026,
            "starts_at": "2026-01-09T08:00:00Z",
            "ends_at": "2026-01-09T09:00:00Z",
            "periodicity": {
                "frequency": "nth_weekday",
                "month": [1, 3],
                "weekday": [0, 4],
                "occurrence": 2,
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["starts_at"] == "2026-01-09T08:00:00Z"
    assert [item["starts_at"] for item in response.json()["occurrences"]] == [
        "2026-01-09T08:00:00Z",
        "2026-01-12T08:00:00Z",
        "2026-03-09T08:00:00Z",
        "2026-03-13T08:00:00Z",
        "2027-01-08T08:00:00Z",
    ]


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


def test_submission_rule_owns_late_policy_while_cutoff_is_contest_configuration():
    submission = SubmissionRule.model_validate(
        {
            "kind": "submission",
            "late_policy": "accept_late",
            "manager_extension_allowed": True,
        }
    )
    cutoff = datetime(2026, 1, 5, tzinfo=UTC)
    assert classify_submission(cutoff, cutoff, submission.late_policy) == "on_time"
    assert (
        classify_submission(
            datetime(2026, 1, 6, tzinfo=UTC),
            cutoff,
            submission.late_policy,
            manager_extension_until=datetime(2026, 1, 7, tzinfo=UTC),
            manager_extension_allowed=submission.manager_extension_allowed,
        )
        == "on_time"
    )
    with pytest.raises(ValueError, match="does not allow"):
        classify_submission(
            datetime(2026, 1, 6, tzinfo=UTC),
            cutoff,
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


def test_duplicate_qso_can_supply_multiplier_without_points():
    payload = valid_payload()
    duplicate_rule = next(item for item in payload["rules"] if item["id"] == "duplicates")
    duplicate_rule["rule"]["count_for_multipliers"] = True
    entry = sample_entry()
    second_qso = entry.qsos[1].model_copy(update={"entity": "VE"})
    entry = entry.model_copy(update={"qsos": [entry.qsos[0], second_qso]})

    result = score_entry(
        validate_ruleset(payload), entry, contest_starts_at=START, contest_ends_at=END
    )

    duplicate_score = next(item for item in result.qso_scores if item.qso_id == 2)
    assert duplicate_score.status == "not_credited"
    assert duplicate_score.points == 0
    assert len(duplicate_score.multiplier_keys) == 1
    assert result.points_total == 2
    assert result.multiplier_count == 2


def test_credit_override_does_not_award_points_or_bonus_to_duplicate_qso():
    payload = valid_payload()
    duplicate_rule = next(item for item in payload["rules"] if item["id"] == "duplicates")
    duplicate_rule["rule"]["count_for_multipliers"] = True
    bonus_rule = next(item for item in payload["rules"] if item["id"] == "entry-bonus")
    bonus_rule["rule"]["basis"] = "per_eligible_qso"
    entry = sample_entry()
    second_qso = entry.qsos[1].model_copy(update={"entity": "VE"})
    entry = entry.model_copy(update={"qsos": [entry.qsos[0], second_qso]})

    result = score_entry(
        validate_ruleset(payload),
        entry,
        contest_starts_at=START,
        contest_ends_at=END,
        qso_overrides={2: {"status": "credited"}},
    )

    duplicate_score = next(item for item in result.qso_scores if item.qso_id == 2)
    assert duplicate_score.status == "credited"
    assert duplicate_score.points == 0
    assert duplicate_score.bonus_points == 0
    assert len(duplicate_score.multiplier_keys) == 1
    assert result.points_total == 2
    assert result.bonus_points == 5
    assert result.multiplier_count == 2


def test_duplicate_multiplier_option_does_not_bypass_other_eligibility_rules():
    payload = valid_payload()
    duplicate_rule = next(item for item in payload["rules"] if item["id"] == "duplicates")
    duplicate_rule["rule"]["count_for_multipliers"] = True
    eligibility_rule = next(item for item in payload["rules"] if item["id"] == "eligibility")
    eligibility_rule["rule"]["allowed_modes"] = ["SSB"]
    entry = sample_entry()
    second_qso = entry.qsos[1].model_copy(update={"entity": "VE"})
    entry = entry.model_copy(update={"qsos": [entry.qsos[0], second_qso]})

    result = score_entry(
        validate_ruleset(payload), entry, contest_starts_at=START, contest_ends_at=END
    )

    assert result.points_total == 0
    assert result.multiplier_count == 0
    assert all(not item.multiplier_keys for item in result.qso_scores)


def test_every_matching_duplicate_rule_must_allow_multiplier_credit():
    payload = valid_payload()
    duplicate_rule = next(item for item in payload["rules"] if item["id"] == "duplicates")
    duplicate_rule["rule"]["count_for_multipliers"] = True
    payload["rules"].append(
        {
            "id": "duplicates-by-mode",
            "rule": {
                "kind": "duplicates",
                "scope": ["worked_callsign", "mode"],
                "effect": "not_credited",
                "count_for_multipliers": False,
            },
        }
    )
    entry = sample_entry()
    second_qso = entry.qsos[1].model_copy(update={"entity": "VE"})
    entry = entry.model_copy(update={"qsos": [entry.qsos[0], second_qso]})

    result = score_entry(
        validate_ruleset(payload), entry, contest_starts_at=START, contest_ends_at=END
    )

    assert result.points_total == 2
    assert result.multiplier_count == 1
    assert next(item for item in result.qso_scores if item.qso_id == 2).multiplier_keys == []


@pytest.mark.parametrize(
    ("station_continent", "expected_points"),
    [("EU", 2), ("NA", 0), (None, 0)],
)
def test_station_geography_condition_is_explicit_and_missing_data_does_not_match(
    station_continent, expected_points
):
    payload = valid_payload()
    point_rule = next(item for item in payload["rules"] if item["id"] == "points")
    point_rule["when"] = {
        "kind": "compare",
        "fact": "station.continent",
        "operator": "eq",
        "value": "EU",
    }
    entry = sample_entry().model_copy(update={"station_continent": station_continent})

    result = score_entry(
        validate_ruleset(payload), entry, contest_starts_at=START, contest_ends_at=END
    )

    assert result.points_total == expected_points


@pytest.mark.parametrize(
    ("station_entity", "station_continent", "worked_entity", "worked_continent", "expected"),
    [
        ("EA", "EU", "EA", "EU", 2),
        ("EA", "EU", "F", "EU", 0),
        ("EA", "EU", "K", "NA", 0),
        (None, "EU", "EA", "EU", 0),
        ("EA", None, "K", "NA", 0),
    ],
)
def test_relative_geography_predicates_compare_pinned_entry_and_worked_facts(
    station_entity, station_continent, worked_entity, worked_continent, expected
):
    payload = valid_payload()
    point_rule = next(item for item in payload["rules"] if item["id"] == "points")
    point_rule["when"] = {
        "kind": "compare",
        "fact": "qso.same_entity",
        "operator": "eq",
        "value": True,
    }
    entry = sample_entry().model_copy(
        update={
            "station_entity": station_entity,
            "station_continent": station_continent,
            "qsos": [
                sample_entry()
                .qsos[0]
                .model_copy(update={"entity": worked_entity, "continent": worked_continent})
            ],
        }
    )

    result = score_entry(
        validate_ruleset(payload), entry, contest_starts_at=START, contest_ends_at=END
    )

    assert result.points_total == expected


@pytest.mark.parametrize(
    ("fact", "station_continent", "worked_continent", "expected"),
    [
        ("qso.same_continent", "EU", "EU", 2),
        ("qso.same_continent", "EU", "NA", 0),
        ("qso.different_continent", "EU", "NA", 2),
        ("qso.different_continent", "EU", "EU", 0),
        ("qso.different_continent", None, "NA", 0),
    ],
)
def test_relative_continent_predicates_handle_equal_different_and_unknown(
    fact, station_continent, worked_continent, expected
):
    payload = valid_payload()
    point_rule = next(item for item in payload["rules"] if item["id"] == "points")
    point_rule["when"] = {
        "kind": "compare",
        "fact": fact,
        "operator": "eq",
        "value": True,
    }
    entry = sample_entry().model_copy(
        update={
            "station_continent": station_continent,
            "qsos": [sample_entry().qsos[0].model_copy(update={"continent": worked_continent})],
        }
    )

    result = score_entry(
        validate_ruleset(payload), entry, contest_starts_at=START, contest_ends_at=END
    )

    assert result.points_total == expected


def test_station_geography_can_be_used_as_a_multiplier_source():
    payload = valid_payload()
    payload["rules"].append(
        {
            "id": "entrant-entity-multiplier",
            "rule": {
                "kind": "multiplier",
                "source_fact": "station.entity",
                "scope": "contest",
                "label": "Entrant entity",
            },
        }
    )
    entry = sample_entry().model_copy(update={"station_entity": "EA"})

    result = score_entry(
        validate_ruleset(payload), entry, contest_starts_at=START, contest_ends_at=END
    )

    assert result.multiplier_count == 2
    assert "entrant-entity-multiplier:*:EA" in result.qso_scores[0].multiplier_keys


def test_formula_can_combine_independent_multiplier_rule_counts():
    payload = valid_payload()
    payload["rules"].extend(
        [
            {
                "id": "mode-count",
                "rule": {
                    "kind": "multiplier",
                    "source_fact": "qso.mode",
                    "scope": "contest",
                    "label": "Mode",
                },
            },
            {
                "id": "country-count",
                "rule": {
                    "kind": "multiplier",
                    "source_fact": "qso.entity",
                    "scope": "contest",
                    "label": "Country",
                },
            },
        ]
    )
    formula = next(item for item in payload["rules"] if item["id"] == "score")
    formula["rule"] = {
        "kind": "score_formula",
        "start": {"variable": "points_total"},
        "steps": [
            {"operator": "multiply", "operand": {"variable": "multiplier.country-count"}},
            {"operator": "add", "operand": {"variable": "multiplier.mode-count"}},
        ],
    }
    first, second = sample_entry().qsos
    entry = sample_entry().model_copy(
        update={
            "qsos": [
                first,
                second.model_copy(
                    update={
                        "worked_callsign": "VE3XYZ",
                        "entity": "VE",
                        "mode": "SSB",
                    }
                ),
            ]
        }
    )

    result = score_entry(
        validate_ruleset(payload), entry, contest_starts_at=START, contest_ends_at=END
    )

    assert result.multiplier_counts == {
        "entity-multiplier": 2,
        "mode-count": 2,
        "country-count": 2,
    }
    assert result.multiplier_count == 6
    assert result.final_score == 10
    assert "Multiplier country-count: 2." in result.explanation
    assert "Multiplier mode-count: 2." in result.explanation


def test_formula_rejects_unknown_multiplier_rule_reference():
    payload = valid_payload()
    formula = next(item for item in payload["rules"] if item["id"] == "score")
    formula["rule"] = {
        "kind": "score_formula",
        "start": {"variable": "multiplier.unknown"},
        "steps": [],
    }

    with pytest.raises(RulesetValidationError) as error:
        validate_ruleset(payload)
    assert any(
        "unknown multiplier rule ID unknown" in item["message"] for item in error.value.errors
    )


def test_conditionally_inactive_multiplier_has_zero_named_count():
    payload = valid_payload()
    payload["rules"].append(
        {
            "id": "inactive-multiplier",
            "rule": {
                "kind": "multiplier",
                "source_fact": "qso.entity",
                "scope": "contest",
                "label": "Inactive",
            },
            "when": {
                "kind": "compare",
                "fact": "qso.band",
                "operator": "eq",
                "value": "10m",
            },
        }
    )
    formula = next(item for item in payload["rules"] if item["id"] == "score")
    formula["rule"] = {
        "kind": "score_formula",
        "start": {"variable": "multiplier.inactive-multiplier"},
        "steps": [],
    }

    result = score_entry(
        validate_ruleset(payload), sample_entry(), contest_starts_at=START, contest_ends_at=END
    )

    assert result.multiplier_counts["inactive-multiplier"] == 0
    assert result.final_score == 0


def test_formula_example_supplies_sample_values_for_named_multiplier_counts():
    from backend.app.rulesets.summary import worked_score_example

    payload = valid_payload()
    formula = next(item for item in payload["rules"] if item["id"] == "score")
    formula["rule"] = {
        "kind": "score_formula",
        "start": {"variable": "multiplier.entity-multiplier"},
        "steps": [],
    }
    definition = validate_ruleset(payload)

    example = worked_score_example(definition)

    assert example["variables"]["multiplier.entity-multiplier"] == 1
    assert example["final_score"] == 1


@pytest.mark.parametrize(
    ("scope", "expected"),
    [
        ("contest", 2),
        ("band", 3),
        ("mode", 3),
        ("band_mode", 4),
        ("grid", 2),
        ("transmitter", 3),
    ],
)
def test_multiplier_scope_counts_again_at_exact_scope_boundary(scope, expected):
    payload = valid_payload()
    multiplier = next(item for item in payload["rules"] if item["id"] == "entity-multiplier")
    multiplier["rule"]["scope"] = scope
    exchange = next(item for item in payload["rules"] if item["id"] == "exchange")
    exchange["rule"]["fields"].append(
        {
            "key": "grid",
            "label": "Grid",
            "value_type": "grid",
            "direction": "both",
            "required": False,
        }
    )
    format_rule = next(item for item in payload["rules"] if item["id"] == "format")
    format_rule["rule"]["qso_columns"].append("transmitter")
    entry = ScoringEntry(
        entry_id=1,
        station_callsign="N0CALL",
        categories={"operator": "single"},
        declarations={"section": "EMA"},
        qsos=[
            {
                "qso_id": 1,
                "occurred_at": START,
                "worked_callsign": "K1AAA",
                "band": "20m",
                "mode": "CW",
                "entity": "K",
                "grid": "FN31",
                "transmitter": "1",
                "sent_exchange": {"serial": 1},
                "received_exchange": {"serial": 1, "grid": "FN31"},
            },
            {
                "qso_id": 2,
                "occurred_at": START,
                "worked_callsign": "K1BBB",
                "band": "20m",
                "mode": "SSB",
                "entity": "K",
                "grid": "FN31",
                "transmitter": "2",
                "sent_exchange": {"serial": 2},
                "received_exchange": {"serial": 2, "grid": "FN31"},
            },
            {
                "qso_id": 3,
                "occurred_at": START,
                "worked_callsign": "K1CCC",
                "band": "40m",
                "mode": "CW",
                "entity": "K",
                "grid": "FN31",
                "transmitter": "1",
                "sent_exchange": {"serial": 3},
                "received_exchange": {"serial": 3, "grid": "FN31"},
            },
            {
                "qso_id": 4,
                "occurred_at": START,
                "worked_callsign": "VE3DDD",
                "band": "20m",
                "mode": "CW",
                "entity": "VE",
                "grid": "FN42",
                "transmitter": "1",
                "sent_exchange": {"serial": 4},
                "received_exchange": {"serial": 4, "grid": "FN42"},
            },
        ],
    )

    result = score_entry(
        validate_ruleset(payload), entry, contest_starts_at=START, contest_ends_at=END
    )

    assert result.multiplier_count == expected
    assert all(item.status == "credited" for item in result.qso_scores)


def test_missing_multiplier_value_withholds_all_keys_for_that_qso():
    payload = valid_payload()
    payload["rules"].append(
        {
            "id": "zone-multiplier",
            "rule": {
                "kind": "multiplier",
                "source_fact": "qso.cq_zone",
                "scope": "contest",
                "label": "CQ zone",
            },
        }
    )

    result = score_entry(
        validate_ruleset(payload),
        sample_entry(),
        contest_starts_at=START,
        contest_ends_at=END,
    )

    assert result.outcome == "needs_review"
    assert result.multiplier_count == 0
    assert all(not item.multiplier_keys for item in result.qso_scores)


@pytest.mark.parametrize(
    ("source_fact", "scope", "expected_message"),
    [
        ("qso.grid", "band", "received or bidirectional grid exchange field"),
        ("qso.entity", "grid", "Grid multiplier scope requires"),
        ("qso.transmitter", "contest", "transmitter QSO column"),
        ("qso.entity", "transmitter", "Transmitter multiplier scope requires"),
    ],
)
def test_multiplier_validation_rejects_unavailable_data_sources(
    source_fact, scope, expected_message
):
    payload = valid_payload()
    multiplier = next(item for item in payload["rules"] if item["id"] == "entity-multiplier")
    multiplier["rule"]["source_fact"] = source_fact
    multiplier["rule"]["scope"] = scope

    with pytest.raises(RulesetValidationError) as exc_info:
        validate_ruleset(payload)

    assert expected_message in str(exc_info.value.errors)


def test_multiplier_validation_accepts_data_available_in_every_enabled_format():
    grid_payload = valid_payload()
    grid_multiplier = next(
        item for item in grid_payload["rules"] if item["id"] == "entity-multiplier"
    )
    grid_multiplier["rule"].update(source_fact="qso.grid", scope="grid")
    exchange = next(item for item in grid_payload["rules"] if item["id"] == "exchange")
    exchange["rule"]["fields"].append(
        {
            "key": "grid",
            "label": "Grid",
            "value_type": "grid",
            "direction": "received",
            "required": False,
        }
    )
    validate_ruleset(grid_payload)

    transmitter_payload = valid_payload()
    transmitter_multiplier = next(
        item for item in transmitter_payload["rules"] if item["id"] == "entity-multiplier"
    )
    transmitter_multiplier["rule"].update(source_fact="qso.transmitter", scope="transmitter")
    format_rule = next(item for item in transmitter_payload["rules"] if item["id"] == "format")
    format_rule["rule"]["qso_columns"].append("transmitter")
    validate_ruleset(transmitter_payload)

    unsupported_combination = json.loads(json.dumps(transmitter_payload))
    cabrillo_format = next(
        item for item in unsupported_combination["rules"] if item["id"] == "format"
    )
    adif_format = json.loads(json.dumps(cabrillo_format))
    adif_format["id"] = "format-adif"
    adif_format["rule"]["format"] = "adif"
    adif_format["rule"]["qso_columns"] = []
    unsupported_combination["rules"].append(adif_format)

    with pytest.raises(RulesetValidationError) as exc_info:
        validate_ruleset(unsupported_combination)

    assert "Cabrillo as every accepted log format" in str(exc_info.value.errors)


def test_ruleset_validation_api_returns_multiplier_availability_error():
    payload = valid_payload()
    multiplier = next(item for item in payload["rules"] if item["id"] == "entity-multiplier")
    multiplier["rule"]["source_fact"] = "qso.grid"

    response = TestClient(app).post("/api/v1/rulesets/validate", json=payload)

    assert response.status_code == 422
    assert "qso.grid multiplier requires" in response.text


def test_multiplier_conditions_exclude_cq_ww_maritime_mobile_entity_credit():
    payload = valid_payload()
    multiplier = next(item for item in payload["rules"] if item["id"] == "entity-multiplier")
    multiplier["when"] = {
        "kind": "not",
        "condition": {
            "kind": "compare",
            "fact": "qso.worked_callsign",
            "operator": "matches",
            "value": ".*/MM",
        },
    }
    entry = sample_entry()
    maritime_qso = entry.qsos[1].model_copy(update={"worked_callsign": "EA1ABC/MM", "entity": "EA"})
    entry = entry.model_copy(update={"qsos": [entry.qsos[0], maritime_qso]})

    result = score_entry(
        validate_ruleset(payload), entry, contest_starts_at=START, contest_ends_at=END
    )

    assert result.multiplier_count == 1
    maritime_score = next(item for item in result.qso_scores if item.qso_id == maritime_qso.qso_id)
    assert maritime_score.status == "credited"
    assert maritime_score.multiplier_keys == []


def test_cq_ww_draft_entity_multipliers_exclude_maritime_mobile():
    from pathlib import Path

    drafts = Path(__file__).parents[2] / "documentation" / "ruleset-drafts"
    for name in ("cq-ww-cw.json", "cq-ww-ssb.json", "cq-ww-rtty.json"):
        payload = json.loads((drafts / name).read_text())
        definition = validate_ruleset(payload)
        entity_multiplier = next(item for item in definition.rules if item.id == "multiplier-2")
        assert entity_multiplier.rule.source_fact == "qso.entity"
        assert entity_multiplier.rule.scope == "band"
        assert entity_multiplier.when is not None


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
