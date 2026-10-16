"""Behavior-focused checks for the importable contest and log fixtures."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from backend.app.logs.adif import parse_adif
from backend.app.logs.cabrillo import parse_cabrillo
from backend.app.rulesets.schema import RulesetDefinition
from backend.app.rulesets.validation import validate_ruleset

ROOT = Path(__file__).resolve().parent


def _load_generator(format_name: str):
    path = ROOT / format_name / "generate_logs.py"
    spec = importlib.util.spec_from_file_location(f"{format_name}_fixture_generator", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_contest_packages_are_valid_and_only_enable_their_declared_format():
    for folder, expected_format in (("cabrillo", "cabrillo"), ("adif", "adif")):
        package = json.loads((ROOT / folder / "contest.json").read_text(encoding="utf-8"))
        contest = package["contest"]
        assert contest["starts_at"] < contest["ends_at"] < contest["log_submission_cutoff_at"]
        assert contest["log_submission_cutoff_at"].startswith("2099-")
        ruleset = RulesetDefinition.model_validate(package["ruleset"])
        validate_ruleset(ruleset)
        formats = [
            rule.rule.format
            for rule in ruleset.rules
            if rule.rule.kind == "format_mapping"
        ]
        assert formats == [expected_format]
        submission = next(rule.rule for rule in ruleset.rules if rule.rule.kind == "submission")
        assert submission.late_policy == "accept_late"
        if folder == "cabrillo":
            exchange = next(rule.rule for rule in ruleset.rules if rule.rule.kind == "exchange")
            serial = next(field for field in exchange.fields if field.key == "serial")
            assert serial.value_type == "serial"
            assert serial.direction == "both"
            assert serial.required


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
        total_calls = matched_calls = 0
        for path in actual_files:
            content = path.read_text(encoding="utf-8")
            assert content == generated[path.name]
            if folder == "cabrillo":
                parsed = parse_cabrillo(content)
            else:
                parsed = parse_adif(content)
            assert parsed.errors == []
            if folder == "cabrillo":
                assert parsed.headers["EMAIL"] == [f"{path.stem}@nomail.invalid"]
            assert 5 <= len(parsed.qsos) <= 80
            assert all(qso.callsign_sent == path.stem for qso in parsed.qsos)
            total_calls += len(parsed.qsos)
            matched_calls += sum(qso.callsign_received in participants for qso in parsed.qsos)
            parsed_logs[path.stem] = parsed.qsos

        assert matched_calls * 5 == total_calls * 4
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
                    if folder == "cabrillo":
                        assert qso.exchange_sent.isdecimal()
                        assert qso.exchange_received.isdecimal()
                        assert qso.exchange_sent == reciprocal[station].exchange_received
                        assert qso.exchange_received == reciprocal[station].exchange_sent
                elif folder == "cabrillo":
                    assert qso.exchange_sent.isdecimal()
                    assert qso.exchange_received.isdecimal()
