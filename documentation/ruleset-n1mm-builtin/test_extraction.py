"""Checks for the checked-in N1MM source inventory and parser."""

from __future__ import annotations

import json
from pathlib import Path

from extract_inventory import ARTIFACT_SCHEMA, parse_dispatch

ROOT = Path(__file__).resolve().parent


def test_factory_parser_groups_case_labels_with_the_handler_constructor():
    source = '''
    case "KEY_ONE":
    case "KEY_TWO":
        contest = new SharedHandler();
        break;
    case "KEY_THREE":
        contest = new SingleHandler();
        break;
    '''
    assert parse_dispatch(source) == [
        {"dispatch_key": "KEY_ONE", "handler": "SharedHandler"},
        {"dispatch_key": "KEY_TWO", "handler": "SharedHandler"},
        {"dispatch_key": "KEY_THREE", "handler": "SingleHandler"},
    ]


def test_checked_in_inventory_accounts_for_all_binary_dispatch_keys():
    inventory = json.loads((ROOT / "profile-inventory.json").read_text(encoding="utf-8"))
    profiles = inventory["profiles"]
    assert inventory["artifact_schema"] == ARTIFACT_SCHEMA
    assert inventory["n1mm_build"] == "1.0.11466"
    assert inventory["dispatch_key_count"] == len(profiles) == 263
    assert inventory["handler_count"] == len({item["handler"] for item in profiles}) == 142
    assert len({item["dispatch_key"] for item in profiles}) == 263
    assert all(item["importable_ruleset"] is False for item in profiles)
    assert all(item["handler_metadata"]["source_methods"] for item in profiles)


def test_profile_records_include_extraction_trace_and_do_not_claim_conversion():
    inventory = json.loads((ROOT / "profile-inventory.json").read_text(encoding="utf-8"))
    profile = next(item for item in inventory["profiles"] if item["dispatch_key"] == "AGCW")
    metadata = profile["handler_metadata"]
    assert profile["handler"] == metadata["source_class"] == "CAGCW"
    assert metadata["source_file"].endswith("CAGCW.cs")
    assert metadata["source_methods"]["ComputePoints"]
    assert metadata["setup_literals"]
    assert profile["conversion_status"] == "not-assessed"

