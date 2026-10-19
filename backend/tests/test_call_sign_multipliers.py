import json
from pathlib import Path

import pytest

from backend.app.rulesets.call_signs import callsign_suffix, wpx_prefix_for_callsign
from backend.app.rulesets.engine import score_entry
from backend.app.rulesets.validation import validate_ruleset
from backend.tests.test_rulesets import END, START, sample_entry, valid_payload


@pytest.mark.parametrize(
    ("callsign", "expected"),
    [
        ("N8BJQ", "N8"),
        ("LY1000", "LY1000"),
        ("XEFTJW", "XE0"),
        ("3DA0XYZ", "3DA0"),
        ("N8BJQ/KH9", "KH9"),
        ("PA/N8BJQ", "PA0"),
        ("N8BJQ/P", "N8"),
        ("EA7KLK/MM", None),
    ],
)
def test_wpx_prefix_extraction_uses_sponsor_letter_numeral_convention(callsign, expected):
    assert wpx_prefix_for_callsign(callsign) == expected


@pytest.mark.parametrize(
    ("callsign", "expected"),
    [("EA7KLK", None), ("EA7KLK/P", "P"), ("EA7KLK/MM", "MM")],
)
def test_callsign_suffix_extraction(callsign, expected):
    assert callsign_suffix(callsign) == expected


def test_wpx_prefix_multiplier_counts_once_across_bands():
    payload = valid_payload()
    multiplier = next(item for item in payload["rules"] if item["id"] == "entity-multiplier")
    multiplier["rule"].update(source_fact="qso.wpx_prefix", scope="contest", label="WPX prefix")
    entry = sample_entry()
    first = entry.qsos[0].model_copy(
        update={"worked_callsign": "N8AAA", "band": "20m", "entity": None}
    )
    second = entry.qsos[1].model_copy(
        update={"worked_callsign": "N8BBB", "band": "40m", "entity": None}
    )
    third = second.model_copy(update={"qso_id": 3, "worked_callsign": "W8XYZ", "band": "40m"})
    scored_entry = entry.model_copy(update={"qsos": [first, second, third]})

    result = score_entry(
        validate_ruleset(payload),
        scored_entry,
        contest_starts_at=START,
        contest_ends_at=END,
    )

    assert result.outcome == "scored"
    assert result.multiplier_count == 2
    earned = [key for item in result.qso_scores for key in item.multiplier_keys]
    assert any(key.endswith(":N8") for key in earned)
    assert any(key.endswith(":W8") for key in earned)


def test_suffix_multiplier_uses_worked_callsign_suffix_as_value():
    payload = valid_payload()
    multiplier = next(item for item in payload["rules"] if item["id"] == "entity-multiplier")
    multiplier["rule"].update(
        source_fact="qso.callsign_suffix", scope="contest", label="Callsign suffix"
    )
    entry = sample_entry()
    first = entry.qsos[0].model_copy(update={"worked_callsign": "EA7ABC/P"})
    second = entry.qsos[1].model_copy(update={"worked_callsign": "EA7XYZ/A"})
    scored_entry = entry.model_copy(update={"qsos": [first, second]})

    result = score_entry(
        validate_ruleset(payload),
        scored_entry,
        contest_starts_at=START,
        contest_ends_at=END,
    )

    assert result.multiplier_count == 2
    assert {
        key.rsplit(":", 1)[1] for item in result.qso_scores for key in item.multiplier_keys
    } == {
        "P",
        "A",
    }


def test_entity_prefix_suffix_and_exact_call_are_distinct_worked_station_sources():
    payload = valid_payload()
    prefix_rule = next(item for item in payload["rules"] if item["id"] == "entity-multiplier")
    prefix_rule["rule"].update(source_fact="qso.wpx_prefix", scope="contest")
    payload["rules"].extend(
        [
            {
                "id": "entity-source",
                "rule": {
                    "kind": "multiplier",
                    "source_fact": "qso.entity",
                    "scope": "contest",
                    "label": "Worked station entity",
                },
            },
            {
                "id": "suffix-source",
                "rule": {
                    "kind": "multiplier",
                    "source_fact": "qso.callsign_suffix",
                    "scope": "contest",
                    "label": "Callsign suffix",
                },
            },
            {
                "id": "exact-call-source",
                "rule": {
                    "kind": "multiplier",
                    "source_fact": "qso.worked_callsign",
                    "scope": "contest",
                    "label": "Exact worked callsign",
                },
            },
        ]
    )
    entry = sample_entry()
    first = entry.qsos[0].model_copy(update={"worked_callsign": "N8AAA/P", "entity": "K"})
    second = entry.qsos[1].model_copy(update={"worked_callsign": "N8BBB/P", "entity": "K"})
    scored_entry = entry.model_copy(update={"qsos": [first, second]})

    result = score_entry(
        validate_ruleset(payload),
        scored_entry,
        contest_starts_at=START,
        contest_ends_at=END,
    )

    assert result.multiplier_count == 5
    assert len(result.qso_scores[0].multiplier_keys) == 4
    assert len(result.qso_scores[1].multiplier_keys) == 1
    assert result.qso_scores[1].multiplier_keys[0].endswith(":N8AAA/P")


def test_multiplier_source_import_draft_configures_worked_station_sources():
    path = Path(__file__).parents[2] / "documentation/ruleset-drafts/multiplier-source-demo.json"
    payload = json.loads(path.read_text())

    definition = validate_ruleset(payload)

    sources = {item.rule.source_fact for item in definition.rules if item.rule.kind == "multiplier"}
    assert sources == {
        "qso.entity",
        "qso.wpx_prefix",
        "qso.callsign_suffix",
        "qso.worked_callsign",
    }
    reloaded = validate_ruleset(definition.model_dump(mode="json"))
    assert {
        item.rule.source_fact for item in reloaded.rules if item.rule.kind == "multiplier"
    } == sources
