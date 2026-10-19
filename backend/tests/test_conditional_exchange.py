from datetime import UTC, datetime

from backend.app.adjudication.scoring import _exchange_schema_for_qso, _exchange_values
from backend.app.logs.api import _parse_log
from backend.app.logs.cabrillo import DEFAULT_QSO_COLUMNS, parse_cabrillo
from backend.app.rulesets.engine import ScoringEntry, ScoringQso
from backend.app.rulesets.schema import ConfiguredRule
from backend.app.rulesets.validation import RulesetValidationError, validate_ruleset
from backend.tests.test_rulesets import valid_payload


def _exchange_variant(sent_field: str, received_field: str, value: str) -> ConfiguredRule:
    return ConfiguredRule.model_validate(
        {
            "id": f"exchange-{value}",
            "when": {
                "kind": "compare",
                "fact": "entry.categories.region",
                "operator": "eq",
                "value": value,
            },
            "rule": {
                "kind": "exchange",
                "fields": [
                    {
                        "key": sent_field,
                        "label": sent_field.title(),
                        "value_type": "text",
                        "direction": "sent",
                        "required": True,
                    },
                    {
                        "key": received_field,
                        "label": received_field.title(),
                        "value_type": "text",
                        "direction": "received",
                        "required": True,
                    },
                ],
            },
        }
    )


def _entry(region: str) -> ScoringEntry:
    return ScoringEntry(
        entry_id=1,
        station_callsign="K7ABC",
        categories={"region": region},
        qsos=[],
    )


def test_selects_directional_exchange_layout_from_entry_context():
    arizona = _exchange_variant("county", "received_state", "arizona")
    outside = _exchange_variant("sent_state", "county", "outside")
    qso = ScoringQso(
        qso_id=1,
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        worked_callsign="N7XYZ",
        band="20m",
        mode="CW",
    )

    arizona_schema = _exchange_schema_for_qso([arizona, outside], _entry("arizona"), qso)
    outside_schema = _exchange_schema_for_qso([arizona, outside], _entry("outside"), qso)

    assert arizona_schema == arizona.rule
    assert outside_schema == outside.rule
    assert _exchange_values({"raw": "MARIC"}, arizona_schema, direction="sent") == {
        "county": "MARIC"
    }
    assert _exchange_values({"raw": "AZ"}, arizona_schema, direction="received") == {
        "received_state": "AZ"
    }
    assert _exchange_values({"raw": "AZ"}, outside_schema, direction="sent") == {"sent_state": "AZ"}
    assert _exchange_values({"raw": "PINAL"}, outside_schema, direction="received") == {
        "county": "PINAL"
    }


def test_ambiguous_active_exchange_layouts_are_not_guessed():
    arizona = _exchange_variant("county", "received_state", "arizona")
    overlapping = _exchange_variant("sent_state", "county", "arizona")
    qso = ScoringQso(
        qso_id=1,
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        worked_callsign="N7XYZ",
        band="20m",
        mode="CW",
    )

    assert _exchange_schema_for_qso([arizona, overlapping], _entry("arizona"), qso) is None


def test_ruleset_accepts_discriminated_exchange_schemas():
    payload = valid_payload()
    payload["rules"] = [item for item in payload["rules"] if item["id"] != "exchange"]
    arizona = _exchange_variant("county", "received_state", "arizona")
    outside = _exchange_variant("sent_state", "county", "outside")
    payload["rules"].extend(
        [
            arizona.model_dump(mode="json"),
            outside.model_dump(mode="json"),
        ]
    )
    category_rule = next(item for item in payload["rules"] if item["id"] == "categories")
    dimension = category_rule["rule"]["dimensions"][0]
    dimension["key"] = "region"
    dimension["label"] = "Region"
    dimension["choices"] = [
        {"key": "arizona", "label": "Arizona"},
        {"key": "outside", "label": "Outside Arizona"},
    ]
    format_rule = next(item for item in payload["rules"] if item["id"] == "format")
    format_rule["rule"]["category_mappings"] = [
        {
            "external_field": "CATEGORY-OPERATOR",
            "external_value": "SINGLE-OP",
            "category_values": {"region": "arizona"},
        }
    ]

    validated = validate_ruleset(payload)

    assert sum(item.rule.kind == "exchange" for item in validated.rules) == 2


def test_ruleset_rejects_exchange_schema_conditions_that_need_parsing_first():
    payload = valid_payload()
    exchange = next(item for item in payload["rules"] if item["id"] == "exchange")
    exchange["when"] = {
        "kind": "compare",
        "fact": "exchange.received.county",
        "operator": "eq",
        "value": "MARICOPA",
    }
    payload["rules"].append(
        {
            **exchange,
            "id": "other-exchange",
            "rule": {
                "kind": "exchange",
                "fields": [
                    {
                        "key": "county",
                        "label": "County",
                        "value_type": "text",
                        "direction": "received",
                    }
                ],
            },
        }
    )

    try:
        validate_ruleset(payload)
    except RulesetValidationError as exc:
        assert any("cannot depend on exchange values" in item["message"] for item in exc.errors)
    else:
        raise AssertionError("Expected circular exchange schema condition to be rejected")


def test_adif_tag_mappings_must_reference_exchange_fields_and_compatible_directions():
    payload = valid_payload()
    exchange = next(item for item in payload["rules"] if item["id"] == "exchange")
    exchange["rule"]["fields"].append(
        {
            "key": "county",
            "label": "County",
            "value_type": "text",
            "direction": "both",
            "required": False,
        }
    )
    cabrillo = next(item for item in payload["rules"] if item["id"] == "format")
    adif = {
        "id": "adif-format",
        "rule": {
            **cabrillo["rule"],
            "format": "adif",
            "qso_columns": [],
            "adif_exchange_fields": [
                {
                    "field_key": "county",
                    "sent_tag": "MY_COUNTY",
                    "received_tag": "COUNTY",
                }
            ],
        },
    }
    payload["rules"].append(adif)

    validated = validate_ruleset(payload)

    assert validated.rules[-1].rule.adif_exchange_fields[0].received_tag == "COUNTY"

    adif["rule"]["adif_exchange_fields"][0]["field_key"] = "unknown"
    try:
        validate_ruleset(payload)
    except RulesetValidationError as exc:
        assert any("undefined exchange field" in item["message"] for item in exc.errors)
    else:
        raise AssertionError("Expected an undefined ADIF exchange field to be rejected")


def test_adif_mapping_configuration_reaches_parser_and_adds_semantic_exchange_values():
    log = (
        "<QSO_DATE:8>20261015<TIME_ON:4>1234<BAND:3>20m<MODE:2>CW"
        "<CALL:5>F4ABC<STATION_CALLSIGN:6>EA7KLK<RST_SENT:3>599<RST_RCVD:3>599"
        "<MY_COUNTY:5>Maric<COUNTY:5>Pinal<EOR>"
    )

    parsed = _parse_log(
        log,
        "adif",
        {
            "adif_exchange_fields": [
                {
                    "field_key": "county",
                    "sent_tag": "MY_COUNTY",
                    "received_tag": "COUNTY",
                }
            ]
        },
    )

    assert parsed.errors == []
    assert parsed.qsos[0].fields["_exchange_sent_values"]["county"] == "Maric"
    assert parsed.qsos[0].fields["_exchange_received_values"]["county"] == "Pinal"


def test_custom_adif_tags_alone_supply_exchange_data():
    log = (
        "<QSO_DATE:8>20261015<TIME_ON:4>1234<BAND:3>20m<MODE:2>CW"
        "<CALL:5>F4ABC<STATION_CALLSIGN:6>EA7KLK"
        "<MY_COUNTY:5>Maric<COUNTY:5>Pinal<EOR>"
    )

    parsed = _parse_log(
        log,
        "adif",
        {
            "adif_exchange_fields": [
                {
                    "field_key": "county",
                    "sent_tag": "MY_COUNTY",
                    "received_tag": "COUNTY",
                }
            ]
        },
    )

    assert parsed.errors == []
    assert parsed.qsos[0].exchange_sent == "Maric"
    assert parsed.qsos[0].exchange_received == "Pinal"


def test_cabrillo_configured_column_order_preserves_directional_exchange_tokens():
    columns = list(DEFAULT_QSO_COLUMNS)
    columns[6], columns[9] = columns[9], columns[6]
    log = (
        "START-OF-LOG: 3.0\nCALLSIGN: K7ABC\nCONTEST: AZQP\n"
        "QSO: 14025 CW 2026-10-17 1200 K7ABC 599 MARIC N7XYZ 599 AZ\n"
        "END-OF-LOG:\n"
    )

    parsed = parse_cabrillo(log, qso_columns=columns)

    assert parsed.errors == []
    assert parsed.qsos[0].fields["exchange_sent"] == "AZ"
    assert parsed.qsos[0].fields["exchange_received"] == "MARIC"


def test_adif_rejects_custom_mappings_when_the_configured_exchange_tags_are_missing():
    log = (
        "<QSO_DATE:8>20261015<TIME_ON:4>1234<BAND:3>20m<MODE:2>CW"
        "<CALL:5>F4ABC<STATION_CALLSIGN:6>EA7KLK<EOR>"
    )

    parsed = _parse_log(
        log,
        "adif",
        {
            "adif_exchange_fields": [
                {
                    "field_key": "county",
                    "sent_tag": "MY_COUNTY",
                    "received_tag": "COUNTY",
                }
            ]
        },
    )

    assert parsed.qsos == []
    assert parsed.errors[0].code == "missing_exchange"
