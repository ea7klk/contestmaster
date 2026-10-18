# Amateur-radio contest rules: body of knowledge

**Research snapshot:** 2026-10-18; **source policy:** sponsor-published contest rules and sponsor rule indexes only.

## Scope and evidence standard

This body of knowledge is a rules survey for reviewing Contestmaster's ruleset model, scoring engine, and composer. It does **not** claim coverage of any event calendar. The linked evidence is published by contest sponsors or their contest committees. Each description is paraphrased; the sponsor's current rules for the selected edition remain authoritative.

The companion [`sponsor-rule-samples.json`](sponsor-rule-samples.json) contains at least 200 individually identified contest samples. It distinguishes one-off contests from sessions/editions governed by a recurring sponsor ruleset and identifies shared rule pages so repeated sessions are not misrepresented as 200 unrelated rulebooks. Where a sponsor has not yet published the next edition, the newest reviewed sponsor edition is explicitly marked and must be checked again before configuration. A source page's existence does not establish that its rules are unchanged.

The inventory is a research aid, not a rules database or endorsement. It excludes secondary calendars and aggregators as evidence. It does not copy contest rules or multiplier tables. The project must not ingest or redistribute the ARRL DXCC list; contest-published scoring definitions may be represented as contest-specific rules where permitted.

## Contest rule sources, grouped by rule family

These groups are navigation aids, not claims that the groups are exhaustive. Each link goes to a sponsor's rule page or official rule document.

### Short sprints and activity sessions

- [NAQCC general sprint rules](https://naqcc.info/sprint_rules.html) — monthly CW sprint baseline; QRP limits, exchange variants, repeat rules, and point/multiplier structure.
- [CWops Tests (CWT)](https://cwops.org/cwops-tests/) and [CW Open rules](https://cwops.org/cwops-tests/cw-open/) — frequent short CW sessions versus a multi-session annual event; session-scoped serials, per-session score, repeated-call multipliers, and optional team aggregation.
- [RSGB 144 MHz FM Activity Contest](https://www.rsgbcc.org/cgi-bin/contest_rules.pl?contest=2mfmac&year=2026) and [432 MHz FM Activity Contest](https://www.rsgbcc.org/cgi-bin/contest_rules.pl?contest=70cmsfmac&year=2026) — very short FM windows, 6-character locators, serial reset by session, distance points, power sections, and best-session series scoring.
- [RSGB 144 MHz UK Activity Contest](https://www.rsgbcc.org/cgi-bin/contest_rules.pl?contest=2mukac&year=2026), [50 MHz UKAC](https://www.rsgbcc.org/cgi-bin/contest_rules.pl?contest=6mukac&year=2026), [70 MHz UKAC](https://www.rsgbcc.org/cgi-bin/contest_rules.pl?contest=4mukac&year=2026), [432 MHz UKAC](https://www.rsgbcc.org/cgi-bin/contest_rules.pl?contest=70cmukac&year=2026), [1.3 GHz UKAC](https://www.rsgbcc.org/cgi-bin/contest_rules.pl?contest=uhfukac&year=2026), and [SHF UKAC](https://www.rsgbcc.org/cgi-bin/contest_rules.pl?contest=shfukac&year=2026) — band-specific activity contests with locator exchanges, distance/square scoring, section constraints, session normalization, best-N individual results, and club totals.
- [RSGB 144 MHz FT8 AC, 2 hours](https://www.rsgbcc.org/cgi-bin/contest_rules.pl?contest=2mmgmac&year=2026), [144 MHz FT8 AC, 4 hours](https://www.rsgbcc.org/cgi-bin/contest_rules.pl?contest=2m4hmgmac&year=2026), [432 MHz FT8 AC, 2 hours](https://www.rsgbcc.org/cgi-bin/contest_rules.pl?contest=70cmsgmac&year=2026), and [432 MHz FT8 AC, 4 hours](https://www.rsgbcc.org/cgi-bin/contest_rules.pl?contest=70cms4mgmac&year=2026) — short ADIF-native FT8 competitions; no serial in the exchange, locator/distance scoring, per-session normalization and best-N aggregation.
- [RSGB 3.5 MHz Autumn Series](https://www.rsgbcc.org/hf/rules/2026/rautumn.shtml) — short evening sessions across modes with band windows, power/assistance sections, and individual and society series outcomes.

### Weekend and long-duration HF contests

- [CQ WW DX rules](https://www.cqww.com/rules/) and [CQ WW RTTY rules](https://www.cqwwrtty.com/) — worldwide multi-band formats with zone/entity multipliers, category dimensions, band/mode repeat policy, and an aggregate multiplier formula.
- [CQ WPX rules](https://cqwpx.com/rules/) — prefix-based multipliers, serial exchange, band-dependent points, single-operator operating limits, and distinct multi-operator provisions.
- [ARRL November Sweepstakes](https://www.arrl.org/arrl-sweepstakes) — ordered serial/precedence/callsign/check/section exchange, unique-contact treatment, and a maximum operating period with off-time.
- [ARRL 10-Meter Contest rules](https://contests.arrl.org/ContestRules/10M-Rules.pdf) — mixed/CW/phone categories, per-mode repeats, 36-of-48-hour operating limit, and geographically asymmetric exchange values.
- [ARRL International DX rules](https://contests.arrl.org/ContestRules/DX-Rules.pdf) — separate CW/phone editions, exchange and point values that depend on station location, and multiplier treatment.
- [IARU HF World Championship rules](https://www.iaru.org/on-the-air/iaru-contests/rules/) — official global sponsor rules for the worldwide HF event and headquarters-station exchanges.
- [DARC Worked All Germany rules](https://www.darc.de/der-club/referate/conteste/wag-contest/regeln/) — CW/SSB and mixed categories, DOK/entity multipliers, asymmetric points, transmitter-change constraints, club aggregation, and Cabrillo submission.
- [DARC Worked All Europe rules](https://www.darc.de/der-club/referate/conteste/wae-dx-contest/en/) — mode-specific editions and QTC transfer traffic in addition to ordinary QSOs; QTC is a separate data object, not an exchange string.
- [RSGB IOTA Contest rules](https://www.rsgbcc.org/hf/rules/2026/riota.shtml) — island/world station roles, island references, band/mode repeats, assistance categories, and operating-location requirements.
- [RSGB Commonwealth Contest rules](https://www.rsgbcc.org/hf/rules/2026/rcwc.shtml) — geographically bounded station eligibility and explicit call-area identification.
- [UBA DX Contest rules](https://www.uba.be/en/hf/contest-rules/uba-dx-contest) — asymmetric participant roles, band/mode multipliers, section exchange, mode editions, operating-time classes, and log penalties.
- [NCJ North American QSO Party rules](https://ncjweb.com/NAQP-Rules.pdf) — 12-hour format with off-time, name/state or province exchange, mode-specific editions, assistance classes, teams, and multi-two band-change limits.

### Digital, RTTY, and mode-specific contests

- [DARC FT4 Contest rules](https://www.darc.de/der-club/referate/conteste/ft4-contest/ft4-rules/) — short digital contest with a compact locator exchange and prefix multipliers.
- [UBA PSK63 Prefix Contest rules](https://www.uba.be/en/hf/contest-rules/uba-psk63-prefix-contest) — single-mode eligibility, prefix multiplier behavior, and power/operator categories.
- [RSGB MGM rules](https://www.rsgbcc.org/vhf/rules/2026/mgmrules.shtml) — machine-generated mode definitions, locator exchange, and rules distinct from CW/phone VHF events.
- [ARRL International Digital Contest rules](https://www.arrl.org/arrl-digital-contest) — digital-only categories, exchange, scoring, and log format requirements.
- [ARRL RTTY Roundup rules](https://www.arrl.org/rtty-roundup) — RTTY exchange and categories; check the event edition for any current digital-mode expansion.
- [DARC RTTY short contest rules entry point](https://www.darc.de/der-club/referate/conteste/rtty-kurzcontest/) — compact RTTY session and series scoring; verify the current edition page before modeling.

### VHF, UHF, SHF, EME, and distance contests

- [ARRL January VHF rules](https://contests.arrl.org/ContestRules/JanJunSep-VHF-Rules.pdf), [June VHF rules](https://contests.arrl.org/ContestRules/JanJunSep-VHF-Rules.pdf), and [September VHF rules](https://contests.arrl.org/ContestRules/JanJunSep-VHF-Rules.pdf) — common rules document with separate contest occurrences, grid-based objectives, band eligibility, and club competition.
- [ARRL International EME rules](https://contests.arrl.org/ContestRules/EME-Rules.pdf) — multiple 48-hour weekends split by frequency range, band-limited periods, grid exchange, fixed QSO points, and per-band grid multipliers.
- [ARRL 10 GHz & Up rules](https://www.arrl.org/10-ghz-up) — two operating weekends, limited operating hours, location-based microwave contacts, and a later log deadline.
- [CQ WW VHF rules](https://www.cqww-vhf.com/rules/) — grid exchange, per-band scoring and multipliers, and rover location changes.
- [RSGB 432 MHz Trophy](https://www.rsgbcc.org/cgi-bin/contest_rules.pl?contest=70cmstrophy&year=2026), [2.3 GHz Trophy](https://www.rsgbcc.org/cgi-bin/contest_rules.pl?contest=13cmstrophy&year=2026), [10 GHz Trophy](https://www.rsgbcc.org/cgi-bin/contest_rules.pl?contest=3cmstrophy&year=2026), and [October 432 MHz–245 GHz Contest](https://www.rsgbcc.org/cgi-bin/contest_rules.pl?contest=octuhf&year=2026) — different band ceilings, operating windows, band-reset serials, split operating periods, and distance scoring.
- [RSGB general VHF/UHF/SHF rules](https://www.rsgbcc.org/vhf/rules/26rules/General.shtml) — shared common rules for location, UTC logging, allowed formats, deadlines, operating categories, and penalties; specific contest rules override these where stated.
- [IARU Region 1 VHF-up rules](https://www.iaru-r1.org/wp-content/uploads/2024/02/Rules-IARU-R1-VHF-up-Contests.pdf) — sponsor rule example of locator and distance scoring. This is not a requirement for IARU organizational-region master data in Contestmaster.

### State, province, and regional QSO parties

These sponsor rules are especially useful for asymmetric eligibility, geographic exchange values, county-line/mobile operation, multipliers, duplicate scope, and power/mode sections:

- [Arizona QSO Party rules](https://www.azqp.org/rules)
- [Arkansas QSO Party rules](https://arkqp.com/)
- [California QSO Party rules](https://www.cqp.org/Rules.html)
- [Colorado QSO Party rules](https://coloradoqsoparty.org/getting-started/rules/)
- [Florida QSO Party rules](https://floridaqsoparty.org/rules/)
- [Georgia QSO Party rules](https://gaqsoparty.com/)
- [Idaho QSO Party rules](https://idahoqsoparty.org/rules.htm)
- [Kansas QSO Party rules](https://www.ksqsoparty.org/)
- [Kentucky QSO Party rules](https://kyqsoparty.org/rules/)
- [Michigan QSO Party rules](https://miqp.org/index.php/rules/)
- [Missouri QSO Party rules](https://www.w0ma.org/mo_qso_party/results/thisyear/moqp-2026-rules-final.pdf)
- [North Carolina QSO Party rules](https://ncqsoparty.org/rules/)
- [Ohio QSO Party rules](https://www.ohqp.org/index.php/rules/)
- [South Carolina QSO Party rules](https://scqso.com/)
- [Tennessee QSO Party rules](https://tnqp.org/rules/)
- [Texas QSO Party rules](https://txqp.net/?page_id=23)
- [Virginia QSO Party rules](https://www.qsl.net/sterling/VA_QSO_Party/2026_VQP/2026_VAQP_Rules.htm)

### QRP, club, field, and participation-focused events

- [ARRL Field Day rules](https://www.arrl.org/field-day-rules/) — station/site classes, mode-dependent points, power multiplier, evidence-bearing bonus points, and separate club aggregation.
- [ARRL Rookie Roundup rules](https://www.arrl.org/rookie-roundup/) — license-age qualification, contacts between different entrant classes, special exchange elements, and team entries.
- [ARRL School Club Roundup rules](https://www.arrl.org/school-club-roundup) — school-based category and exchange conditions; check current rules for class and scoring details.
- [ARRL Kids Day rules](https://www.arrl.org/kids-day) — participation-focused special event with simplified exchange and reporting expectations.
- [NAQCC sprint rules](https://naqcc.info/sprint_rules.html) — QRP threshold and CW-only participation pattern.
- [RSGB VHF National Field Day rules](https://www.rsgbcc.org/vhf/rules/2026/VHFNFD.shtml) — site/equipment classes, club entry, and field operation requirements.
- [RSGB 144 MHz Backpackers rules](https://www.rsgbcc.org/cgi-bin/contest_rules.pl?contest=144backpack5&year=2026) — portable station constraints and a dedicated operating class.
- [RSGB AFS 80m/40m rules](https://www.rsgbcc.org/hf/rules/2026/rafs.shtml) — society team contribution across mode-specific contests and aggregate league scoring.

## Cross-cutting patterns to check against Contestmaster

The observations below are patterns present in sponsor rules, not universal defaults. Configure them per edition; do not infer behavior from a contest name.

| Area | Recurrent variations observed | Model / engine implication |
|---|---|---|
| Schedule | Sprint windows; 4–8 hour sessions; overnight events; 24/48 hour weekends; multiple separated operating blocks; recurring series with best-N sessions | Store each edition's UTC start, end, and independent submission cutoff. Explicit sessions and series aggregation need first-class semantics; do not approximate gaps as one continuous interval. |
| Eligibility | Any station may participate; only one side of a QSO can score; host-area versus outside-area rules; island, club, school, rookie, QRP, or portable qualification | Entry-side eligibility must be distinct from QSO validity. Identify whether each fact is organizer-verified, declared, inferred from a log, or adjudicated. |
| Categories | Operator/transmitter count, power, assistance, mode, band, station location/setup, rover, youth/rookie, club and overlays | Category labels do not implement category behavior. Separate eligibility, scoring, parallel standings, and award overlays. |
| Exchanges | RST/RS(T), serial, name, state/province/county/section, DOK, grid, island reference, age/check, and compound exchanges | Preserve sent/received values and field order. Serial scope may reset by entry, band, mode, date, or session. Some exchanges are conditional on station role. |
| Duplicates | Per contest, per band, per mode, band+mode, county, grid, rover position, or a limited number of repeats | Keep duplicate key, QSO point effect, and multiplier eligibility independently configurable. A duplicate may be uncredited for points yet remain relevant to another rule only when the sponsor says so. |
| Scoring | Fixed integer contact points; geography tiers; zone/entity/section/prefix/grid multipliers; distance; bonus points; percentage penalties; normalized series scores | Define calculation order and integer rounding. Distance and normalized series formulas need explicit integer conversion and reproducible tie handling. |
| Operations | Off-time, max operating hours, band-change limits, transmitter constraints, station-radius rules, self-spotting/assistance limits | Rules can depend on timelines and evidence not always present in Cabrillo/ADIF. Unsupported facts must produce review states rather than guessed results. |
| Adjudication | NIL/busted calls, exchange errors, penalties, checklogs, disqualification, late logs, or committee discretion | Store per-QSO and per-entry decisions with a reason and rule reference; keep publication policy independent of raw scoring. |
| Log transport | Cabrillo, ADIF, EDI/REG1TEST, sponsor web forms, online transcriptions, or mode-specific robot uploads | Format and required-field mapping are edition-specific. Parse at the boundary, retain unknown source fields, and reject invalid uploads atomically with line-level feedback. |
| Series/teams | Best N sessions, normalized scores, club leagues, teams, or cross-event aggregations | A score run for one contest edition is not enough for a season league. Model aggregate result snapshots and membership/eligibility explicitly. |

## Current Contestmaster capability comparison

The schema is in `backend/app/rulesets/schema.py`; execution is in `backend/app/rulesets/engine.py`; composition is in `frontend/src/views/RulesetComposerView.vue` and the related editors. Status describes the current repository implementation, not the whole range of real rules.

| Pattern | Current fit | Gap / review caution |
|---|---|---|
| UTC event dates and independent log deadline | Supported in contest configuration | Recurrence creates editions; confirm exact sponsor timezone before materializing UTC instants. |
| Category dimensions and choices | Supported for classification | Overlay rankings, team results, and evidence-based class derivation are not implied by a category value. |
| Typed exchange fields and serial scopes | Supported for declared fields | Conditional asymmetric exchanges and compound/multi-contact exchanges require end-to-end validation. |
| Cabrillo and ADIF mappings | Supported for declared mappings | EDI/REG1TEST and arbitrary sponsor forms need adapters; WWROF remains authority for Cabrillo QSO columns. |
| Fixed, band, mode, continent, entity, zone, and received-exchange points | Supported for engine facts | Distance-based scoring and formulas needing undeclared facts are gaps; no hidden fallback. |
| Multipliers from supported engine facts | Supported for current sources/scopes | Prefix/suffix/specific-call multiplier capability is tracked separately; do not equate prefix with entity. |
| Duplicate QSO point/multiplier behavior | Separate settings supported | Verify exact scope and ordering against each sponsor rule. |
| Penalty/adjudication workflows | Partial | Human decisions, evidence, team awards, percentage deductions, and score normalization need explicit capability review. |
| Time windows, off-time, band changes, transmitter limits | Partial | Longitudinal constraints need complete cross-log/session facts and clear boundary semantics. |
| Series, teams, club leagues, best-N ranking | Gap/partial | Requires result aggregation across contest editions and immutable reproducible aggregate snapshots. |
| Distance and locator-square bonuses | Gap | Requires a specified locator precision, geodesic calculation, distance units, integer rounding, and missing-data behavior. |
| QTC traffic | Gap | Requires first-class directed transfer records, ordering, sequence, duplicate checks, cross-log validation, and scoring. |

Current score facts are finite and typed. A JSON field name alone does not make a rule executable. Scoring values and all score intermediates remain integers; if a sponsor uses division, the exact integer rounding rule must be specified and tested.

## Source and edition handling

- Keep the sponsor, contest edition, direct rules URL, source edition/revision, and review timestamp with each ruleset review.
- Re-open the sponsor's rule source before every configured contest edition. Mark unpublished future rules as pending; do not assume a previous edition carries forward unchanged.
- Apply common/general rules only where the contest's specific rule set adopts them. Record the precedence between sponsor-wide and event-specific rules.
- Link to rules for examples, but paraphrase them. Do not copy complete sponsor rule text, categories tables, or proprietary multiplier files into the application.
- No source list in this document is a claim of calendar coverage, complete worldwide event coverage, or continuing sponsor publication.

## Review checklist for each contest

- [ ] Confirm the sponsor and the exact edition-specific rules URL.
- [ ] Separate event start/end, permitted operating intervals, and submission cutoff.
- [ ] Classify every rule fact as machine-verifiable, declared, externally resolved, or human-adjudicated.
- [ ] Define categories, category compatibility, overlays, and standings behavior.
- [ ] Define exchange order, direction, value constraints, serial scope, and required file fields.
- [ ] Define QSO eligibility and duplicate behavior separately for points and multipliers.
- [ ] Define point and multiplier facts, scopes, caps, calculation order, rounding, and tie-breaks.
- [ ] Define operating limits, evidence requirements, penalties, late/checklog policy, and publication eligibility.
- [ ] Identify engine/schema gaps and do not work around them with contest-name branches.
- [ ] Add worked examples and boundary tests before calling the configuration verified.

## Machine-readable inventory

See [`sponsor-rule-samples.json`](sponsor-rule-samples.json) for the 200+ sample records, source URLs, event family tags, and scope/edition notes. Records with a shared recurring-series rule source are intentionally linked to the same sponsor page and carry a distinct session or event identifier.
