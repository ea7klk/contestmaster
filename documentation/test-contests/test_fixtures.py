"""Behavior-focused checks for the importable contest and log fixtures."""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from backend.app.api.contests import ContestImportPayload
from backend.app.logs.adif import parse_adif
from backend.app.logs.cabrillo import map_categories, parse_cabrillo
from backend.app.rulesets.engine import ScoringEntry, ScoringQso, score_entry
from backend.app.rulesets.schema import RulesetDefinition
from backend.app.rulesets.validation import validate_ruleset

ROOT = Path(__file__).resolve().parent
MIN_20M_FREQUENCY_KHZ = Decimal(14_000)
MAX_20M_FREQUENCY_KHZ = Decimal(14_350)


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
        parsed = parse_cabrillo(content) if folder == "cabrillo" else parse_adif(content)
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
                    band="20m",
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
        formats = [rule.rule.format for rule in ruleset.rules if rule.rule.kind == "format_mapping"]
        assert formats == [expected_format]
        submission = next(rule.rule for rule in ruleset.rules if rule.rule.kind == "submission")
        assert submission.late_policy == "accept_late"
        publication = [
            rule.rule
            for rule in ruleset.rules
            if rule.rule.kind == "workflow_hook" and rule.rule.stage == "publication"
        ]
        assert len(publication) == 1
        assert publication[0].parameters["include_late"] is True
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
                "workflow_hook",
            } <= kinds
        formula = next(rule.rule for rule in ruleset.rules if rule.rule.kind == "score_formula")
        assert any(
            step.operator == "multiply" and step.operand.variable == "multiplier_count"
            for step in formula.steps
        )


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
            assert 5 <= len(parsed.qsos) <= 80
            assert all(qso.callsign_sent == path.stem for qso in parsed.qsos)
            for qso in parsed.qsos:
                frequency_khz = _frequency_khz(folder, qso)
                assert MIN_20M_FREQUENCY_KHZ <= frequency_khz <= MAX_20M_FREQUENCY_KHZ
                frequencies_khz.add(frequency_khz)
            total_calls += len(parsed.qsos)
            matched_calls += sum(qso.callsign_received in participants for qso in parsed.qsos)
            parsed_logs[path.stem] = parsed.qsos

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
                    reciprocal = {item.callsign_received: item for item in parsed_logs[peer]}
                    assert station in reciprocal
                    assert _frequency_khz(folder, qso) == _frequency_khz(
                        folder, reciprocal[station]
                    )
                    if folder in {"cabrillo", "advanced-cabrillo"}:
                        assert qso.exchange_sent.isdecimal()
                        assert qso.exchange_received.isdecimal()
                        assert qso.exchange_sent == reciprocal[station].exchange_received
                        assert qso.exchange_received == reciprocal[station].exchange_sent
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
    scores = {}
    for entry_id, path in enumerate(sorted((ROOT / folder / "logs").glob("*.log")), start=1):
        parsed = parse_cabrillo(path.read_text(encoding="utf-8"))
        assert parsed.errors == []
        categories, warnings = map_categories(parsed, serialized_mappings)
        assert not warnings
        qsos = [
            ScoringQso(
                qso_id=qso_id,
                occurred_at=qso.occurred_at,
                worked_callsign=qso.callsign_received,
                band="20m",
                mode=qso.mode,
                transmitter="1",
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


def test_advanced_cabrillo_fixture_exercises_penalties_bonuses_multipliers_and_review():
    generator = _load_generator("advanced-cabrillo")
    logs = generator.build_logs()
    paths = sorted((ROOT / "advanced-cabrillo" / "logs").glob("*.log"))
    assert len(logs) == len(paths) == 32
    assert all(path.read_text(encoding="utf-8") == logs[path.name] for path in paths)

    parsed_logs = {
        path.stem: parse_cabrillo(path.read_text(encoding="utf-8")).qsos for path in paths
    }
    for station, qsos in parsed_logs.items():
        assert [qso.exchange_sent for qso in qsos] == [
            f"{serial:03d}" for serial in range(1, len(qsos) + 1)
        ]
        for qso in qsos:
            if station == "K0AAA" and qso.occurred_at.hour == 17:
                # This final record is the deliberately unpaired duplicate.
                continue
            if qso.callsign_received not in parsed_logs:
                continue
            reciprocal = next(
                item
                for item in parsed_logs[qso.callsign_received]
                if item.callsign_received == station and item.occurred_at == qso.occurred_at
            )
            assert qso.exchange_sent == reciprocal.exchange_received
            assert qso.exchange_received == reciprocal.exchange_sent

    scores = _score_advanced_cabrillo()
    ordered = sorted(scores.items(), key=lambda item: item[1].final_score, reverse=True)
    assert ordered[0][0] == "K0AAA"
    assert [(name, score.final_score) for name, score in ordered[:3]] == [
        ("K0AAA", 21344),
        ("K0AAB", 8487),
        ("K0AAC", 1534),
    ]
    assert ordered[0][1].final_score > ordered[1][1].final_score
    assert len({score.final_score for _callsign, score in ordered[:3]}) == 3
    assert ordered[0][1].bonus_points >= 250
    assert ordered[0][1].penalty_points > 0
    assert any("duplicate" in qso.reasons for qso in ordered[0][1].qso_scores)
    assert any(
        "low-serial-review" in qso.reasons
        for _callsign, score in ordered
        for qso in score.qso_scores
    )
    assert any(score.workflow_actions for score in scores.values())
    assert all(score.final_score >= 0 for score in scores.values())
