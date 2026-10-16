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
        for path in actual_files:
            content = path.read_text(encoding="utf-8")
            assert content == generated[path.name]
            if folder == "cabrillo":
                parsed = parse_cabrillo(content)
            else:
                parsed = parse_adif(content)
            assert parsed.errors == []
            assert len(parsed.qsos) == 1
            assert parsed.qsos[0].callsign_sent == path.stem
