# Strategy for supporting the unconverted N1MM profiles

## Purpose

This document describes the application work that could be needed to represent and score the profiles in [`unconverted-profiles.md`](unconverted-profiles.md). It is a plan only: it does not change the application, add rule types, or claim parity for any profile.

The source inventory covers 263 factory dispatch keys routed to 142 handlers, plus 50 known data-backed QSO Party selectors routed through the shared `QSOPARTY` key. Many handler methods are present for logger entry, display, or export rather than scoring. A method override alone does not prove an application gap. The blocked records currently identify source method families and broad gaps; before proposing each implementation, a reviewer still needs to trace the active-key branch and state the exact input facts and expected outcome.

N1MM's binary is evidence of one logger build's behavior. For a real contest edition, the sponsor's published rules remain authoritative. The objective is reusable, validated declarative rules in Contestmaster; it is not an N1MM runtime, user interface, or logger-workflow clone.

## Current capabilities to retain

The proposed work should extend existing capabilities rather than treat them as absent:

| Area | Current Contestmaster capability | Boundary to verify per profile |
| --- | --- | --- |
| Points | Fixed points, lookups by selected QSO facts, conditions, and integer Maidenhead distance points | Profile-specific lookup domains, entrant-relative cases, distance origins/thresholds, special same-cell rules, and missing-input behavior |
| Formula | Integer arithmetic over total points, bonuses, penalties, power multiplier, combined multipliers, and each configured multiplier's count | Any formula that needs a fact or aggregate not currently exposed; retain sponsor-defined integer rounding |
| Multipliers | Multiple named rules, supported source facts, and configured uniqueness scopes | Composite keys, profile tables, per-period or conditional uniqueness, and any source not present in the scoring context |
| Duplicates | Configurable identity fields including callsign, band, mode, grid, transmitter, and exchange fields; duplicates may optionally earn multipliers | Profile-specific mobile/rover identities, uncommon period boundaries, and any N1MM SQL behavior that does not reduce to these fields |
| Conditions | Validated declarative conditions with explicit missing-fact handling | New fact derivation, complex reference lookups, and conditions whose evidence must trigger human review |
| Bonuses and penalties | Integer fixed, per-QSO, per-entry, and distinct-value bonuses, plus configured penalty outcomes | Contest-specific counted entities, bonus caps/stacking rules, occurrence windows, and data sources |
| Sessions and operating constraints | Fixed UTC session resets, operating/off-time and band-change constraints, and review outcomes for unverifiable evidence | Irregular session calendars, series aggregation, or station-operation facts the uploaded log cannot establish |
| Formats | Explicit Cabrillo and ADIF mappings, category mapping, and preservation of unknown input | Contest-specific exchange variants, required attachments, fields absent from accepted formats, and any additional parser that a real profile needs |
| Geography | Contest-start-pinned CTY facts for entity, prefix, zones, and continent; entrant-relative same-entity/same-continent facts | Other classifications or sponsor-specific geographic tables. Do not assume they can be derived from CTY. |

The current implementation and sponsor-verified examples are described in the [parity plan](../ruleset-parity/n1mm-functional-parity-plan.md), [behavior matrix](../ruleset-parity/behavior-matrix.md), [ruleset schema](../../backend/app/rulesets/schema.py), and [scoring engine](../../backend/app/rulesets/engine.py).

## Recommended architecture

Keep the existing separation between input adapters, typed rules, and deterministic scoring. Add capabilities only where a traced profile demonstrates a missing reusable behavior.

1. **Build a source-to-behavior trace.** For every dispatch key and QSO Party selector, record the active handler branch, source method/line, scoring or validation outcome, required facts, and whether that behavior is scoring-critical, import-critical, adjudication-only, or logger-only. Link the applicable sponsor edition when one exists. Keep aliases and token-specific branches separate.
2. **Define a typed fact catalog.** Each score fact should declare its type, provenance, availability stage (entry, parsed QSO, normalized QSO, master-data resolution, or adjudication), valid domain where finite, supported formats, and missing/ambiguous-data policy. Expose the same catalog to backend validation and the graphical composer. Do not let arbitrary strings silently become executable fact paths.
3. **Represent reference data as data.** For contest-specific sections, counties, grids, islands, bonus stations, or similar lists, prefer explicit, versioned, provenance-bearing tables referenced by a ruleset. Validate table keys and data licensing. Keep operational CTY data distinct from contest-specific lists. Never copy N1MM executable code or private/runtime tables into Contestmaster as an assumed license grant.
4. **Use bounded rule expressions.** Extend typed rules or a constrained expression tree for verified recurring patterns. Expressions must be size- and depth-bounded, use registered facts and integer operations, define rounding and missing-data behavior, and remain explainable in score output. Do not add Python evaluation, arbitrary SQL, uploaded scripts, or callbacks.
5. **Model unresolved evidence explicitly.** When a Cabrillo/ADIF log cannot establish a fact (for example, transmitter count or actual operating time), the configured rule should produce a review state or a documented conservative outcome. It must not infer compliance from missing information or silently give a claimed score.
6. **Treat format support as an adapter contract.** Preserve original source values; map each required scoring input to an accepted Cabrillo/ADIF field; and reject a profile if its exchange cannot be recovered. Cabrillo QSO layout remains governed by the [WWROF QSO specification](https://wwrof.org/cabrillo/cabrillo-qso-data/). N1MM's internal output or UI behavior is not a format specification.
7. **Version rule and data inputs.** A score run records the exact ruleset and any table/master-data versions used. A schema upgrade must keep existing schema-v2 drafts readable, provide a deliberate import/export path for newer schema versions, and avoid changing the meaning of saved versions.

## Capability workstreams

### A. Finish the evidence audit before changing the engine

The first implementation step should refine each blocked record into an evidence-backed decision:

- `representable`: existing rules and facts suffice; convert and test it.
- `needs_new_primitive`: cite the exact behavior and smallest reusable typed capability that covers it.
- `needs_contest_data`: identify the list/table, source, license/terms, effective version, and missing-value policy.
- `needs_adapter`: identify the required source field and target format mapping.
- `human_review`: describe what the log cannot prove and the review outcome.
- `logger_only`: document the behavior but exclude it from server scoring parity.
- `uncertain_or_obsolete`: keep blocked until a sponsor or product source establishes current relevance.

Do not label a profile permanently unsupported based only on method names or the presence of SQL in a handler. Likewise, do not mark it convertible because its JSON passes schema validation.

### B. Add only the scoring primitives the audit proves necessary

Likely areas to evaluate, not pre-approved implementation requirements:

- **Distance variants:** decide whether any profile needs a distance origin, locator precision, rounding rule, threshold bands, cap, or same-cell behavior beyond the current integer grid-distance rule. Encode each as explicit parameters and hand-calculated boundary tests.
- **Composite multipliers:** check whether profiles require a single multiplier identity composed from several facts, count-by-session behavior, or conditional counting beyond current per-rule source/scope support. Keep per-multiplier totals available to formulas.
- **Reference-table lookups:** QSO Party selectors are the clearest data-heavy area. They may require separate accepted-value tables, entrant-area rules, mobile/rover exchange identity, bonus station/county counts, and profile-specific score tables. Model the table schema and licensing first; do not treat one generic QSO Party formula as sufficient.
- **Entrant and station predicates:** add a derived fact only when it is necessary and reproducible from declared entry data, submitted exchanges, or pinned master data. Make conflicting or absent station-location declarations explicit.
- **Irregular scoring sessions:** compare actual per-profile reset boundaries with current fixed UTC intervals. Keep contest recurrence and dates in contest configuration; put only scoring-relevant within-event boundaries in the ruleset or explicit contest session configuration, according to whether they are reusable or edition-specific.
- **Operating proof and review:** decide which operating-time, transmitter, band-change, rover, or multi-operator constraints can be checked from logs and which must remain human review. Never label unobservable facts as automatically verified.
- **Exchange and log variants:** add parser or mapping support only for fields needed by a traced rule and present in the sponsor-accepted format. If the input format omits a required value, block scoring or require review rather than guessing.

### C. Keep API, composer, and scorer aligned

For any approved new capability, deliver the same typed semantics through:

- backend Pydantic schema, compatibility validation, and deterministic engine behavior;
- generated rule catalog/fact metadata and useful field-level API errors;
- Vue composer controls with plain-language help, valid-value selection, contradiction checks, and a visible “requires review” explanation where relevant;
- import/export JSON handling and schema-version compatibility;
- score explanations that show the source fact, matched table/condition, awarded integer value, multiplier identity, penalty, or review reason.

Avoid adding N1MM-specific fields or token switches to the core engine. Profile keys belong in source provenance and conversion manifests, not in scattered scoring conditionals.

## Suggested delivery sequence

| Stage | Outcome | Exit check |
| --- | --- | --- |
| 0. Evidence and scope | Complete the per-key semantic trace; classify logger-only, outdated, data-backed, and scoring behaviors | Every factory key and selector has a reviewed status and a specific reason; shared handlers are split where branches differ |
| 1. Capability specification | Define fact registry, table provenance/versioning, missing-data semantics, and only the proven schema extensions | Each new primitive has a sponsor-backed example, JSON shape, compatibility plan, and boundary cases before code work starts |
| 2. Domain engine | Implement approved point, multiplier, lookup, duplicate, session, eligibility, or review behavior as isolated services | Pure unit tests prove integer, deterministic outcomes including missing/ambiguous facts and boundaries |
| 3. Import and API | Make required facts available from Cabrillo/ADIF or explicit contest data; add mappings and validation | End-to-end fixtures show accepted inputs preserve all scoring facts and reject unavailable ones with actionable errors |
| 4. Composer and explanations | Expose supported primitives with safe controls and describe score/review outcomes | UI can author, validate, export, re-import, and explain every new rule without free-form executable logic |
| 5. Profile conversion batches | Convert suitable standard profiles, then data-heavy national/QSO Party profiles, then VHF/specialized profiles, and finally aliases/legacy entries | Every profile is either a validated importable ruleset with trace/tests or a structured blocker with an exact residual gap |
| 6. Conformance and release | Run full profile manifest validation and regression suites | No key is missing or duplicated; no blocked profile is importable; every enabled profile has documented source, tests, and a score explanation |

Recommended conversion order is based on likely reuse, not a claim that any profile is already complete: ordinary fixed/lookup HF profiles first; DX and sprint variants next; national/regional profiles and QSO Parties after table provenance is settled; VHF/distance and specialized operation profiles after their facts and review needs are traced; then aliases, historical, and uncertain entries. Reorder once stage 0 reveals the actual dependency graph.

## Conversion acceptance for every profile

A profile should be marked importable only when all of the following are true:

1. Its handler branch and profile selector are traced to exact source locations, and the extraction records the N1MM build/checksum.
2. Its category dimensions, exchange schema, eligibility, duplicate key/effect, each multiplier source and uniqueness scope, point calculation, final integer formula, penalties/bonuses, and scoring windows are captured or explicitly declared irrelevant.
3. Every fact is obtainable from an accepted log format, an explicit entry declaration, pinned master data, a versioned ruleset table, or a documented human-review outcome.
4. Each contest-specific data table has source, version, permission/terms, and a defined response to missing or unknown values.
5. The ruleset passes schema and semantic validation; the composer can edit and round-trip it without losing meaning.
6. Hand-calculated fixtures verify normal, boundary, duplicate, missing-input, and relevant invalid cases. Where the sponsor edition can differ from the N1MM binary, the conversion states whether it represents N1MM build behavior or sponsor-current rules; it must not conflate them.
7. Scoring remains deterministic and integer-valued, and the result explanation exposes enough detail to audit each decision.

## Explicit non-goals and safeguards

- Do not execute or embed N1MM code, SQL, dynamic libraries, or custom callbacks.
- Do not reproduce N1MM's keyboard workflows, contest windows, call-history completion, spotting, radio control, or presentation-only calculations unless a separate product request establishes a Contestmaster need.
- Do not assume a profile's historical binary behavior is an active contest edition or substitute it for sponsor rules.
- Do not copy external lookup tables or data into the hosted service until source terms and intended use are reviewed. Public availability alone is not permission to republish.
- Do not silently turn unverifiable or unsupported behavior into a credited QSO, multiplier, or published score.

## Inputs and traceability

- [Unconverted profile list and structured records](unconverted-profiles.md)
- [Generated blocked-profile records](blocked/)
- [Existing N1MM parity plan](../ruleset-parity/n1mm-functional-parity-plan.md)
- [Sponsor-verified behavior matrix](../ruleset-parity/behavior-matrix.md)
- [Ruleset schema and engine](../../backend/app/rulesets/schema.py) and [engine](../../backend/app/rulesets/engine.py)
- Tracking: parent issue [#398](https://github.com/ea7klk/contestmaster/issues/398), strategy child [#406](https://github.com/ea7klk/contestmaster/issues/406), and profile-conversion children [#399–#405](https://github.com/ea7klk/contestmaster/issues/399).
