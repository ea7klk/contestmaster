"""Behavior-focused checks for the importable contest and log fixtures."""

from __future__ import annotations

import importlib.util
import json
import re
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from backend.app.api.contests import ContestImportPayload
from backend.app.logs.adif import band_from_frequency_mhz, parse_adif
from backend.app.logs.cabrillo import DEFAULT_QSO_COLUMNS, map_categories, parse_cabrillo
from backend.app.rulesets.engine import ScoringEntry, ScoringQso, score_entry
from backend.app.rulesets.schema import CABRILLO_CATEGORY_VALUES, RulesetDefinition
from backend.app.rulesets.validation import validate_ruleset

ROOT = Path(__file__).resolve().parent
MIN_20M_FREQUENCY_KHZ = Decimal(14_000)
MAX_20M_FREQUENCY_KHZ = Decimal(14_350)
FIXTURE_BAND_RANGES_KHZ = {
    "10m": (Decimal(28_000), Decimal(29_700)),
    "15m": (Decimal(21_000), Decimal(21_450)),
    "20m": (MIN_20M_FREQUENCY_KHZ, MAX_20M_FREQUENCY_KHZ),
    "40m": (Decimal(7_000), Decimal(7_300)),
}


def _frequency_khz(folder: str, qso) -> Decimal:
    if folder == "cabrillo":
        return Decimal(qso.frequency)
    return Decimal(qso.fields["freq"]) * 1000


def _load_generator(format_name: str):
    path = ROOT / format_name / "generate_logs.py"
    spec = importlib.util.spec_from_file_location(f"{format_name}_fixture_generator", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _score_generated_contest(folder: str) -> dict[str, object]:
    package = json.loads((ROOT / folder / "contest.json").read_text(encoding="utf-8"))
    definition = RulesetDefinition.model_validate(package["ruleset"])
    start = datetime.fromisoformat(package["contest"]["starts_at"].replace("Z", "+00:00"))
    end = datetime.fromisoformat(package["contest"]["ends_at"].replace("Z", "+00:00"))
    extension = "*.log" if folder == "cabrillo" else "*.adi"
    scores = {}
    for entry_id, path in enumerate(sorted((ROOT / folder / "logs").glob(extension)), start=1):
        content = path.read_text(encoding="utf-8")
        if folder in {"cabrillo", "advanced-cabrillo"}:
            mapping = next(
                rule.rule for rule in definition.rules if rule.rule.kind == "format_mapping"
            )
            parsed = parse_cabrillo(content, qso_columns=mapping.qso_columns or None)
        else:
            parsed = parse_adif(content)
        qsos = []
        for qso_id, qso in enumerate(parsed.qsos, start=1):
            if folder == "cabrillo":
                sent_exchange = {"serial": int(qso.exchange_sent)}
                received_exchange = {"serial": int(qso.exchange_received)}
                mode = qso.mode
            else:
                sent_exchange = qso.fields["_exchange_sent_values"]
                received_exchange = qso.fields["_exchange_received_values"]
                mode = qso.mode
            qsos.append(
                ScoringQso(
                    qso_id=qso_id,
                    occurred_at=qso.occurred_at,
                    worked_callsign=qso.callsign_received,
                    band=(
                        band_from_frequency_mhz(str(Decimal(qso.frequency) / 1000))
                        if folder in {"cabrillo", "advanced-cabrillo"}
                        else "20m"
                    ),
                    mode=mode,
                    sent_exchange=sent_exchange,
                    received_exchange=received_exchange,
                )
            )
        result = score_entry(
            definition,
            ScoringEntry(entry_id=entry_id, station_callsign=path.stem, qsos=qsos),
            contest_starts_at=start,
            contest_ends_at=end,
        )
        scores[path.stem] = result
    return scores


def test_contest_packages_are_valid_and_only_enable_their_declared_format():
    for folder, expected_format in (
        ("cabrillo", "cabrillo"),
        ("adif", "adif"),
        ("advanced-cabrillo", "cabrillo"),
    ):
        package = json.loads((ROOT / folder / "contest.json").read_text(encoding="utf-8"))
        ContestImportPayload.model_validate(package)
        contest = package["contest"]
        assert contest["starts_at"] < contest["ends_at"] < contest["log_submission_cutoff_at"]
        assert contest["log_submission_cutoff_at"].startswith("2099-")
        ruleset = RulesetDefinition.model_validate(package["ruleset"])
        validate_ruleset(ruleset)
        category_choices = {
            dimension.key: {choice.key for choice in dimension.choices}
            for configured in ruleset.rules
            if configured.rule.kind == "categories"
            for dimension in configured.rule.dimensions
        }
        for configured in ruleset.rules:
            if configured.rule.kind != "format_mapping":
                continue
            for mapping in configured.rule.category_mappings:
                assert mapping.external_field
                assert mapping.category_values
                assert all(
                    dimension in category_choices and choice in category_choices[dimension]
                    for dimension, choice in mapping.category_values.items()
                )
        formats = [rule.rule.format for rule in ruleset.rules if rule.rule.kind == "format_mapping"]
        assert formats == [expected_format]
        if expected_format == "cabrillo":
            format_rule = next(
                rule.rule for rule in ruleset.rules if rule.rule.kind == "format_mapping"
            )
            assert format_rule.qso_columns[: len(DEFAULT_QSO_COLUMNS)] == list(DEFAULT_QSO_COLUMNS)
            assert format_rule.qso_columns[len(DEFAULT_QSO_COLUMNS) :] in ([], ["transmitter"])
            assert len(format_rule.qso_columns) == len(set(format_rule.qso_columns))
            assert format_rule.header_fields == {
                "callsign": "CALLSIGN",
                "contest": "CONTEST",
            }
            assert all(mapping.external_field for mapping in format_rule.category_mappings)
        submission = next(rule.rule for rule in ruleset.rules if rule.rule.kind == "submission")
        assert submission.late_policy == "accept_late"
        publication = [
            rule.rule
            for rule in ruleset.rules
            if rule.rule.kind == "workflow_hook" and rule.rule.stage == "publication"
        ]
        assert len(publication) == 1
        assert publication[0].parameters["include_late"] is True
        if folder == "advanced-cabrillo":
            assert publication[0].parameters["include_needs_review"] is False
        if folder in {"cabrillo", "advanced-cabrillo"}:
            exchange = next(rule.rule for rule in ruleset.rules if rule.rule.kind == "exchange")
            serial = next(field for field in exchange.fields if field.key == "serial")
            assert serial.value_type == "serial"
            assert serial.direction == "both"
            assert serial.required
        multipliers = [rule.rule for rule in ruleset.rules if rule.rule.kind == "multiplier"]
        expected_multipliers = {
            "cabrillo": 2,
            "adif": 3,
            "advanced-cabrillo": 3,
        }[folder]
        assert len(multipliers) == expected_multipliers
        assert multipliers[0].source_fact == "qso.worked_callsign"
        if folder == "advanced-cabrillo":
            kinds = {item.rule.kind for item in ruleset.rules}
            assert {
                "bonus",
                "duplicates",
                "eligibility",
                "exchange",
                "format_mapping",
                "operating_constraints",
                "penalty",
                "points",
                "score_formula",
                "session_resets",
                "workflow_hook",
            } <= kinds
        formula = next(rule.rule for rule in ruleset.rules if rule.rule.kind == "score_formula")
        if folder == "advanced-cabrillo":
            configured_multiplier_ids = {
                item.id for item in ruleset.rules if item.rule.kind == "multiplier"
            }
            formula_multiplier_ids = {
                formula.start.variable.removeprefix("multiplier."),
                *(
                    step.operand.variable.removeprefix("multiplier.")
                    for step in formula.steps
                    if step.operand.variable and step.operand.variable.startswith("multiplier.")
                ),
            }
            assert formula_multiplier_ids == configured_multiplier_ids
            assert all(step.operand.variable != "multiplier_count" for step in formula.steps)
        else:
            assert any(
                step.operator == "multiply" and step.operand.variable == "multiplier_count"
                for step in formula.steps
            )


def test_all_documented_ruleset_drafts_validate():
    for path in sorted((ROOT.parent / "ruleset-drafts").glob("*.json")):
        definition = RulesetDefinition.model_validate(json.loads(path.read_text(encoding="utf-8")))
        validate_ruleset(definition)
        if path.name in {"cq-ww-cw.json", "cq-ww-rtty.json", "cq-ww-ssb.json"}:
            formula = next(
                item.rule for item in definition.rules if item.rule.kind == "score_formula"
            )
            multiplier_ids = {
                item.id for item in definition.rules if item.rule.kind == "multiplier"
            }
            assert formula.start.variable == "multiplier.multiplier-1"
            assert formula.steps[0].operand.variable == "multiplier.multiplier-2"
            assert formula.steps[1].operand.variable == "points_total"
            assert {"multiplier-1", "multiplier-2"} <= multiplier_ids
        if path.name == "rsgb-vhf-general-distance-sessions.json":
            assert any(item.rule.kind == "distance_points" for item in definition.rules)
            assert any(item.rule.kind == "session_resets" for item in definition.rules)
        category_choices = {
            dimension.key: {choice.key for choice in dimension.choices}
            for configured in definition.rules
            if configured.rule.kind == "categories"
            for dimension in configured.rule.dimensions
        }
        for configured in definition.rules:
            if configured.rule.kind != "format_mapping":
                continue
            for mapping in configured.rule.category_mappings:
                assert mapping.external_field, path.name
                assert mapping.category_values, path.name
                assert all(
                    dimension in category_choices and choice in category_choices[dimension]
                    for dimension, choice in mapping.category_values.items()
                ), path.name


def test_generated_logs_are_reproducible_unique_and_parseable():
    expectations = (("cabrillo", 110), ("adif", 56))
    for folder, expected_count in expectations:
        generator = _load_generator(folder)
        generated = generator.build_logs()
        log_dir = ROOT / folder / "logs"
        actual_files = sorted(log_dir.glob("*.log" if folder == "cabrillo" else "*.adi"))
        assert len(generated) == expected_count
        assert len(actual_files) == expected_count
        assert len({path.stem for path in actual_files}) == expected_count
        participants = {path.stem for path in actual_files}
        parsed_logs = {}
        frequencies_khz = set()
        total_calls = matched_calls = 0
        for path in actual_files:
            content = path.read_text(encoding="utf-8")
            assert content == generated[path.name]
            if folder in {"cabrillo", "advanced-cabrillo"}:
                parsed = parse_cabrillo(content)
            else:
                parsed = parse_adif(content)
            assert parsed.errors == []
            if folder in {"cabrillo", "advanced-cabrillo"}:
                assert parsed.headers["EMAIL"] == [f"{path.stem}@nomail.invalid"]
                contest_header = parsed.headers["CONTEST"][0]
                assert len(contest_header) <= 32
                assert re.fullmatch(r"[A-Z0-9-]+", contest_header)
                for header, values in parsed.headers.items():
                    if header.startswith("CATEGORY-"):
                        assert header in CABRILLO_CATEGORY_VALUES
                        permitted_values = {
                            value.casefold() for value in CABRILLO_CATEGORY_VALUES[header]
                        }
                        assert all(value.casefold() in permitted_values for value in values)
                for line in content.splitlines():
                    if line.startswith("QSO:"):
                        fields = line.split()
                        assert len(fields) == (12 if folder == "advanced-cabrillo" else 11)
                        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", fields[3])
                        assert re.fullmatch(r"\d{4}", fields[4])
            if folder == "advanced-cabrillo":
                assert 50 <= len(parsed.qsos) <= 250
            else:
                assert 5 <= len(parsed.qsos) <= 80
            assert all(qso.callsign_sent == path.stem for qso in parsed.qsos)
            for qso in parsed.qsos:
                frequency_khz = _frequency_khz(folder, qso)
                if folder == "advanced-cabrillo":
                    band = band_from_frequency_mhz(str(frequency_khz / 1000))
                    assert band in FIXTURE_BAND_RANGES_KHZ
                    low_khz, high_khz = FIXTURE_BAND_RANGES_KHZ[band]
                    assert low_khz <= frequency_khz <= high_khz
                else:
                    assert MIN_20M_FREQUENCY_KHZ <= frequency_khz <= MAX_20M_FREQUENCY_KHZ
                frequencies_khz.add(frequency_khz)
            total_calls += len(parsed.qsos)
            matched_calls += sum(qso.callsign_received in participants for qso in parsed.qsos)
            parsed_logs[path.stem] = parsed.qsos
        reciprocal_lookups = {
            station: {qso.callsign_received: qso for qso in qsos}
            for station, qsos in parsed_logs.items()
        }

        if folder == "advanced-cabrillo":
            assert 0.78 <= matched_calls / total_calls <= 0.82
        else:
            assert matched_calls * 5 == total_calls * 4
        assert len(frequencies_khz) >= 30
        for station, qsos in parsed_logs.items():
            if folder == "cabrillo":
                assert [qso.exchange_sent for qso in qsos] == [
                    f"{serial:03d}" for serial in range(1, len(qsos) + 1)
                ]
            by_peer = {qso.callsign_received: qso for qso in qsos}
            for peer, qso in by_peer.items():
                if peer in participants:
                    reciprocal = reciprocal_lookups[peer].get(station)
                    assert reciprocal is not None
                    assert _frequency_khz(folder, qso) == _frequency_khz(folder, reciprocal)
                    if folder in {"cabrillo", "advanced-cabrillo"}:
                        assert qso.exchange_sent.isdecimal()
                        assert qso.exchange_received.isdecimal()
                        assert qso.exchange_sent == reciprocal.exchange_received
                        assert qso.exchange_received == reciprocal.exchange_sent
                elif folder in {"cabrillo", "advanced-cabrillo"}:
                    assert qso.exchange_sent.isdecimal()
                    assert qso.exchange_received.isdecimal()


def test_synthetic_contest_rules_produce_clear_ranked_winners():
    expected_scores = {
        "cabrillo": {"K0AAA": 87480, "K0AAB": 32960, "K0AAC": 22440},
        "adif": {"K0AAA": 65720, "K0AAB": 22440, "K0AAC": 120},
    }
    for folder, expected in expected_scores.items():
        scores = _score_generated_contest(folder)
        ordered = sorted(scores.items(), key=lambda item: item[1].final_score, reverse=True)
        assert [callsign for callsign, _score in ordered[:3]] == ["K0AAA", "K0AAB", "K0AAC"]
        assert {callsign: score.final_score for callsign, score in ordered[:3]} == expected
        assert ordered[0][1].final_score > ordered[1][1].final_score * 2
        assert ordered[1][1].final_score > ordered[2][1].final_score
        assert (
            ordered[2][1].final_score
            > max(score.final_score for _callsign, score in ordered[3:]) * 3
        )
        assert all(score.outcome == "scored" for score in scores.values())


def _score_advanced_cabrillo() -> dict[str, object]:
    folder = "advanced-cabrillo"
    package = json.loads((ROOT / folder / "contest.json").read_text(encoding="utf-8"))
    definition = RulesetDefinition.model_validate(package["ruleset"])
    start = datetime.fromisoformat(package["contest"]["starts_at"].replace("Z", "+00:00"))
    end = datetime.fromisoformat(package["contest"]["ends_at"].replace("Z", "+00:00"))
    mappings = next(
        item.rule.category_mappings
        for item in definition.rules
        if item.rule.kind == "format_mapping"
    )
    serialized_mappings = [mapping.model_dump(mode="json") for mapping in mappings]
    format_rule = next(item.rule for item in definition.rules if item.rule.kind == "format_mapping")
    scores = {}
    for entry_id, path in enumerate(sorted((ROOT / folder / "logs").glob("*.log")), start=1):
        parsed = parse_cabrillo(
            path.read_text(encoding="utf-8"),
            qso_columns=format_rule.qso_columns or None,
        )
        assert parsed.errors == []
        categories, warnings = map_categories(parsed, serialized_mappings)
        assert not warnings
        qsos = [
            ScoringQso(
                qso_id=qso_id,
                occurred_at=qso.occurred_at,
                worked_callsign=qso.callsign_received,
                band=band_from_frequency_mhz(str(Decimal(qso.frequency) / 1000)),
                mode=qso.mode,
                transmitter=qso.fields["transmitter"],
                sent_exchange={"serial": int(qso.exchange_sent)},
                received_exchange={"serial": int(qso.exchange_received)},
            )
            for qso_id, qso in enumerate(parsed.qsos, start=1)
        ]
        scores[path.stem] = score_entry(
            definition,
            ScoringEntry(
                entry_id=entry_id,
                station_callsign=path.stem,
                categories=categories,
                qsos=qsos,
            ),
            contest_starts_at=start,
            contest_ends_at=end,
        )
    return scores


def test_advanced_cabrillo_fixture_scores_with_advanced_rules_without_review():
    generator = _load_generator("advanced-cabrillo")
    logs = generator.build_logs()
    paths = sorted((ROOT / "advanced-cabrillo" / "logs").glob("*.log"))
    assert len(logs) == len(paths) == 2_500
    assert all(path.read_text(encoding="utf-8") == logs[path.name] for path in paths)
    assert len(generator.ENTITY_PREFIXES) == 10
    assert {
        next(prefix for prefix in generator.ENTITY_PREFIXES if path.stem.startswith(prefix))
        for path in paths
    } == set(generator.ENTITY_PREFIXES)

    format_rule = next(
        item.rule
        for item in RulesetDefinition.model_validate(
            json.loads((ROOT / "advanced-cabrillo" / "contest.json").read_text())["ruleset"]
        ).rules
        if item.rule.kind == "format_mapping"
    )
    parsed_logs = {
        path.stem: parse_cabrillo(
            path.read_text(encoding="utf-8"),
            qso_columns=format_rule.qso_columns or None,
        ).qsos
        for path in paths
    }
    reciprocal_lookups = {
        station: {(qso.callsign_received, qso.occurred_at): qso for qso in qsos}
        for station, qsos in parsed_logs.items()
    }
    for station, qsos in parsed_logs.items():
        assert [qso.exchange_sent for qso in qsos] == [
            f"{serial:03d}" for serial in range(1, len(qsos) + 1)
        ]
        for qso in qsos:
            if qso.callsign_received not in parsed_logs:
                continue
            reciprocal = reciprocal_lookups[qso.callsign_received].get((station, qso.occurred_at))
            assert reciprocal is not None
            assert qso.exchange_sent == reciprocal.exchange_received
            assert qso.exchange_received == reciprocal.exchange_sent

    assert all(50 <= len(qsos) <= 250 for qsos in parsed_logs.values())
    assert all(
        len({qso.fields["transmitter"] for qso in qsos}) <= 2 for qsos in parsed_logs.values()
    )
    assert all(
        band_from_frequency_mhz(str(Decimal(qso.frequency) / 1000)) in FIXTURE_BAND_RANGES_KHZ
        for qsos in parsed_logs.values()
        for qso in qsos
    )
    operating_rule = next(
        item.rule
        for item in RulesetDefinition.model_validate(
            json.loads((ROOT / "advanced-cabrillo" / "contest.json").read_text())["ruleset"]
        ).rules
        if item.rule.kind == "operating_constraints"
    )
    assert operating_rule.minimum_band_dwell_minutes == 60
    assert operating_rule.maximum_band_changes == 1
    assert operating_rule.band_change_window_minutes == 60
    for qsos in parsed_logs.values():
        bands = [band_from_frequency_mhz(str(Decimal(qso.frequency) / 1000)) for qso in qsos]
        assert set(bands) == set(FIXTURE_BAND_RANGES_KHZ)
        for qso, band in zip(qsos, bands, strict=True):
            session = next(
                session
                for session in generator.BAND_SESSIONS
                if session[0] <= qso.occurred_at < session[1]
            )
            assert band == session[2]
        band_changes = [
            (left.occurred_at, right.occurred_at)
            for left, right, left_band, right_band in zip(
                qsos, qsos[1:], bands, bands[1:], strict=False
            )
            if left_band != right_band
        ]
        assert all(
            (current - previous) >= timedelta(minutes=operating_rule.minimum_band_dwell_minutes)
            for previous, current in band_changes
        )
        change_instants = [current for _previous, current in band_changes]
        assert all(
            sum(
                instant
                <= candidate
                < instant + timedelta(minutes=operating_rule.band_change_window_minutes)
                for candidate in change_instants
            )
            <= operating_rule.maximum_band_changes
            for instant in change_instants
        )
    scores = _score_advanced_cabrillo()
    ordered = sorted(scores.items(), key=lambda item: item[1].final_score, reverse=True)
    assert [name for name, _score in ordered[:3]] == ["K0AAA", "K0AAB", "K0AAC"]
    assert ordered[0][1].final_score > ordered[1][1].final_score
    assert ordered[1][1].final_score > ordered[2][1].final_score
    assert len({score.final_score for _callsign, score in ordered[:3]}) == 3
    assert ordered[0][1].bonus_points >= 250
    assert ordered[0][1].penalty_points > 0
    assert any(
        "low-serial-review" in qso.reasons
        for _callsign, score in ordered
        for qso in score.qso_scores
    )
    assert all(score.final_score > 0 for score in scores.values())
    assert all(score.outcome == "scored" and not score.review_reasons for score in scores.values())
    assert all(
        qso.session_number is not None
        for _callsign, score in scores.items()
        for qso in score.qso_scores
    )
