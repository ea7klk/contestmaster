# Sponsor-linked scoring fixtures

These fixtures pair a named sponsor edition, machine-readable Contestmaster rules, synthetic log inputs, and hand-calculated expected scoring components. They test only the behavior described in each fixture; they do not claim to reproduce every rule or entry class for that contest.

## Arizona QSO Party 2026

[`arizona-qso-party-2026-cabrillo.json`](arizona-qso-party-2026-cabrillo.json) is a simplified outside-Arizona entrant example based on the [sponsor's 2026 rules](https://www.azqp.org/rules). It exercises these documented rules:

- CW contacts earn two points and Phone contacts earn one point.
- Outside Arizona entrants count Arizona county multipliers again for each band and mode.
- One QSO with K7A earns a single 100-point bonus during the contest.
- Total score is QSO points multiplied by multipliers, plus bonus points.
- The exchange direction for this fixture is an outside entrant sending a state and an Arizona station sending a county.

The fixture has three CW QSOs with three counties and two Phone QSOs with one county. Its independent arithmetic is `8 × 4 + 100 = 132`. The repeated K7A contact is on a different mode, so it remains a valid QSO and can supply a new band/mode county multiplier; the K7A bonus is still counted once. Cabrillo uses the WWROF `PH` mode token for Phone, as defined by the [WWROF QSO data specification](https://wwrof.org/cabrillo/cabrillo-qso-data/).

The API integration test builds the dated QSO records at runtime, validates the fixture's ruleset via `/api/v1/rulesets/validate`, imports the generated Cabrillo log, scores it, checks manager-facing component details, publishes the result, and verifies that public standings expose only the aggregate explanation. Run it with:

```sh
.venv/bin/pytest -q backend/tests/test_results.py::test_azqp_2026_sponsor_fixture_scores_and_publishes_safe_explanation
```

This fixture does not resolve Arizona status from callsigns, validate the county list against station locations, adjudicate mobile/expedition operation, or model Arizona entrant multipliers. Those requirements need additional rules and authoritative data and remain outside this fixture's claim.

## CQ WW DX 2026 CW

[`cq-ww-dx-2026-cw-cabrillo.json`](cq-ww-dx-2026-cw-cabrillo.json) is a small, sponsor-linked profile for the [CQ WW 2026 rules](https://www.cqww.com/rules/). It exercises entrant-relative geography and independent multiplier totals through the Cabrillo upload, score-run, and public publication paths.

The pinned synthetic CTY subset resolves the entrant and three worked stations. The contacts cover the different-continent 3-point branch, same-country zero QSO points while retaining multiplier eligibility, and the North American same-continent/different-country 2-point branch. Expected totals are 5 QSO points, 3 CQ zones, 3 countries, and `(3 + 3) × 5 = 30` final points. The integration test asserts that the public output contains the score explanation and does not reveal raw QSOs or email data.

Run it with:

```sh
.venv/bin/pytest -q backend/tests/test_results.py::test_cqww_2026_sponsor_fixture_uses_contest_pinned_geography_and_separate_counts
```

This is a deliberately small scoring profile, not a complete implementation of CQ WW categories, eligibility, judging, or all geography branches.

## RSGB VHF/UHF/SHF General Rules 2026

[`rsgb-vhf-2026-distance-sessions-cabrillo.json`](rsgb-vhf-2026-distance-sessions-cabrillo.json) cites the [RSGB 2026 general rules](https://www.rsgbcc.org/vhf/rules/26rules/General.shtml). It scores an identical six-character locator as 1 point and IO91AA-to-IO92AA as 112 commenced kilometres under Contestmaster's configured six-character cell-center convention. The same worked station appears once in each of two fixed UTC sessions; the sent serial restarts at 001 and the second contact is not treated as a duplicate.

The Cabrillo record intentionally carries the sent serial and received locator needed by these checks. It is a focused scoring fixture, not a claim to encode every value required by every RSGB log profile. It does not verify an irregular cumulative activity calendar, an MGM special distance rule, or all RSGB exchange requirements.

Run it with:

```sh
.venv/bin/pytest -q backend/tests/test_results.py::test_rsgb_2026_sponsor_fixture_scores_distance_and_session_resets_end_to_end
```

## SARL ZS2 QSO Party 2026 ADIF

[`sarl-zs2-qso-party-2026-adif.json`](sarl-zs2-qso-party-2026-adif.json) cites the [SARL 2026 Contest Manual](https://mysarl.org.za/wp-content/uploads/2025/11/2026-SARL-Contest-Manual-Version-1.0-2025-11-12.pdf), ZS2 QSO Party rules. The manual accepts ADIF logs and awards an outside entrant 2 points for contacts with ZS2 stations, 1 point for contacts with other ZS call areas or Southern African countries, and 5 points for listed ZS2 club stations (with one contact per station). The fixture has one contact in each of those point cases and independently calculates `5 + 2 + 1 = 8`.

The API test imports an ADIF file using `STX_STRING` and `SRX_STRING` mappings, validates conditional point rules, scores the log, publishes the result, and checks the public score. The fixture intentionally covers only an outside entrant and a small subset of exchanges; the sponsor also requires an accompanying summary sheet for ADIF logs. It does not model local ZS2 scoring, every Southern African area, or the summary-sheet workflow.

Run it with:

```sh
.venv/bin/pytest -q backend/tests/test_results.py::test_sarl_zs2_2026_sponsor_fixture_scores_adif_exchange_end_to_end
```

## Residual fixture coverage

| Sponsor case / capability | Current evidence | Remaining limitation |
|---|---|---|
| Arizona QSO Party 2026: conditional mode points, distinct station bonus, county multipliers, Cabrillo exchange import | `test_azqp_2026_sponsor_fixture_scores_and_publishes_safe_explanation` | Simplified outside entrant; no station-region adjudication, mobile rules, or exhaustive county validation. |
| CQ WW DX 2026: entrant-relative country/continent branches and independent multiplier formula | `test_cqww_2026_sponsor_fixture_uses_contest_pinned_geography_and_separate_counts` | Simplified CW profile; no portable-location override or complete adjudication rules. |
| RSGB VHF/UHF/SHF 2026: distance method and fixed session resets | `test_rsgb_2026_sponsor_fixture_scores_distance_and_session_resets_end_to_end` | Focused Cabrillo facts; no irregular activity calendar, MGM special scoring, or full exchange profile. |
| SARL ZS2 QSO Party 2026: ADIF sent/received mapping and conditional points | `test_sarl_zs2_2026_sponsor_fixture_scores_adif_exchange_end_to_end` | Limited outside-entrant profile; no full event scoring, local-entry branches, or required summary-sheet workflow. |

See the [behavior matrix](../behavior-matrix.md) and issue [#394](https://github.com/ea7klk/contestmaster/issues/394) for the full conformance scope and remaining fixture work.
