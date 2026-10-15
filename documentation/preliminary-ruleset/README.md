# Preliminary ruleset feature checklist

**Research date:** 2026-10-15  
**Purpose:** A research-informed inventory of rule features a contest manager may need to configure with the graphical rules composer. The checkboxes are a design checklist; they do not mean every contest uses every rule. Each contest edition must be modeled from its own published rules.

## Guidance for the rule composer

- [ ] Let a contest manager select reusable rule types and provide their parameters, rather than selecting a named contest with hidden behavior.
- [ ] Support conditional rules such as “when entry category is Rover” or “for contacts on 144 MHz.”
- [ ] Validate required parameters and conflicting selections before a ruleset can be saved or activated.
- [ ] Version each ruleset and retain its source URL, edition/year, and effective contest. Do not silently change the rules used by an existing contest or score run.
- [ ] Show a readable summary of the configured rules and example calculations before publishing a contest definition.
- [ ] Keep the composer declarative. Contest-specific executable logic should remain behind the documented ruleset interface when a rule cannot be represented safely by the available rule types.
- [ ] Distinguish rules the system can calculate from rules that require an entrant declaration, evidence, or human adjudication.
- [ ] Represent every point, bonus, penalty, multiplier, intermediate score, and final score as an integer. Apply a contest's specified rounding rule where required and record it.

## Contest identity, schedule, and eligibility

- [ ] Contest name, sponsoring organization, edition/year, ruleset version, and public description.
- [ ] Eligibility by geography, license class, operator status, membership, or invited-station list.
- [ ] Contest start and end instants in UTC.
- [ ] Separate log submission cutoff in UTC, including late-log handling and any explicitly allowed extension process.
- [ ] Operating-time limits independent of the contest's wall-clock period.
- [ ] Off-time rules: minimum continuous off period, total permitted operating time, number of required breaks, and whether listening counts as operating.
- [ ] Recurring schedules such as “first full weekend,” with the resolved UTC instants saved for each edition.
- [ ] Accepted bands and band segments, with restrictions that may depend on mode, region, license, or category.
- [ ] Accepted modes and mode families, including mixed-mode entries and whether the same station may be credited again on another mode.
- [ ] Geographic or entity tables used by scoring, with an identified source and version: CQ/ITU zones, DXCC entities, ARRL/RAC sections, Maidenhead grids, continents, states, provinces, or contest-specific regions.

Examples show why these are separate settings: CQ WW defines a fixed operating window and HF bands, while Sweepstakes also limits logged operating time and requires minimum off periods. Submission deadlines are separate from the operating period and can change by edition. [CQ WW rules](https://www.cqww.com/rules/), [ARRL November Sweepstakes rules](https://contests.arrl.org/ContestRules/SS-Rules.pdf), [CQ WW 2026 rule changes](https://cqww.com/blog/2026-rule-changes/)

## Entry categories and overlays

- [ ] Operator configuration: single operator, multi-operator, school/group, club, headquarters station, or other contest-defined type.
- [ ] Transmitter configuration: one transmitter, multi-single, multi-two, multi-unlimited, one signal per band, or a contest-specific limit.
- [ ] Power classes with contest-defined limits (for example QRP, low power, and high power), measured per contact, transmitter, band, or whole entry as the rule requires.
- [ ] All-band or single-band entry, including whether all contacts must be uploaded but only the selected band scores.
- [ ] Mode-specific categories: CW-only, phone-only, digital-only, analog-only, or mixed.
- [ ] Assistance rules: unassisted, assisted/unlimited, spotting permitted or prohibited, and the allowed source of assistance.
- [ ] Station/site type: fixed, portable, mobile, rover, emergency operations center, distributed, or other event-specific class.
- [ ] Category overlays that are in addition to a base category, such as rookie, youth, classic operator, limited antennas, or tribander/single-element.
- [ ] Category compatibility rules and mutually exclusive choices. Make explicit whether an overlay creates a separate result listing or changes scoring.
- [ ] Checklog or non-scoring submission category.
- [ ] Entry-level declarations and evidence fields required to claim a category.
- [ ] Operating restrictions that are only partly verifiable from a log (for example transmitter count, power, antenna, station radius, and human initiation) and the adjudication workflow for them.

CQ WW and WPX combine operator type, power, band choice, assistance, overlays, and multi-transmitter limits in different ways. Field Day has site classes based on group/site and power arrangements. Treat these as composable dimensions and encode category compatibility explicitly. [CQ WW rules](https://www.cqww.com/rules/), [CQ WPX rules](https://cqwpx.com/rules/), [ARRL Field Day rules](https://www.arrl.org/field-day-rules)

## Exchange definition

- [ ] Define the exchange as an ordered list of named fields, each with a type, format, required/optional flag, and validation rule.
- [ ] Support fields exchanged per contact and entry-level fields repeated across contacts.
- [ ] Support common field types: signal report (RS/RST), serial number, callsign, category/precedence, section/region, CQ or ITU zone, grid locator, class, prefix, age/year, and contest-specific text.
- [ ] Define which values are sent, received, or derived from the entrant's contest entry.
- [ ] Define serial-number scope and starting value: whole log, band, transmitter, mode, or another rule-defined scope.
- [ ] Validate fixed lengths, allowed enumerations, geographic formats, and sequence behavior without discarding the submitted text.
- [ ] Support optional fields, conditional fields, and distinct exchange schemas by category, station type, band, or mode.
- [ ] Preserve the raw submitted exchange and its parsed/normalized interpretation separately.
- [ ] Provide an exchange preview/example for contest setup and clear row-level validation errors during log import.

The exchange can be a signal report plus CQ zone, a serial number, a long structured Sweepstakes exchange, a Field Day class and section, a VHF grid locator, or an IARU zone/HQ identifier. A generic untyped “exchange string” cannot express all the validation and scoring dependencies needed by these examples. [CQ WW rules](https://www.cqww.com/rules/), [ARRL Sweepstakes rules](https://contests.arrl.org/ContestRules/SS-Rules.pdf), [ARRL Field Day rules](https://www.arrl.org/field-day-rules), [ARRL VHF rules](https://contests.arrl.org/ContestRules/JanJunSep-VHF-Rules.pdf), [IARU HF rules](https://contests.arrl.org/ContestRules/IARU-HF-Rules.pdf)

## QSO eligibility, duplicate handling, and log validation

- [ ] Required QSO data: UTC timestamp, band or frequency, mode, worked callsign, sent exchange, and received exchange.
- [ ] Contest-period bounds, allowed band/mode combinations, and category-specific contact eligibility.
- [ ] Contact geography rules, including who may contact whom and whether special stations are eligible.
- [ ] QSO uniqueness key, configurable by contest: once per contest, per band, per mode, per band and mode, per rover grid, per transmitter, or another defined scope.
- [ ] Whether a repeat contact is ignored, invalidated, or treated as a duplicate with a penalty.
- [ ] Self-contact, same-site, cross-band, repeater, satellite, and remote-receiver restrictions where applicable.
- [ ] Multi-operator band-change, mode-change, transmitter-count, and clock-window constraints, when sufficient log data exists to check them.
- [ ] Off-time and maximum operating-time calculations, including whether an uploaded log may contain unscored contacts outside an entrant's claimed operating period.
- [ ] Callsign and exchange matching rules, including permitted normalization, portable designators, and contest-specific call parsing.
- [ ] Cross-check against submitted counterpart logs, if available, and the comparison window/tolerance for timestamps or copied exchanges.
- [ ] Keep the entrant's claimed score for comparison while deriving the adjudicated score from contacts and rules.

The duplication key is not universal: CQ WW and WPX give band-level repeat credit, Sweepstakes limits a station to one credit regardless of band, and ARRL VHF rules permit a rover to work the same call from more than one grid. Keep uniqueness policy in the selected ruleset. [CQ WW rules](https://www.cqww.com/rules/), [CQ WPX rules](https://cqwpx.com/rules/), [ARRL Sweepstakes rules](https://contests.arrl.org/ContestRules/SS-Rules.pdf), [ARRL VHF rules](https://contests.arrl.org/ContestRules/JanJunSep-VHF-Rules.pdf)

## Scoring and multipliers

- [ ] Integer QSO points by a configured context: fixed value, band, mode, distance, continent, entity, zone, station type, or a combination.
- [ ] Zero-point contacts that still qualify for multiplier credit.
- [ ] Multiplier kinds and sources: zones, countries/entities, prefixes, sections, grids, states/provinces, headquarters stations, officials, or other rule-defined values.
- [ ] Multiplier uniqueness scope: once per contest, per band, per mode, per band and mode, per grid/site, or another explicit scope.
- [ ] Multiplier eligibility conditions, including contacts that earn points, multipliers, both, or neither.
- [ ] Final score expression and operation order, such as QSO points multiplied by multiplier count, power multiplier followed by bonuses, or a custom integer-only expression.
- [ ] Integer bonus points with eligibility, proof requirements, caps, per-contact/per-entry basis, and whether they are added before or after a multiplier.
- [ ] Penalties for busted calls, not-in-log (NIL), incorrect exchanges, invalid band/mode, excessive unverifiable contacts, or rule breaches; allow each penalty to remove credit, deduct points, reclassify an entry, or disqualify it as specified.
- [ ] Tie-breakers and score precision (integer only), plus a complete explanation of each score component.
- [ ] Club/team aggregation rules, membership eligibility, and allocation rules for multi-operator entries.
- [ ] Separate claimed, provisional, and adjudicated scores; store immutable score runs tied to the ruleset version and source log revision.

Different scoring shapes appear in the sources: CQ WW combines QSO points with zone and country multipliers counted by band; WPX uses a prefix multiplier counted once regardless of band; Sweepstakes uses section multipliers; ARRL VHF weights QSO points by band and counts grid multipliers per band, with additional rover-specific multipliers; IARU combines zones and HQ stations; Field Day applies a power multiplier and then eligible bonuses. [CQ WW rules](https://www.cqww.com/rules/), [CQ WPX rules](https://cqwpx.com/rules/), [ARRL Sweepstakes rules](https://contests.arrl.org/ContestRules/SS-Rules.pdf), [ARRL VHF rules](https://contests.arrl.org/ContestRules/JanJunSep-VHF-Rules.pdf), [IARU HF rules](https://contests.arrl.org/ContestRules/IARU-HF-Rules.pdf), [ARRL Field Day rules](https://www.arrl.org/field-day-rules)

## Submission, imports, and publication

- [ ] Accepted submission methods and file formats; keep format parsing in adapters separate from rules validation and scoring.
- [ ] Cabrillo category headers and contest-specific QSO templates, including optional and repeated header fields.
- [ ] Import validation with line/record numbers, actionable errors, warnings, and a summary of accepted/rejected records.
- [ ] Preserve fields not understood by the current ruleset so imports can be reviewed or re-exported without silent data loss.
- [ ] Submission cutoff, late-log classification, authorized extensions, corrections/resubmission, withdrawal, and checklog policies.
- [ ] Public result/standings visibility, publication state, and how checklogs, late logs, reclassified entries, and disqualified entries appear.
- [ ] Reproducible result exports and a versioned downloadable log/result format where needed.

Cabrillo is a common interchange format, but its category header describes entry attributes and the contest sponsor determines the valid category; claimed line scores may be recomputed during log checking. Keep the common QSO model separate from each contest's Cabrillo template. [WWROF Cabrillo developer notes](https://wwrof.org/cabrillo/cabrillo-specification-notes/), [ARRL log submission](https://www.arrl.org/log-submission)

## Adjudication, audit, and awards

- [ ] Per-QSO decision states such as credited, duplicate, busted call, NIL, exchange error, out of period, out of band, or check required.
- [ ] Rule-specific consequence for each state; do not assume every error has the same penalty.
- [ ] Manual review with reason, reviewer, timestamp, supporting evidence, and a way to supersede a previous decision without erasing the audit trail.
- [ ] Entry status workflow: submitted, validated, under review, scored, published, late, checklog, reclassified, withdrawn, or disqualified.
- [ ] Entrant notification, appeal window, and finalization rules if the contest sponsor defines them.
- [ ] Awards and rankings by category, overlay, geography/division, band, mode, operator, club, and any contest-specific grouping.
- [ ] Award eligibility separate from score rank, including on-time entry, minimum participation, proof, and sponsor discretion.
- [ ] Explainable result output: score, point totals, each multiplier, bonus/penalty totals, credited QSOs, and disqualification/reclassification reason.

Official judging policies vary even where the event calculation is similar: CQ and ARRL materials distinguish duplicate contacts, exchange errors, busted calls/NILs, penalties, appeals, and category reclassification. Make these independent policy settings and retain a human-review path. [CQ WW rules](https://www.cqww.com/rules/), [CQ WPX rules](https://cqwpx.com/rules/), [IARU HF rules](https://contests.arrl.org/ContestRules/IARU-HF-Rules.pdf)

## Initial reusable rule types suggested by the survey

- [ ] Schedule and UTC submission cutoff.
- [ ] Category dimensions and compatibility constraints.
- [ ] Declarative exchange schema and field validators.
- [ ] QSO eligibility predicates and configurable duplicate scope.
- [ ] Integer QSO-point rules and integer-only score composition.
- [ ] Multiplier source, uniqueness scope, and eligibility.
- [ ] Bonus and penalty rules with thresholds, caps, ordering, and evidence.
- [ ] Operating-time, off-time, band-change, and transmitter constraints.
- [ ] Log import/export schema and category mapping.
- [ ] Cross-log checking, review decisions, and publication/award eligibility.
- [ ] Ruleset edition/source provenance and immutable score-run explanations.

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
