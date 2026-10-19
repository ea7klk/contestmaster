import json
from pathlib import Path

from build_blocked_profiles import build_records, safe_name

ROOT = Path(__file__).parent


def test_every_factory_key_has_a_non_importable_blocker_record():
    inventory = json.loads((ROOT / "profile-inventory.json").read_text(encoding="utf-8"))
    records = build_records(inventory)

    keys = [record["dispatch_key"] for record in records]
    assert len(records) == inventory["dispatch_key_count"] == 263
    assert len(keys) == len(set(keys))
    assert all(record["status"] == "blocked_from_import" for record in records)
    assert all(record["importable_ruleset"] is False for record in records)
    assert all(record["known_capability_gaps"] for record in records)


def test_checked_in_blocked_records_match_inventory_and_mark_gaps():
    inventory = json.loads((ROOT / "profile-inventory.json").read_text(encoding="utf-8"))
    keys = {profile["dispatch_key"] for profile in inventory["profiles"]}
    files = [
        path
        for path in (ROOT / "blocked").glob("*.json")
        if path.name != "qso-party-selectors.json"
    ]
    assert len(files) == len(keys)

    records = [json.loads(path.read_text(encoding="utf-8")) for path in files]
    assert {record["dispatch_key"] for record in records} == keys
    for record in records:
        assert record["artifact_schema"] == "contestmaster.n1mm-blocked-profile.v1"
        assert record["importable_ruleset"] is False
        assert record["source_trace"]["file"].endswith(f"{record['handler']}.cs")
        assert record["source_trace"]["methods"]
        assert (ROOT / "blocked" / f"{safe_name(record['dispatch_key'])}.json").is_file()

    selector_doc = json.loads(
        (ROOT / "blocked" / "qso-party-selectors.json").read_text(encoding="utf-8")
    )
    assert selector_doc["profile_selector_count"] == 50
    assert len(selector_doc["profiles"]) == 50
    assert all(profile["importable_ruleset"] is False for profile in selector_doc["profiles"])
    assert all(
        profile["blocker_kind"] == "lookup_profile_data_not_in_factory_inventory"
        for profile in selector_doc["profiles"]
    )


def test_formula_and_distance_capabilities_are_not_misreported_as_absent():
    inventory = json.loads((ROOT / "profile-inventory.json").read_text(encoding="utf-8"))
    records = build_records(inventory)
    by_key = {record["dispatch_key"]: record for record in records}

    # The scorer has distance points and formula operands for multiplier.<id>;
    # remaining blockers must describe translation fidelity, not total absence.
    assert all(record["blocker_kind"] == "not_fidelity_reviewed" for record in records)
    cqww = by_key["CQWWCW"]
    assert "no fidelity-reviewed mapping" in cqww["known_capability_gaps"][0]["detail"]
    assert (ROOT / "unconverted-profiles.md").read_text(encoding="utf-8").find(
        "Maidenhead distance points"
    ) >= 0
    assert "individual multiplier totals" in (ROOT / "unconverted-profiles.md").read_text(
        encoding="utf-8"
    )
