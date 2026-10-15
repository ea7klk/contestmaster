# Preliminary ruleset feature checklist

**Research date:** 2026-10-15  
**Purpose:** A research-informed inventory of rule features a contest manager may need to configure with the graphical rules composer. The checkboxes are a design checklist; they do not mean every contest uses every rule. Each contest edition must be modeled from its own published rules.

## Guidance for the rule composer

- [x] Let a contest manager select reusable rule types and provide their parameters, rather than selecting a named contest with hidden behavior.
- [x] Support conditional rules such as “when entry category is Rover” or “for contacts on 144 MHz.”
- [x] Validate required parameters and conflicting selections before a ruleset can be saved or activated.
- [x] Version each ruleset and retain its source URL, edition/year, and effective contest. Do not silently change the rules used by an existing contest or score run.
- [x] Show a readable summary of the configured rules and example calculations before publishing a contest definition.
- [x] Keep the composer declarative. Contest-specific executable logic should remain behind the documented ruleset interface when a rule cannot be represented safely by the available rule types.
- [x] Distinguish rules the system can calculate from rules that require an entrant declaration, evidence, or human adjudication.
- [x] Represent every point, bonus, penalty, multiplier, intermediate score, and final score as an integer. Apply a contest's specified rounding rule where required and record it.

## Contest identity, schedule, and eligibility

- [x] Contest name, sponsoring organization, edition/year, ruleset version, and public description.
- [x] Eligibility by geography, license class, operator status, membership, or invited-station list.
- [x] Contest start and end instants in UTC.
- [x] Separate log submission cutoff in UTC, including late-log handling and any explicitly allowed extension process.
- [x] Operating-time limits independent of the contest's wall-clock period.
- [x] Off-time rules: minimum continuous off period, total permitted operating time, number of required breaks, and whether listening counts as operating.
- [x] Recurring schedules such as “first full weekend,” with the resolved UTC instants saved for each edition.
- [x] Accepted bands and band segments, with restrictions that may depend on mode, region, license, or category.
- [x] Accepted modes and mode families, including mixed-mode entries and whether the same station may be credited again on another mode.
- [x] Geographic or entity tables used by scoring, with an identified source and version: CQ/ITU zones, DXCC entities, ARRL/RAC sections, Maidenhead grids, continents, states, provinces, or contest-specific regions.

Examples show why these are separate settings: CQ WW defines a fixed operating window and HF bands, while Sweepstakes also limits logged operating time and requires minimum off periods. Submission deadlines are separate from the operating period and can change by edition. [CQ WW rules](https://www.cqww.com/rules/), [ARRL November Sweepstakes rules](https://contests.arrl.org/ContestRules/SS-Rules.pdf), [CQ WW 2026 rule changes](https://cqww.com/blog/2026-rule-changes/)

## Entry categories and overlays

- [x] Operator configuration: single operator, multi-operator, school/group, club, headquarters station, or other contest-defined type.
- [x] Transmitter configuration: one transmitter, multi-single, multi-two, multi-unlimited, one signal per band, or a contest-specific limit.
- [x] Power classes with contest-defined limits (for example QRP, low power, and high power), measured per contact, transmitter, band, or whole entry as the rule requires.
- [x] All-band or single-band entry, including whether all contacts must be uploaded but only the selected band scores.
- [x] Mode-specific categories: CW-only, phone-only, digital-only, analog-only, or mixed.
- [x] Assistance rules: unassisted, assisted/unlimited, spotting permitted or prohibited, and the allowed source of assistance.
- [x] Station/site type: fixed, portable, mobile, rover, emergency operations center, distributed, or other event-specific class.
- [ ] Category overlays that are in addition to a base category, such as rookie, youth, classic operator, limited antennas, or tribander/single-element.
- [x] Category compatibility rules and mutually exclusive choices. Make explicit whether an overlay creates a separate result listing or changes scoring.
- [ ] Checklog or non-scoring submission category.
- [ ] Entry-level declarations and evidence fields required to claim a category.
- [x] Operating restrictions that are only partly verifiable from a log (for example transmitter count, power, antenna, station radius, and human initiation) and the adjudication workflow for them.

CQ WW and WPX combine operator type, power, band choice, assistance, overlays, and multi-transmitter limits in different ways. Field Day has site classes based on group/site and power arrangements. Treat these as composable dimensions and encode category compatibility explicitly. [CQ WW rules](https://www.cqww.com/rules/), [CQ WPX rules](https://cqwpx.com/rules/), [ARRL Field Day rules](https://www.arrl.org/field-day-rules)

## Exchange definition

- [x] Define the exchange as an ordered list of named fields, each with a type, format, required/optional flag, and validation rule.
- [x] Support fields exchanged per contact and entry-level fields repeated across contacts.
- [x] Support common field types: signal report (RS/RST), serial number, callsign, category/precedence, section/region, CQ or ITU zone, grid locator, class, prefix, age/year, and contest-specific text.
- [x] Define which values are sent, received, or derived from the entrant's contest entry.
- [x] Define serial-number scope and starting value: whole log, band, transmitter, mode, or another rule-defined scope.
- [x] Validate fixed lengths, allowed enumerations, geographic formats, and sequence behavior without discarding the submitted text.
- [x] Support optional fields, conditional fields, and distinct exchange schemas by category, station type, band, or mode.
- [x] Preserve the raw submitted exchange and its parsed/normalized interpretation separately.
- [x] Provide an exchange preview/example for contest setup and clear row-level validation errors during log import.

The exchange can be a signal report plus CQ zone, a serial number, a long structured Sweepstakes exchange, a Field Day class and section, a VHF grid locator, or an IARU zone/HQ identifier. A generic untyped “exchange string” cannot express all the validation and scoring dependencies needed by these examples. [CQ WW rules](https://www.cqww.com/rules/), [ARRL Sweepstakes rules](https://contests.arrl.org/ContestRules/SS-Rules.pdf), [ARRL Field Day rules](https://www.arrl.org/field-day-rules), [ARRL VHF rules](https://contests.arrl.org/ContestRules/JanJunSep-VHF-Rules.pdf), [IARU HF rules](https://contests.arrl.org/ContestRules/IARU-HF-Rules.pdf)

## QSO eligibility, duplicate handling, and log validation

- [x] Required QSO data: UTC timestamp, band or frequency, mode, worked callsign, sent exchange, and received exchange.
- [x] Contest-period bounds, allowed band/mode combinations, and category-specific contact eligibility.
- [x] Contact geography rules, including who may contact whom and whether special stations are eligible.
- [x] QSO uniqueness key, configurable by contest: once per contest, per band, per mode, per band and mode, per rover grid, per transmitter, or another defined scope.
- [x] Whether a repeat contact is ignored, invalidated, or treated as a duplicate with a penalty.
- [x] Self-contact, same-site, cross-band, repeater, satellite, and remote-receiver restrictions where applicable.
- [x] Multi-operator band-change, mode-change, transmitter-count, and clock-window constraints, when sufficient log data exists to check them.
- [x] Off-time and maximum operating-time calculations, including whether an uploaded log may contain unscored contacts outside an entrant's claimed operating period.
- [x] Callsign and exchange matching rules, including permitted normalization, portable designators, and contest-specific call parsing.
- [x] Cross-check against submitted counterpart logs, if available, and the comparison window/tolerance for timestamps or copied exchanges.
- [x] Keep the entrant's claimed score for comparison while deriving the adjudicated score from contacts and rules.

The duplication key is not universal: CQ WW and WPX give band-level repeat credit, Sweepstakes limits a station to one credit regardless of band, and ARRL VHF rules permit a rover to work the same call from more than one grid. Keep uniqueness policy in the selected ruleset. [CQ WW rules](https://www.cqww.com/rules/), [CQ WPX rules](https://cqwpx.com/rules/), [ARRL Sweepstakes rules](https://contests.arrl.org/ContestRules/SS-Rules.pdf), [ARRL VHF rules](https://contests.arrl.org/ContestRules/JanJunSep-VHF-Rules.pdf)

## Scoring and multipliers

- [x] Integer QSO points by a configured context: fixed value, band, mode, distance, continent, entity, zone, station type, or a combination.
- [x] Zero-point contacts that still qualify for multiplier credit.
- [x] Multiplier kinds and sources: zones, countries/entities, prefixes, sections, grids, states/provinces, headquarters stations, officials, or other rule-defined values.
- [x] Multiplier uniqueness scope: once per contest, per band, per mode, per band and mode, per grid/site, or another explicit scope.
- [x] Multiplier eligibility conditions, including contacts that earn points, multipliers, both, or neither.
- [x] Final score expression and operation order, such as QSO points multiplied by multiplier count, power multiplier followed by bonuses, or a custom integer-only expression.
- [x] Integer bonus points with eligibility, proof requirements, caps, per-contact/per-entry basis, and whether they are added before or after a multiplier.
- [x] Penalties for busted calls, not-in-log (NIL), incorrect exchanges, invalid band/mode, excessive unverifiable contacts, or rule breaches; allow each penalty to remove credit, deduct points, reclassify an entry, or disqualify it as specified.
- [x] Tie-breakers and score precision (integer only), plus a complete explanation of each score component.
- [x] Club/team aggregation rules, membership eligibility, and allocation rules for multi-operator entries.
- [x] Separate claimed, provisional, and adjudicated scores; store immutable score runs tied to the ruleset version and source log revision.

Different scoring shapes appear in the sources: CQ WW combines QSO points with zone and country multipliers counted by band; WPX uses a prefix multiplier counted once regardless of band; Sweepstakes uses section multipliers; ARRL VHF weights QSO points by band and counts grid multipliers per band, with additional rover-specific multipliers; IARU combines zones and HQ stations; Field Day applies a power multiplier and then eligible bonuses. [CQ WW rules](https://www.cqww.com/rules/), [CQ WPX rules](https://cqwpx.com/rules/), [ARRL Sweepstakes rules](https://contests.arrl.org/ContestRules/SS-Rules.pdf), [ARRL VHF rules](https://contests.arrl.org/ContestRules/JanJunSep-VHF-Rules.pdf), [IARU HF rules](https://contests.arrl.org/ContestRules/IARU-HF-Rules.pdf), [ARRL Field Day rules](https://www.arrl.org/field-day-rules)

## Submission, imports, and publication

- [x] Accepted submission methods and file formats; keep format parsing in adapters separate from rules validation and scoring.
- [x] Cabrillo category headers and contest-specific QSO templates, including optional and repeated header fields.
- [x] Import validation with line/record numbers, actionable errors, warnings, and a summary of accepted/rejected records.
- [x] Preserve fields not understood by the current ruleset so imports can be reviewed or re-exported without silent data loss.
- [x] Submission cutoff, late-log classification, authorized extensions, corrections/resubmission, withdrawal, and checklog policies.
- [x] Public result/standings visibility, publication state, and how checklogs, late logs, reclassified entries, and disqualified entries appear.
- [x] Reproducible result exports and a versioned downloadable log/result format where needed.

Cabrillo is a common interchange format, but its category header describes entry attributes and the contest sponsor determines the valid category; claimed line scores may be recomputed during log checking. Keep the common QSO model separate from each contest's Cabrillo template. [WWROF Cabrillo developer notes](https://wwrof.org/cabrillo/cabrillo-specification-notes/), [ARRL log submission](https://www.arrl.org/log-submission)

## Adjudication, audit, and awards

- [x] Per-QSO decision states such as credited, duplicate, busted call, NIL, exchange error, out of period, out of band, or check required.
- [x] Rule-specific consequence for each state; do not assume every error has the same penalty.
- [x] Manual review with reason, reviewer, timestamp, supporting evidence, and a way to supersede a previous decision without erasing the audit trail.
- [x] Entry status workflow: submitted, validated, under review, scored, published, late, checklog, reclassified, withdrawn, or disqualified.
- [x] Entrant notification, appeal window, and finalization rules if the contest sponsor defines them.
- [x] Awards and rankings by category, overlay, geography/division, band, mode, operator, club, and any contest-specific grouping.
- [x] Award eligibility separate from score rank, including on-time entry, minimum participation, proof, and sponsor discretion.
- [x] Explainable result output: score, point totals, each multiplier, bonus/penalty totals, credited QSOs, and disqualification/reclassification reason.

Official judging policies vary even where the event calculation is similar: CQ and ARRL materials distinguish duplicate contacts, exchange errors, busted calls/NILs, penalties, appeals, and category reclassification. Make these independent policy settings and retain a human-review path. [CQ WW rules](https://www.cqww.com/rules/), [CQ WPX rules](https://cqwpx.com/rules/), [IARU HF rules](https://contests.arrl.org/ContestRules/IARU-HF-Rules.pdf)

## Initial reusable rule catalog of the system

The checked items below are adopted as the system's initial reusable ruleset catalog. They define the rule types Contestmaster must support in its rule composer and backend ruleset interface. They are not a single contest's configured rule values: each contest manager supplies and versions the parameters, and each contest's published rules determine which types and values apply. The detailed survey sections above provide the supporting requirements and examples for this initial catalog.

- [x] Schedule and UTC submission cutoff.
- [x] Category dimensions and compatibility constraints.
- [x] Declarative exchange schema and field validators.
- [x] QSO eligibility predicates and configurable duplicate scope.
- [x] Integer QSO-point rules and integer-only score composition.
- [x] Multiplier source, uniqueness scope, and eligibility.
- [x] Bonus and penalty rules with thresholds, caps, ordering, and evidence.
- [x] Operating-time, off-time, band-change, and transmitter constraints.
- [x] Log import/export schema and category mapping.
- [x] Cross-log checking, review decisions, and publication/award eligibility.
- [x] Ruleset edition/source provenance and immutable score-run explanations.

## Research sources

The examples above are paraphrased from official contest rules and format documentation. Contest committees can revise rules between editions; use these sources to discover rule patterns, then verify the exact edition selected for a real contest.

- [CQ World-Wide DX Contest rules (2026)](https://www.cqww.com/rules/) — schedule, bands, exchange, scoring, categories, multipliers, clubs, log deadlines, and judging.
- [CQ WW 2026 rule-change notice](https://cqww.com/blog/2026-rule-changes/) — edition-specific submission deadline and human-initiation rule changes.
- [CQ World-Wide WPX Contest rules](https://cqwpx.com/rules/) — serial exchange, prefix multiplier, off-time, categories, overlays, and multi-transmitter rules.
- [ARRL November Sweepstakes rules](https://contests.arrl.org/ContestRules/SS-Rules.pdf) — structured exchange, one-contact uniqueness, operating/off-time limit, sections, and score formula.
- [ARRL Jan/June/September VHF rules](https://contests.arrl.org/ContestRules/JanJunSep-VHF-Rules.pdf) — grid exchanges, band-weighted points, per-band grids, and rover scoring/category variants.
- [ARRL Field Day 2026 rules](https://www.arrl.org/field-day-rules) — operating classes, class/section exchange, mode points, power multiplier, bonuses, and club aggregation.
- [IARU HF World Championship rules](https://contests.arrl.org/ContestRules/IARU-HF-Rules.pdf) — zone and HQ exchange variants, geographic point tiers, HQ/official multipliers, and operation restrictions.
- [WWROF Cabrillo specification notes](https://wwrof.org/cabrillo/cabrillo-specification-notes/) — developer guidance for reading/writing Cabrillo and category/header/QSO representation.
- [ARRL log submission](https://www.arrl.org/log-submission) — official submission guidance and use of Cabrillo.
