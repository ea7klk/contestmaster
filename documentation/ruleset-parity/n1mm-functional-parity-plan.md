# N1MM Built-in Contest Ruleset Parity Plan

## Purpose and scope

This plan turns the user-provided gap analysis into staged work for Contestmaster. That report statically examined the built-in contest handlers in N1MM Logger+ update 1.0.11466 (2026-10-13) and compared them with Contestmaster ruleset schema v2 at commit `8661bbd`. The supplied report is outside this repository; its findings needed for implementation are summarized below.

“Functional parity” means that Contestmaster can express and reproducibly score the same rule outcome for a selected, sponsor-verified contest edition. It does not mean reproducing N1MM’s logger UI, operating workflow, private APIs, implementation language, every historical handler, or every UDC. N1MM’s executable dispatch inventory is a source of test scenarios, not an authoritative rulebook. A sponsor’s published edition rules remain the authority.

Do not translate handlers mechanically. First establish the applicable published rule, required input facts, output, and edge cases. Implement reusable declarative primitives for recurring rule patterns. Do not load N1MM code, add arbitrary contest-supplied code or `eval`, or claim support because a JSON draft validates. Any unsupported sponsor requirement must remain explicit and block activation/scoring where necessary.

## Existing capabilities and confirmed gaps

Contestmaster already has typed rules for categories, exchange validation, eligibility, duplicate identity/effect, points, multiple multiplier rules and scopes, bonuses, penalties, integer score formulas, operating constraints, import mappings, and review hooks. Contest configuration separately owns event dates, recurrence, and the log cutoff. See the [ruleset schema](../../backend/app/rulesets/schema.py), [scoring engine](../../backend/app/rulesets/engine.py), [rule catalog](../../backend/app/rulesets/registry.py), and [radio contest body of knowledge](../radio-contest-body-of-knowledge/README.md#current-contestmaster-capability-comparison).

The comparison identified these functional gaps:

1. **Distance scoring (G1):** no entrant/worked-station distance fact or distance scoring service.
2. **Entrant-relative geography (G2):** no native same-country/same-continent comparison using the entrant’s resolved station location.
3. **Independent multiplier totals (G3):** the final formula can use only the combined multiplier count, not each configured multiplier rule’s count independently.
4. **Compound event-specific scoring (G4):** QSO Party patterns need reusable rules for conditional point matrices and distinct bonus-station/county counts, beyond a simple per-QSO bonus.
5. **Workability and derived facts (G5):** some contact checks depend on entrant location, validated exchange/reference lists, or other derived facts not currently available to rules.
6. **Handler-specific scoring behavior (G6):** code-only behavior has no direct representation. This is addressed by identifying reusable primitives per verified behavior, not by embedding custom code.
7. **Exchange and format semantics (G7):** contest-specific ordered, conditional, and asymmetric exchanges need end-to-end coverage through supported upload adapters and validation.
8. **Scoring-relevant session resets (G8):** some contests reset duplicate keys, multipliers, or sent serial sequences by operating session. Event schedule and recurrence remain contest configuration, not ruleset fields.

Existing coverage is partial: ordinary fixed/look-up scores, multipliers, duplicates, and supported exchange mappings already work. The [body-of-knowledge gap table](../radio-contest-body-of-knowledge/README.md#current-contestmaster-capability-comparison) records additional cautions including distance, QTC traffic, team/series aggregation, and human adjudication. Those broader areas are not silently included in this N1MM parity plan unless a specific built-in profile and sponsor rule demonstrates the need.

## Work sequence

### Workstream 1 — Establish a traceable parity benchmark

Build a behavior matrix from the N1MM gap report. For each selected handler branch, record the source token, relevant executable behavior, sponsor rule URL and edition, required facts, expected scoring effect, whether current Contestmaster supports it, and a test case. Start with representative cases for each gap rather than attempting to convert all 263 dispatch keys at once. Mark aliases, discontinued profiles, token-specific branches, unsupported sponsor rules, and unresolved cases explicitly.

### Workstream 2 — Add reusable scoring facts and formula variables

Implement entrant-relative geography and distance-derived scoring as explicit, validated facts/services with defined missing-data behavior and deterministic integer units/rounding. Expose independent multiplier-rule totals to the score formula while preserving the existing combined count for compatibility. Store enough score detail to explain each component and pin geographic reference versions when consumed.

### Workstream 3 — Express conditional and aggregate rules safely

Extend declarative scoring for verified patterns that recur across sponsor rules: conditional point tables, distinct bonus-call/entity/section/county counts, and contest-specific workability predicates over available exchange, entry, and resolved station facts. Validate data dependencies and formats. Keep data-driven lists versioned/provenanced where needed. Do not make an N1MM-specific generic rule or embed arbitrary code.

### Workstream 4 — Complete input and session behavior

Specify and test supported-format mappings for the verified exchange patterns, including conditional/asymmetric fields and serial requirements. Add scoring-relevant session identities/reset policies for duplicate scope, multiplier uniqueness, and serial sequences where sponsor rules require them. Preserve UTC instants and keep recurrence/schedule generation on the contest record.

### Workstream 5 — Prove behavior with conformance fixtures

For each implemented primitive, include behavior-focused unit tests and API/import integration tests where boundaries matter. Add sponsor-linked fixtures with valid and invalid logs and known component totals. Compare the same input/rules against independently hand-calculated expected outcomes; do not use the N1MM executable as the sole oracle. Include boundary, missing-fact, duplicate, reset, and integer-rounding cases. Run representative profiles end-to-end through import, validation, scoring, and score explanation.

## Issue breakdown and dependencies

The implementation is tracked by parent issue [#385](https://github.com/ea7klk/contestmaster/issues/385) and child issues #386–#394. They are linked using GitHub's parent/sub-issue relationship. Each child has its own acceptance criteria and verification expectations.

| Child | Outcome | Dependencies |
|---|---|---|
| [#386 — Parity benchmark and behavior traceability matrix](https://github.com/ea7klk/contestmaster/issues/386) | Turn G1–G8 into sponsor-verified, testable cases; classify capabilities versus gaps. | None; do first. |
| [#387 — Distance-derived scoring](https://github.com/ea7klk/contestmaster/issues/387) | Add deterministic distance facts and integer scoring rules, including defined grid precision and missing-data behavior. | Benchmark. |
| [#388 — Entrant-relative station geography](https://github.com/ea7klk/contestmaster/issues/388) | Make entrant country/continent facts available and support verified relative-geography scoring. | Benchmark; may reuse master-data pinning. |
| [#389 — Per-rule multiplier totals in score formulas](https://github.com/ea7klk/contestmaster/issues/389) | Allow formula steps to refer to distinct multiplier totals while preserving aggregate compatibility. | Benchmark. |
| [#390 — Conditional and distinct-count scoring primitives](https://github.com/ea7klk/contestmaster/issues/390) | Cover verified QSO Party patterns such as conditional points and unique bonus station/county counts. | Benchmark; formula variables as needed. |
| [#391 — Declarative workability and derived-fact validation](https://github.com/ea7klk/contestmaster/issues/391) | Add the minimum reusable predicates/reference-data dependencies proven by the benchmark. | Benchmark; entrant geography where required. |
| [#392 — Exchange/import conformance for sponsor rules](https://github.com/ea7klk/contestmaster/issues/392) | Validate conditional/asymmetric exchange semantics through each supported format adapter. | Benchmark. |
| [#393 — Scoring session reset policies](https://github.com/ea7klk/contestmaster/issues/393) | Support sponsor-required reset boundaries for duplicates, multipliers, and serial sequences without moving event schedules into rulesets. | Benchmark. |
| [#394 — Sponsor-linked scoring conformance fixtures](https://github.com/ea7klk/contestmaster/issues/394) | Exercise selected representative built-in profiles end-to-end and document residual gaps. | Relevant implemented primitives above. |

## Completion criteria

- Every implemented behavior links to a sponsor rule edition and a behavior-level expected result.
- The composer and API expose only validated declarative rules; unsupported conditions fail clearly rather than defaulting silently.
- Existing schema-v2 imports, current rulesets, and combined multiplier behavior remain compatible or receive an explicit migration/versioning plan.
- All stored and intermediate scoring values remain integers with sponsor-defined rounding captured in the ruleset and tests.
- Unit and cross-layer tests cover valid, invalid, and boundary paths; commands and outcomes are recorded on the child and parent GitHub issues.
- Representative contest profiles complete import, validation, scoring, and explanation with expected component totals.
- A final residual-gap list distinguishes unsupported sponsor behaviors from stale/alias/discontinued N1MM executable dispatches. No claim of universal parity is made without evidence.

## Reference material

- User-supplied static comparison report — executable gap analysis and full dispatch index (outside this repository; version and findings summarized above).
- [Contestmaster radio contest body of knowledge](../radio-contest-body-of-knowledge/README.md) — sponsor rule patterns and current coverage review.
- [N1MM supported contests list](https://n1mmwp.hamdocs.com/manual-supported/contests-list/) — product support index, not a substitute for sponsor rules.
- The sponsor’s current published rules for each selected contest edition — authoritative source for implemented behavior.
