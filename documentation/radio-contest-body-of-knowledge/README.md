# Amateur-radio contest rules: body of knowledge

**Research snapshot:** 2026-10-18

**Calendar window reviewed:** 2026-10-01 through 2027-09-30
**Purpose:** A structured reference for comparing real contest rules with Contestmaster's ruleset schema, scoring engine, and visual composer.

## How to use this document

This is a normalized inventory of rule patterns, not a ruleset for any one contest and not a reproduction of calendar records or contest rulebooks. Use the stable pattern IDs (`SCH-*`, `CAT-*`, `XCH-*`, `DUP-*`, `SCORE-*`, `MULT-*`, `OPS-*`, and `PUB-*`) when reviewing a ruleset or filing a capability gap.

For each contest edition under review:

1. Use the [WA7BNM 12-month calendar](https://www.contestcalendar.com/contestcal.php) to discover events and their dates. Its reviewed horizon runs from October 2026 through September 2027. Repeated weekly events should be treated as recurring series, not separate rule families.
2. Open the linked contest detail page to identify the sponsor, advertised exchange, bands, modes, categories, scoring summary, submission deadline, and official rules link.
3. Use the sponsor's published rules for the selected edition as the authority. Calendar summaries and historical rules can be incomplete, provisional, or stale. If the sponsor has not published rules for the future edition, record the uncertainty and do not infer that last year's rules are unchanged.
4. For each rule, record the exact source section, Contestmaster configuration path, engine facts needed, and a behavior test. Classify it as `supported`, `partial`, `gap`, or `not applicable`.
5. Keep contest-specific operations declarative. If a rule cannot be represented and calculated safely, identify the missing capability rather than adding a contest-name branch or hiding behavior in a default.

All contest rule descriptions below are paraphrased. The calendar is a discovery source; it is not the authority on interpretation. This document does not copy or provision third-party multiplier lists. In particular, it does not authorize ingestion or redistribution of the ARRL DXCC list. Use permitted master-data sources and contest-specific rule values.

## Review set from the calendar horizon

The following linked event pages provide a cross-section of distinct contest families in the reviewed calendar year. This is a rule-pattern sample, not an exhaustive copy of every calendar occurrence.

| Family | Event in the calendar window | Observed rule characteristics | Rule authority |
|---|---|---|---|
| Worldwide HF DX | [CQ WW SSB detail](https://www.contestcalendar.com/contestdetails.php?ref=172), Oct 2026; [CQ WW RTTY detail](https://www.contestcalendar.com/contestdetails.php?ref=130), Sep 2027 | Zone/entity multipliers, per-band duplicate policy, geographic point tiers, multiple power/operator/transmitter classes, overlays, operating limits, and a final multiplier formula | [CQ WW rules](https://www.cqww.com/rules/); [CQ WW RTTY rules](https://www.cqwwrtty.com/) |
| Prefix DX | CQ WPX SSB/CW calendar events; 2027 SSB dates are also listed by the [sponsor](https://cqwpx.com/) | Prefix multiplier; serial exchange; band-dependent point tiers; single-op off-time and distinct serial scopes for some multi-op classes | [CQ WPX rules](https://cqwpx.com/rules/) |
| QSO party | [California QSO Party detail](https://www.contestcalendar.com/contestdetails.php?ref=140), Oct 2026 | Asymmetric eligibility and exchanges for in-state/out-of-state entries; county/state/province values; per-mode/per-band repeat credit; maximum multiplier count; operating-time limit | [CQP rules](https://www.cqp.org/Rules.html) |
| Structured domestic exchange | [ARRL Sweepstakes CW detail](https://www.contestcalendar.com/contestdetails.php?ref=177), Nov 2026 and Nov 2027 | Long ordered exchange containing serial, precedence, callsign, check, and section; one contact per station; a total operating-time cap with minimum off periods | [ARRL Sweepstakes](https://www.arrl.org/sweepstakes) |
| Digital short contest | [DARC FT4 detail](https://www.contestcalendar.com/contestdetails.php?ref=745) | FT4-only, two HF bands, report plus four-character grid, per-band repeats, prefix multipliers, short UTC operating window | [DARC FT4 rules](https://www.darc.de/der-club/referate/conteste/ft4-contest/ft4-rules/) |
| RTTY DX with transfer traffic | [WAE RTTY detail](https://www.contestcalendar.com/contestdetails.php?ref=183), Nov 2026 and Nov 2027 | Serial exchange, per-band repeats, single-op operating/off-time limits, and additional QTC traffic under the sponsor rules | [DARC WAE contest page](https://www.darc.de/der-club/referate/conteste/wae-dx-contest/en/) |
| Emergency/community field event | ARRL Field Day is listed annually in June | Entry class depends on station/site and transmitter setup; contact value depends on mode; a power multiplier and evidence-backed bonuses affect the score; club aggregation is separate from individual entries | [ARRL Field Day 2026 rules](https://www.arrl.org/field-day-rules/) |
| VHF / rover | CQ WW VHF and multiple VHF/UHF contests appear in the calendar; see [CQ WW VHF rules](https://www.cqww-vhf.com/rules/) | Grid exchange and per-band grid multipliers; band-specific QSO points; a rover can establish a new operating identity by changing grid | [CQ WW VHF rules](https://www.cqww-vhf.com/rules/); [IARU Region 1 VHF-up rules](https://www.iaru-r1.org/wp-content/uploads/2024/02/Rules-IARU-R1-VHF-up-Contests.pdf) |

## Rule-pattern inventory and current model comparison

Status describes today's repository implementation, not a promise that all variants of a pattern are supported. The main schema is `backend/app/rulesets/schema.py`; deterministic rule execution is in `backend/app/rulesets/engine.py`; the UI is `frontend/src/views/RulesetComposerView.vue` plus `RuleSchemaEditor.vue` and `ConditionEditor.vue`.

| ID | Rule pattern and examples | Current representation | Status and analysis notes |
|---|---|---|---|
| SCH-01 | Fixed UTC start/end and an independent log cutoff; CQ WW, CQP, Sweepstakes | Contest configuration; submission rule handles late policy | **Supported.** Dates/cutoff belong to the contest edition, not the reusable ruleset. |
| SCH-02 | Recurring calendar patterns such as a full weekend, monthly sprint, or fixed annual weekend | Contest periodicity and saved edition UTC instants | **Partial.** Calendar discovery provides recurrence clues. Confirm each sponsor's date convention; do not derive unscheduled edition times from an approximate calendar summary. |
| SCH-03 | Multiple operating blocks or an event with scheduled pauses | One contest start/end plus QSO time eligibility; operating constraints handle off-time | **Gap for explicit sessions.** A wall-clock interval that includes an inactive gap is not equivalent to an allowed-window schedule. Test that QSOs in each gap are excluded if a contest uses split periods. |
| SCH-04 | Calendar advertises local time, not UTC | Convert only after the sponsor defines the relevant timezone and date; persist UTC | **Requires source clarification.** Some calendar entries explicitly say “local.” Do not assume the operator's locale or the server timezone. |
| ELG-01 | Asymmetric who-may-work-whom rules; CQP awards CA and non-CA stations differently | Eligibility condition predicates and conditions on points/multipliers | **Partial.** Conditions can express simple predicates against current entry/QSO facts. Confirm that participant location/region is available as a trusted fact; free-text exchange alone must not be mistaken for verified station location. |
| ELG-02 | Special entrant classes or geographic boundaries | Category dimensions, exchange fields, and declarative conditions | **Partial.** Generic categories exist, but the engine has a finite fact set. A condition is useful only when its fact is populated and validated. |
| CAT-01 | Operator, power, assisted status, band, mode, station type, transmitter count | `CategoryRule.dimensions` and choice values | **Supported for classification.** Rulesets can define dimensions and incompatibilities. Contest-specific limits must be described in the choice/rule text, not inferred from labels. |
| CAT-02 | Overlay categories such as Rookie/Youth/Classic, with both a base-category result and a separate overlay result | Category choices can record an overlay-like value; workflow hooks can request downstream work | **Partial/gap for parallel rankings.** A category value alone does not produce a second independent scored listing or award. Define whether an overlay changes eligibility, scoring, placement, or creates an additional result before claiming support. |
| CAT-03 | Class depends on station construction, operator count, transmitters, power source, or setup facts; Field Day | Categories plus entry declarations and evidence-keyed bonuses | **Partial.** Declarations can capture facts, but complex derived classes and evidence review require explicit workflows. Never infer transmitter count or power source from a Cabrillo category label alone. |
| XCH-01 | Ordered, multi-field exchange; Sweepstakes, CQP, serial contests | `ExchangeRule.fields`, direction, typed validators, enum choices, serial scope | **Supported for defined fields.** Preserve sent/received raw values. Add an edition-specific test for field order, requiredness, parsing, and serial behavior. |
| XCH-02 | Conditional exchange schema by entrant type/location/mode | Multiple exchange declarations and conditions; import adapters | **Partial.** Verify that every condition is tied to data actually available in the upload or entry declaration. A schema that accepts a field does not by itself implement sponsor-specific parsing. |
| XCH-03 | QTC traffic: exchange a record of prior contacts, not merely the current QSO; WAE | No QTC message collection, direction, sequence, validation, or score facts in the current common model | **Gap.** Requires a first-class transfer/message record and rules for sent/received QTC limits, ordering, duplicate transfers, cross-checking, and integer score contribution. Do not model a QTC as an ordinary exchange field. |
| XCH-04 | Serial counter scope varies by entire entry, band, mode, or transmitter | `ExchangeField.serial_scope` | **Supported for declared scopes.** Test counter resets and sequencing separately for the exact entry category. |
| DUP-01 | Duplicate key varies by contest, band, mode, grid, transmitter; CQ WW, CQP, VHF | `DuplicateRule.scope`; duplicates may optionally count for multipliers without points | **Supported for current scopes.** The scope vocabulary is finite. CQP's “once per mode/band/county” needs a county or equivalent location key before it can be represented exactly. |
| DUP-02 | A rover's same callsign can become a new contact after moving grid | Grid-aware duplicate scope and QSO grid fact | **Partial.** A grid can participate in a duplicate key, but the model does not yet establish a time-varying station-location/rover itinerary as a first-class, verified fact. Validate location transitions and opponent-side credit rules. |
| SCORE-01 | Integer contact points depend on entity, continent, zone, mode, band, or exchange | `PointRule.fact` plus lookup values/default and rule conditions | **Supported for enumerated current facts.** Missing values need explicit default/review behavior. Arithmetic, intermediate points, penalties, and final score remain integers. |
| SCORE-02 | Distance or locator-distance points; many VHF-up contests | No distance fact or grid-to-distance calculation in current `ScoringQso` | **Gap.** Requires a defined locator precision, station coordinates, distance algorithm/rounding, missing-grid behavior, and integer conversion agreed from the sponsor rule. |
| MULT-01 | Entity/country, continent, CQ/ITU zone, grid, band or mode multipliers | `MultiplierRule.source_fact` and uniqueness scope; CTY-resolved entity/continent/zones are available in scoring | **Supported for current source facts and scopes.** Dataset semantics and contest-specific definitions must be version-pinned and documented. |
| MULT-02 | Prefix, suffix, exact callsign, or special-call multipliers; CQ WPX and many digital events | `qso.worked_callsign` is available; there is no derived `qso.prefix` or `qso.suffix` fact. Conditions can filter explicit callsign values, but there is no dedicated configured callsign-set or prefix-extraction rule | **Partial/gap.** A callsign used as a multiplier source is not the same as prefix normalization. Prefix construction must follow each contest's portable/special-call rules, with test cases at ambiguity boundaries. Treat explicit callsign filters as candidate only after verifying canonicalization and validation. |
| MULT-03 | Section, county, DOK, state/province, or another contest-specific multiplier | Can use configured exchange fields as multiplier facts; no universal source table for all such areas | **Partial.** Values may be declared as rule-specific enums when permitted. Keep lists tied to source/provenance and contest edition; do not add restricted master datasets to solve it. |
| MULT-04 | Cap the total or per-group multiplier credit; CQP has a scored multiplier maximum | No dedicated maximum-multiplier/cap property in `MultiplierRule` | **Gap.** A capped tally is distinct from filtering which multiplier keys are eligible. Define cap ordering and score explanation before adding support. |
| SCORE-03 | Multiplicative points-times-multipliers formulas; bonuses before/after multiplier; power multiplier | `ScoreFormulaRule`, integer `BonusRule`, `PenaltyRule`, and entry `power_multiplier` | **Supported for declarative formulas.** Test exact order, cap behavior, and ties using integer arithmetic. |
| SCORE-04 | QSO points plus transfer-traffic points; QTC example | No QTC scoring input | **Gap; depends on XCH-03.** Do not count message points without validated transfer records. |
| SCORE-05 | Club totals, club membership radii, split allocation of multi-op scores | No club/team result aggregate rule in the per-entry score engine | **Gap.** Treat aggregation, membership eligibility, allocation percentages, minimum-entry thresholds, and output rows as a separate group-result capability. Any fractional split must have an explicitly specified integer rounding rule. |
| OPS-01 | Maximum operating time, minimum/required off periods, and session gap | `OperatingConstraintRule` | **Supported for represented constraints.** Rules differ on whether listening counts as operating and whether post-limit QSOs stay in the log but are unscored; model the exact consequence and test edge boundaries. |
| OPS-02 | Maximum band changes per clock hour / minimum dwell; multi-op band hopping | Band-change window, maximum changes, and minimum dwell fields | **Supported for current constraint shape.** Validate whether counting windows are fixed UTC clock hours, rolling windows, or begin with the first QSO on a band; these are not interchangeable. |
| OPS-03 | Simultaneous transmitters, one signal per band, run/multiplier station and independent clocks | Maximum transmitters and signal-per-band flags, transmitter QSO field, workflow review | **Partial.** Basic limits exist. Rules such as CQ WW multi-single 10-minute run/multiplier roles need role-aware logs and precise clock grouping; review-only checks must be identified as such. |
| OPS-04 | Location radius, remote receiver, self-spotting, post-contest correction, human initiation | Eligibility/rule conditions and workflow hooks | **Partial / often human review.** A log cannot prove every operational fact. Store declarations and review actions; don't describe a log-only calculation as enforcement of off-air conduct. |
| PEN-01 | Duplicate treatment, exchange mismatch, NIL/busted-call penalties, reclassification or DQ | Duplicate effects, penalty actions, cross-log/adjudication workflows | **Partial.** Each sponsor's penalty basis and lookup tolerances differ. Missing counterpart logs or unverifiable facts must not silently become a universal penalty. |
| PUB-01 | Entry deadline, late status, checklog, withdrawal and published-list policy | Contest cutoff, submission rule, entry status, immutable score/publication snapshots | **Supported for core lifecycle.** Sponsor-specific late-log publication and award eligibility may differ; configure the policy for each contest. |
| PUB-02 | Required headers, QSO columns, accepted file formats and category mapping | `FormatMappingRule` and Cabrillo/ADIF boundary adapters | **Supported for declared formats.** Keep Cabrillo field semantics per WWROF. Verify the selected contest's required fields and category mappings against its sponsor template. |
| PUB-03 | Awards/rankings by base category, overlay, geography, club, or award eligibility | Published snapshots expose configured categories and scores | **Partial.** Independent overlay awards and aggregate club competitions are not implied by category tags or score snapshots. |

## Current engine facts: guardrail for reviews

The scoring engine currently accepts a finite, typed QSO context. It includes QSO ID/time, worked callsign, band, mode, grid, transmitter, continent, entity, CQ zone, ITU zone, sent/received exchanges; entry ID, categories, declarations, and power multiplier; and station callsign. The `MultiplierRule` schema's string path is validated against this set. A future field name in JSON is not an implemented capability until it is accepted, populated, and tested end to end.

The current point-source vocabulary is `fixed`, `band`, `mode`, `continent`, `entity`, `cq_zone`, `itu_zone`, and received `exchange`. The multiplier scopes are `contest`, `band`, `mode`, `band_mode`, `grid`, and `transmitter`. The duplicate scopes are a separately enumerated list. Use these exact vocabularies when doing a schema audit; do not treat them as synonyms.

## Suggested analysis and regression cases

These are review prompts for ruleset construction and future tests, not universal contest rules.

| Test ID | Setup | Expected rule question |
|---|---|---|
| BOK-T01 | Same callsign worked on two bands and two modes | Is the duplicate scope per contest, band, mode, or band+mode? Does a duplicate contribute a multiplier while scoring zero QSO points? |
| BOK-T02 | Same station appears in a new rover grid | Which entrant's contact is new, what location-change proof is required, and does the multiplier scope reset? |
| BOK-T03 | Entry location changes whether a contact is valid or which exchange/points apply | Is location a verified entry fact or only an untrusted received exchange? Test both sides of the geography branch. |
| BOK-T04 | Exchange includes a serial and several text/enumerated fields | Are fields ordered, directional, required, bounded, and serial-scoped correctly? Test first/last serial and malformed values. |
| BOK-T05 | Entry has base category plus a claimed overlay | Does the overlay alter category eligibility, add a parallel listing, alter score, or require evidence? Test the published result shape. |
| BOK-T06 | QSO falls exactly on an allowed band segment edge or in a scheduled gap | Are endpoints inclusive/exclusive as sponsor says? Can the current model represent the gap without rejecting valid surrounding QSOs? |
| BOK-T07 | Single op exceeds operating time and later submits further QSOs | Are late-in-operation QSOs retained for cross-checking but left unscored, removed, or reviewed? Do off-time boundaries match the official counting rule? |
| BOK-T08 | Multi-op switches bands at 12:59/13:00 UTC | Is the rule a fixed clock-hour count, rolling interval, or first-QSO-anchored period? Test boundary transition. |
| BOK-T09 | A QSO is valid but yields zero points; the multiplier is already worked | Is it still a new multiplier? Does a duplicate count for multipliers? Check the rule-specific ordering. |
| BOK-T10 | A received QTC repeats or conflicts with a previously sent/received record | Which transfer identity, direction, sequence, and scoring rule apply? The current model needs an explicit QTC capability first. |
| BOK-T11 | Grid exchanges imply distance points | Which locator precision and distance algorithm are used? What integer rounding and missing-grid action are required? |
| BOK-T12 | A claimed club bonus is split among multiple clubs | What eligibility/evidence and allocation apply? How are fractional shares rounded to integer points, and are club totals separate from participant standings? |
| BOK-T13 | Log is submitted after event end but before configured cutoff | Is it timely by the application cutoff? Is award eligibility a separate rule? Do not equate contest end with deadline. |
| BOK-T14 | Multiplier list has more values than a ruleset cap | Is the cap applied before or after grouping by band/mode? How are suppressed credits explained? |

## Review checklist for each new contest ruleset

- [ ] Record sponsor, edition/year, authoritative rule URL, source-edition label, and the reviewed publication date.
- [ ] Configure UTC contest occurrence and independent UTC submission cutoff outside the reusable ruleset.
- [ ] Mark each contest statement as machine-verifiable, participant-declared, or human-adjudicated.
- [ ] Define entry dimensions and valid choices, compatibility, overlay semantics, and publication grouping.
- [ ] Define every sent/received exchange field and parser mapping, including serial scope and allowed values.
- [ ] Define contact eligibility, repeat-contact key, duplicate point effect, and duplicate multiplier effect separately.
- [ ] Define the point-value table and each multiplier's source, grouping scope, cap, and interaction with zero-point/duplicate contacts.
- [ ] Express score operation order with integer arithmetic; state any rounding rule and tie-breaker.
- [ ] Define operating-time and transmitter/band-change windows with exact interval semantics.
- [ ] Define log format, mandatory headers/columns, late/checklog handling, publication eligibility, and required evidence.
- [ ] Identify features that the model or engine does not currently support; do not work around them with contest-name conditionals.
- [ ] Add worked examples and boundary tests from the sponsor rules before a ruleset is treated as verified.

## Source register

### Calendar and event detail pages

- [WA7BNM Contest Calendar, 12-month view](https://www.contestcalendar.com/contestcal.php) — event discovery and upcoming date horizon. Reviewed 2026-10-18.
- [CQ WW SSB contest detail](https://www.contestcalendar.com/contestdetails.php?ref=172) — calendar summary for bands, exchange, points/multipliers, categories, deadline, and source rules.
- [California QSO Party detail](https://www.contestcalendar.com/contestdetails.php?ref=140) — calendar summary for asymmetrical participant roles, county multipliers, and repeat policy.
- [ARRL Sweepstakes CW detail](https://www.contestcalendar.com/contestdetails.php?ref=177) — calendar summary for long exchange and operating-time restriction.
- [DARC FT4 Contest detail](https://www.contestcalendar.com/contestdetails.php?ref=745) — calendar summary for FT4, grid exchange, per-band duplicate rule, and prefix multipliers. It reported no future date known at review time; recurring dates must therefore not be assumed as confirmed.
- [WAE RTTY detail](https://www.contestcalendar.com/contestdetails.php?ref=183) — calendar summary for operating/off-time, serial exchange, and link to sponsor rules.
- [CQ WW RTTY detail](https://www.contestcalendar.com/contestdetails.php?ref=130) — calendar summary showing the closing month of the reviewed window.

### Official sponsor rules

- [CQ World-Wide DX rules](https://www.cqww.com/rules/) — 2026 objective, exchange, six HF bands, zone/country scoring, power/operator categories, overlays, transmitter rules, deadline, and log checking.
- [CQ WPX rules](https://cqwpx.com/rules/) — prefix construction, serial scope, band-dependent points, off time, categories, and multi-operator details.
- [California QSO Party rules](https://www.cqp.org/Rules.html) — 2026 exchange, asymmetric entry objectives, mode/band repeat credit, operating caps, multipliers, and integer score formula.
- [ARRL November Sweepstakes](https://www.arrl.org/sweepstakes) — serial/precedence/callsign/check/section exchange, contact uniqueness, total operating-time and off-time rules, and deadline.
- [ARRL Field Day rules](https://www.arrl.org/field-day-rules/) — station classes, exchange, mode-specific QSO points, highest-power-based multiplier, evidence-bearing bonuses, and aggregate club scoring.
- [CQ WW VHF rules](https://www.cqww-vhf.com/rules/) — grid locators, per-band multipliers and points, rover movement/scoring.
- [IARU Region 1 VHF-up rules](https://www.iaru-r1.org/wp-content/uploads/2024/02/Rules-IARU-R1-VHF-up-Contests.pdf) — locator fields and distance-based scoring example. This source illustrates a rule pattern only; it does not add IARU regions to Contestmaster's master data or current requirements.
- [DARC FT4 contest rules](https://www.darc.de/der-club/referate/conteste/ft4-contest/ft4-rules/) — sponsor rules linked from the calendar detail page; recheck the edition before modeling.
- [DARC WAE DX contest rules](https://www.darc.de/der-club/referate/conteste/wae-dx-contest/en/) — sponsor rule entry point for the WAE formats and QTC provisions; use the relevant mode/year rule sheet when modeling.
