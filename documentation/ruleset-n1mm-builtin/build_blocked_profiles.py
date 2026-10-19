#!/usr/bin/env python3
"""Build explicit, non-importable analysis records for unconverted N1MM keys.

The records point to decompiled method locations without copying method bodies.
They are deliberately not Contestmaster ruleset documents.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

QSO_PARTY_SELECTORS = (
    "QSOP_7QP QSOP_AK QSOP_AL QSOP_AR QSOP_AZ QSOP_BC QSOP_CA QSOP_CO QSOP_CT QSOP_DE "
    "QSOP_GA QSOP_HI QSOP_IA QSOP_ID QSOP_IL QSOP_IN QSOP_IN7QPE QSOP_KS QSOP_KY "
    "QSOP_LA QSOP_MARAC_ QSOP_MCC QSOP_MD QSOP_MI QSOP_MN QSOP_MO QSOP_MT QSOP_NC "
    "QSOP_ND QSOP_NE QSOP_NEWE QSOP_NH QSOP_NJ QSOP_NM QSOP_NV QSOP_NY QSOP_OH QSOP_OK "
    "QSOP_ON QSOP_OR QSOP_PA QSOP_SC QSOP_SD QSOP_TN QSOP_TX QSOP_VA QSOP_VT QSOP_WA "
    "QSOP_WI QSOP_WV"
).split()


def capability_gaps(profile: dict[str, Any]) -> list[dict[str, str]]:
    methods = profile["handler_metadata"]["source_methods"]
    gaps = [
        {
            "id": "profile_translation_unverified",
            "detail": (
                "This profile has no fidelity-reviewed mapping from its handler branches "
                "to Contestmaster's declarative rules. It is blocked from import until its "
                "exchange, categories, eligibility, duplicate identity, multipliers, points, "
                "formula, and format behavior are traced and represented."
            ),
        }
    ]
    mapping = {
        "ComputePoints": (
            "points_branch_translation",
            "Contestmaster supports fixed, lookup, conditional, and grid-distance points, "
            "but does not execute arbitrary N1MM C# branches. Trace every token-specific "
            "branch and identify any unsupported fact, lookup table, distance convention, "
            "or rounding behavior before conversion.",
        ),
        "ComputeScore": (
            "final_formula_translation",
            "Contestmaster supports integer arithmetic over points, bonuses, penalties, "
            "power, and individual multiplier totals. Any branch or operand outside those "
            "declarative facts needs a new typed rule capability or must remain blocked.",
        ),
        "ScoreSqlString": (
            "score_query_translation",
            "N1MM's score SQL is executable/query-backed behavior. Contestmaster does not "
            "execute handler SQL; translate its exact result into supported declarative "
            "rules or identify the missing typed scoring fact.",
        ),
        "MultSqlString": (
            "multiplier_source_translation",
            "Contestmaster supports per-rule multiplier facts and scopes, but not arbitrary "
            "N1MM SQL joins or profile-specific external tables. Trace the selected profile's "
            "source values, uniqueness key, and scope.",
        ),
        "MultSqlString2": (
            "second_multiplier_source_translation",
            "The second N1MM multiplier query must be translated to a separately identified "
            "Contestmaster multiplier rule with equivalent source, uniqueness, and scope; "
            "arbitrary SQL is not supported.",
        ),
        "MultSqlString3": (
            "third_multiplier_source_translation",
            "The third N1MM multiplier query must be translated to a separately identified "
            "Contestmaster multiplier rule with equivalent source, uniqueness, and scope; "
            "arbitrary SQL is not supported.",
        ),
        "DupeSqlString": (
            "duplicate_identity_translation",
            "Contestmaster has declarative duplicate scopes, but does not execute N1MM's "
            "profile SQL. Verify the full identity key and whether a duplicate can still "
            "contribute to multipliers for this profile.",
        ),
        "IsWorkable": (
            "workability_predicate_translation",
            "Contestmaster supports validated declarative conditions, not arbitrary handler "
            "predicates. Identify required entrant, station, exchange, mode, and reference "
            "facts and check that each is available to the scorer.",
        ),
        "QsoErrorString": (
            "exchange_validation_translation",
            "Contestmaster validates configured exchange fields and supported file mappings, "
            "but does not import N1MM's interactive parser and correction behavior. Trace "
            "mandatory fields, value domains, and profile-specific validation.",
        ),
        "SentExch": (
            "sent_exchange_translation",
            "Map the exact sent exchange fields and semantics to Contestmaster's exchange "
            "schema and accepted Cabrillo/ADIF mappings; N1MM logger-entry behavior is not "
            "a portable ruleset capability.",
        ),
        "RcvdExch": (
            "received_exchange_translation",
            "Map the exact received exchange fields and semantics to Contestmaster's exchange "
            "schema and accepted Cabrillo/ADIF mappings; N1MM logger-entry behavior is not "
            "a portable ruleset capability.",
        ),
        "CabrilloFormat": (
            "cabrillo_layout_translation",
            "Contestmaster uses explicit Cabrillo field mappings. Trace the handler's format "
            "identifier and verify that required WWROF QSO columns and category headers can "
            "represent this profile without losing scoring inputs.",
        ),
    }
    for method, (gap_id, detail) in mapping.items():
        if method in methods:
            gaps.append({"id": gap_id, "detail": detail})
    if "DefaultContestExchange" in methods:
        gaps.append(
            {
                "id": "default_exchange_is_not_a_complete_schema",
                "detail": (
                    "N1MM's default exchange string is only a logger default. Contestmaster "
                    "still needs an explicit typed exchange schema, allowed values, and "
                    "format mappings; the literal alone is insufficient."
                ),
            }
        )
    return gaps


def build_records(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    records = []
    for profile in inventory["profiles"]:
        metadata = profile["handler_metadata"]
        records.append(
            {
                "artifact_schema": "contestmaster.n1mm-blocked-profile.v1",
                "n1mm_build": inventory["n1mm_build"],
                "profile_id": profile["profile_id"],
                "dispatch_key": profile["dispatch_key"],
                "handler": profile["handler"],
                "status": "blocked_from_import",
                "importable_ruleset": False,
                "blocker_kind": "not_fidelity_reviewed",
                "source_trace": {
                    "file": metadata["source_file"],
                    "methods": metadata["source_methods"],
                    "default_exchange_literal": metadata["default_exchange_literal"],
                    "constant_method_returns": metadata["constant_method_returns"],
                },
                "known_capability_gaps": capability_gaps(profile),
                "conversion_note": (
                    "Blocked means no complete, verified Contestmaster translation exists "
                    "in this output yet. It does not claim every listed behavior is "
                    "permanently impossible; sponsor-edition validation and exact branch "
                    "tracing may show that supported declarative rules suffice."
                ),
            }
        )
    return records


def safe_name(value: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "-", value.lower()).strip("-")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    args = parser.parse_args()
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    records = build_records(inventory)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for record in records:
        name = safe_name(record["dispatch_key"]) + ".json"
        (args.output_dir / name).write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    selector_record = {
        "artifact_schema": "contestmaster.n1mm-data-backed-profile-selectors.v1",
        "n1mm_build": inventory["n1mm_build"],
        "handler_dispatch_key": "QSOPARTY",
        "profile_selector_count": len(QSO_PARTY_SELECTORS),
        "profiles": [
            {
                "profile_id": profile_id,
                "status": "blocked_from_import",
                "importable_ruleset": False,
                "blocker_kind": "lookup_profile_data_not_in_factory_inventory",
                "source_trace": {
                    "handler": "CQSOpartyNr",
                    "methods": ["Initialize", "ComputePoints", "MultSqlString", "QsoErrorString"],
                    "notes": (
                        "The factory constructs only the shared QSOPARTY handler. "
                        "The handler selects subtype and lookup rows at runtime; its "
                        "factory case does not contain this profile's full exchange and "
                        "scoring tables."
                    ),
                },
                "known_capability_gaps": [
                    (
                        "Exact profile lookup rows, accepted sections/counties, and scoring "
                        "data were not extracted from the factory handler."
                    ),
                    (
                        "The shared QSO Party handler has profile-specific point, multiplier, "
                        "entrant, mobile/rover, and bonus branches that must be selected and "
                        "traced for this subtype."
                    ),
                    (
                        "Contestmaster has no imported QSO Party reference table for this "
                        "profile; any lookup data must be sourced and licensed separately or "
                        "represented as reviewed declarative values."
                    ),
                ],
            }
            for profile_id in QSO_PARTY_SELECTORS
        ],
    }
    (args.output_dir / "qso-party-selectors.json").write_text(
        json.dumps(selector_record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    rows = [
        "# N1MM profiles blocked from faithful conversion",
        "",
        (
            "**Scope:** N1MM Logger+ update 1.0.11466; static handler inventory compared "
            "with the current Contestmaster ruleset engine."
        ),
        "",
        (
            "This is a complete list of factory dispatch keys for which this directory does "
            "not yet contain a fidelity-reviewed, importable Contestmaster ruleset. "
            "`blocked_from_import` means the conversion is incomplete, not that a profile is "
            "permanently impossible to express. Each row links to a structured record with "
            "the handler's source method locations and applicable capability gaps. Do not "
            "import these records as contest rules."
        ),
        "",
        (
            "N1MM handlers are executable C#; Contestmaster accepts validated declarative "
            "configuration and never loads or executes these handlers. The shared engine "
            "currently has fixed, lookup, conditional, and Maidenhead distance points; "
            "per-rule multiplier counts and scopes; integer formulas over individual "
            "multiplier totals; declarative conditions; duplicate scopes; bonuses; and "
            "explicit Cabrillo/ADIF mappings. Thus older generic gap reports about all "
            "distance scoring or all independent multiplier arithmetic are stale. The "
            "remaining issue is exact per-profile translation and any handler behavior "
            "outside those supported facts, not absence of every general scoring primitive."
        ),
        "",
        "## Dispatch-key inventory",
        "",
        "| Key | Handler | Methods to trace | Known blockers | Analysis record |",
        "| --- | --- | --- | --- | --- |",
    ]
    for record in records:
        trace = record["source_trace"]
        method_names = ", ".join(f"`{name}`" for name in trace["methods"])
        if not method_names:
            method_names = "setup metadata only; no relevant override located"
        gap_names = ", ".join(f"`{item['id']}`" for item in record["known_capability_gaps"])
        rows.append(
            f"| `{record['dispatch_key']}` | `{record['handler']}` | {method_names} | "
            f"{gap_names} | [`{record['dispatch_key']}.json`]"
            f"(blocked/{safe_name(record['dispatch_key'])}.json) |"
        )
    rows.extend(
        [
            "",
            "## QSO Party data-backed profile selectors",
            "",
            (
                "The supported-contests index and supplied handler analysis identify 50 QSO "
                "Party profile selectors that all use the single factory key `QSOPARTY`. "
                "They are not 50 factory dispatch keys, and their complete lookup tables are "
                "not present in the factory inventory. The handler references runtime "
                "subtype-specific lookup data and has profile-dependent scoring/workability "
                "branches. These selector profiles therefore remain individually blocked; "
                "see [`blocked/qso-party-selectors.json`](blocked/qso-party-selectors.json). "
                "The list is selector inventory only, not a claim that its exchange or "
                "scoring data has been extracted."
            ),
            "",
            ", ".join(f"`{item}`" for item in QSO_PARTY_SELECTORS),
        ]
    )
    rows.extend(
        [
            "",
            "## How to read the blockers",
            "",
            (
                "- `profile_translation_unverified` is present for every record until its "
                "complete rule behavior has been translated and validated. A source method "
                "reference is a trace pointer, not an extracted rule."
            ),
            (
                "- Specialized handler methods add a precise blocker family: points, final "
                "formula, multiplier source, duplicate identity, workability, exchange "
                "validation, sent/received exchange, Cabrillo layout, or incomplete default "
                "exchange metadata."
            ),
            (
                "- The same handler can serve several keys and branch on the active key. A "
                "shared class does not make those profiles interchangeable; trace source "
                "references with the token branch in view."
            ),
            (
                "- Before marking a key converted, obtain a target sponsor rule edition when "
                "applicable, map all scoring inputs to current typed rules, validate the JSON, "
                "and add expected-outcome tests. Keep event dates on Contestmaster contest "
                "records, not reusable rulesets."
            ),
            (
                "- These records do not infer current status from N1MM's dispatch switch. "
                "Aliases, legacy keys, and discontinued entries need independent status "
                "verification."
            ),
            "",
            (
                "See [the extraction README](README.md), [N1MM binary behavior notes]"
                "(../../ruleset-parity/n1mm-functional-parity-plan.md), and tracking issue "
                "[#404](https://github.com/ea7klk/contestmaster/issues/404)."
            ),
            "",
        ]
    )
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.write_text("\n".join(rows), encoding="utf-8")
    print(f"Wrote {len(records)} explicit non-importable profile records")


if __name__ == "__main__":
    main()
