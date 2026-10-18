# Ruleset composer guidance

The Vue composer exposes the same typed ruleset definition that the API validates. A contest manager should compare every draft with the sponsor's current rules before saving or activating it. The backend remains authoritative; browser controls only help build valid configuration.

## Ruleset creation workflow

The composer uses five task-based steps. The step navigation preserves one draft while moving between sections, and the review step links back to the section that needs attention.

1. **Basics and source** — name the reusable ruleset, choose its version, and record the sponsor URL and edition. This records which published rules were translated into the draft.
2. **Categories and exchange** — define entrant classification dimensions, their allowed choices, and the values participants exchange. Required and optional dimensions, declaration requirements, and unusual sponsor-specific terms remain configurable.
3. **Logs and contact eligibility** — set accepted file formats and mappings, late-log policy, eligible bands and modes, duplicate handling, and any conditions that govern whether contacts count.
4. **Scoring** — define integer QSO points, multipliers, bonuses, penalties, and the score formula. Include only the behavior required by the sponsor's rules.
5. **Limits and review** — configure operating constraints and review workflows when needed, inspect summaries of the preceding steps, validate against the API, and save only after validation succeeds.

Each rule appears as a short expandable card. Open a card to edit it. Stable rule identifiers, nested conditions, detailed mappings, and other less common settings are kept inside labeled **Technical details** or **Advanced conditions** disclosures. Collapsing a card or changing steps does not discard its values. JSON draft import/export remains available from the review step, and imported settings are retained even when they are not visible in the current step.

The review page summarizes each step and provides an **Edit** link back to it. Server validation errors include a link to the relevant section and open the associated rule card when possible. The API remains authoritative. A generated rules explanation and worked integer-score example are available for comparison with the sponsor's rules. Saving is offered only after successful server validation, and creates a new immutable version. Editing a saved version starts a new version without changing contests already assigned to the earlier version.

Contest dates, recurrence, and the UTC submission cutoff are intentionally not ruleset fields; configure them on the contest. The ruleset's submission setting describes how logs after that contest cutoff are classified.

The ruleset can be reused for contest editions with different event dates. Start/end times, recurrence, and the UTC submission cutoff belong to each contest. The ruleset's submission setting only describes how the application classifies logs received after that cutoff. Stable keys identify rules, categories, choices, and exchange fields in data and references; labels are intended for display and may be revised when making a new version.

## Conditions

A condition tests an existing fact, such as `qso.band`, `qso.entity`, `entry.categories.operator`, or `station.callsign`. Choose a fact path, comparison, and matching value. “Is one of” and “Is not one of” compare against a comma-separated list; “Is present” checks whether the fact has a value. “All conditions” requires every child condition to match, “Any condition” accepts one or more matches, and “Not a condition” inverts its child. An eligibility condition decides whether a contact can count at all; a rule-level condition decides whether that rule applies. They are separate controls. Conditions only use supported facts and operators, which are checked when validating the draft. If the sponsor defines behavior that the available condition controls cannot express, record it for review rather than approximating it.

## Import contests and edit saved rulesets

From **Contest manager**, choose **Import contest** and select a JSON package containing a `contest` object and, optionally, a `ruleset` object. The contest object uses UTC start, end, and submission-cutoff timestamps plus optional periodicity; an included ruleset uses schema version 2 described in [ruleset drafts](../ruleset-drafts/README.md). A package without a ruleset creates a manager-owned draft with no ruleset assigned. A package with a ruleset creates a manager-owned draft and saves and assigns its immutable ruleset version. Both paths are transactional: malformed input, invalid contest data, unavailable operating-catalog keys, or conflicting records leave no partial import.

Contest cards offer **Export contest** actions for a contest-only package and, when a ruleset is assigned, a package with that ruleset. Both exports use the same JSON shape accepted by **Import contest**. Contest data includes its name, slug, description, UTC event and cutoff timestamps, periodicity, and automatic-recalculation setting. The optional `ruleset` value contains the selected immutable ruleset configuration; contest-only export intentionally omits it.

For example, the package shape is:

```json
{
  "contest": {
    "name": "Example Sprint",
    "slug": "example-sprint",
    "description": null,
    "starts_at": "2026-05-01T00:00:00Z",
    "ends_at": "2026-05-01T06:00:00Z",
    "periodicity": null,
    "log_submission_cutoff_at": "2026-05-08T00:00:00Z",
    "auto_recalculate_on_upload": false
  },
  "ruleset": {
    "schema_version": 2,
    "ruleset_key": "example-sprint",
    "version": "2026",
    "rules": []
  }
}
```

The example's empty `rules` array is a shape illustration only; a real ruleset must include and validate all required rule types. Contest and ruleset administration each have a paged listing page. The contest list is at `/manage/contests`; create and edit contests at `/manage/contests/new` and `/manage/contests/{contest_id}/edit`. The ruleset list is at `/manage/rulesets`; create a ruleset at `/manage/rulesets/new`, or start a revised immutable version from a saved version at `/manage/rulesets/{version_id}/edit`. Both listings support server-side filtering and pagination. Existing ruleset versions remain immutable, and editing does not change a contest's current assignment. Select the newly saved version from the contest manager when ready.

## Schedule and submissions

The contest manager owns UTC start and end instants and optional periodicity. Configure one-time or recurring schedule details in the contest form; schedule settings are not part of a reusable ruleset. Enter actual event instants in UTC. Recurring contests are a series of separate contest editions, each with its own logs, results, and lifecycle. The first contest is the series anchor. The composer previews the next five UTC occurrences. A local start-time control adds no information to a UTC event instant. Daylight-saving “fold” means the repeated local wall-clock hour when clocks move backward; UTC scheduling has no fold.

Supported recurrence selectors are:

- **Annual date:** same month and day every year.
- **Nth weekday:** occurrence 1–5 or last (`-1`) for any selected weekday within any selected month. Each selected month and weekday combination creates an occurrence.
- **First, last, or Nth full weekend:** a full Saturday/Sunday pair entirely within the chosen month; the schedule starts Saturday at its configured UTC time. Nth weekend supports occurrences 1–5 and can target multiple selected months.

The API's `POST /api/v1/contests/schedule-preview` returns five upcoming occurrences, preserving the configured UTC time and event duration. An annual date that does not exist in a year is omitted. If a selected month lacks the selected fifth weekday or fifth full weekend, that month/weekday combination is skipped while other valid selections continue. Older imports may continue to provide a single month or weekday as a number; multiple selections are stored as arrays.

For recurring contests, **automatic edition creation** is optional. Set a rolling window from 1 to 730 days; the API's single-process internal timer checks at startup and hourly, then creates missing editions as drafts within that window. Leave it disabled to manage editions manually. The manager can add an exception to skip or move a scheduled date. A skipped edition that already has logs cannot be removed; keep it as an edition instead. Deleting a series requires typing its name and removes all editions and their dependent data.

Set a recurring series' log cutoff as a whole number of hours or days after its end. If the event duration or series offset changes, derived edition cutoffs move with them. A manager may set an absolute UTC cutoff override for a particular edition; later series changes leave that override unchanged.

Contest configuration owns the separate UTC log submission cutoff. The ruleset's log-submission policy only determines whether uploads beyond that cutoff are rejected, accepted as late, or classified as checklog. Manager extensions are possible only when explicitly enabled by the ruleset.

## Categories and exchanges

A category dimension is one entry-classification axis, such as operator, power, band, mode, assistance, transmitter count, station class, region, or overlay. Operator describes the operator arrangement; band and mode describe operating segments; assistance describes permitted use of tools such as spotting; transmitter and station class describe station configuration; region groups entries geographically; an overlay adds a sponsor-defined class. For dimensions with built-in choices, select accepted values with checkboxes labeled using their display names; a newly selected dimension starts with no values accepted until the manager checks them. The stable choice keys are stored in the existing `dimensions[].choices` structure. Use the collapsed choice-details panel to add contest-specific descriptions, declarations, or extra custom values. Region, contest category, and custom dimensions have no universal choice list; define their values from the sponsor's rules. A required dimension must have a selected value; an optional dimension may be left blank. A choice can be marked as requiring a participant declaration. Mutually exclusive groups identify dimensions that may not be selected together.

Power choices need particular care. Contestmaster's generated overview assumes QRP up to 5 W, Low Power up to 100 W, and High Power up to the applicable legal limit. These are defaults for plain-language descriptions; contest-specific published rules take precedence and define the measurement point and any different thresholds. Record those contest-specific requirements in the dimension or choice explanation fields. Apply the same practice to other dimensions: record the contest's exact operator, assistance, station, region, and mode definitions when they affect eligibility or classification. The sponsor's published rules remain authoritative.

Common keys and labels are selected from the controls; choose the custom option for sponsor-specific values. Keys are stable references used by imported categories, conditions, and format mappings. For custom values, changing a display label never changes its key; built-in labels follow their preset. Optional plain-text descriptions are stored in the ruleset JSON for each dimension and choice. The public “Contest rules at a glance” summary includes these descriptions when present, supplies general explanations for known dimensions when they are absent, and tells participants to consult the official rules for exact qualifications and limits. This summary is generated and may be imprecise.

## Contest description and generated overview

The contest manager can add an optional Markdown description in contest configuration. It is stored as source text on the contest, outside its reusable ruleset, and displayed at the top of public contest details. The frontend sanitizes rendered Markdown. Below it, the frontend generates “Contest rules at a glance” from the selected ruleset, including category meanings, choices, and any contest-specific dimension or choice explanations. Category dimensions and required Cabrillo fields are rendered as indented bullet lists. The overview also lists required fields for each enabled ADIF upload format, including importer-required QSO fields plus configured accepted bands, modes, and exchange constraints or values. Unless a contest-specific power description says otherwise, the summary assumes QRP up to 5 W, Low Power up to 100 W, and High Power up to the legal limit. This generated overview may be incomplete or imprecise; the sponsor's official published rules remain authoritative.

An exchange schema is the ordered set of values sent, received, exchanged in both directions, or declared once for an entry. A new ruleset starts with `rst` (Signal report) and a generic `exchange` (Contest exchange) field in both directions. These are editable starter values, not a claim that every sponsor requires the same exchange content. The [WWROF Cabrillo QSO specification](https://wwrof.org/cabrillo/cabrillo-qso-data/) shows the sent and received report and exchange positions; the sponsor defines the actual exchange elements, and a serial is only one possible exchange. Replace the generic field or add multiple fields to match those rules.

The new Cabrillo mapping is prefilled with the ten QSO columns required by the current importer, in the order shown in the mapping editor. The `rst_sent` and `rst_received` columns map the schema's `rst` field. The generic `exchange_sent` and `exchange_received` columns carry other configured exchange fields in their declared order; the composer previews this relationship automatically. Adding a schema field does not add another Cabrillo QSO column: multiple exchange values are parts of the existing exchange token field. The optional transmitter column remains available when the sponsor's template requires it. This behavior uses the existing ruleset/API schema and preserves imported mappings. ADIF exchange tags continue to use the same configured field definitions. The selected value type controls validation (text, integer, callsign, serial, enum, grid, or zone). Custom fields remain supported. Enum values and serial scopes are validated by the API.

## Eligibility catalogs

Band and mode catalogs are separate shared reference values, managed by global administrators in distinct Bands and Modes sections, each with its own “Add catalog item” form. Contest managers select allowed values with checkboxes. Each Configure checkbox appears directly above its matching eligible-band or allowed-mode choices. An empty selection means that dimension is unrestricted. Inactive catalog entries cannot be selected in new drafts. Existing ruleset snapshots remain unchanged; an entry referenced by a saved ruleset may be deactivated but cannot be deleted or renamed.

Boolean rule settings use one checkbox each; they do not have a separate “Configure” switch. Schema version 2 removes the schedule rule and cutoff timestamps from reusable rulesets. The bonus rule uses the presence of `evidence_key` to indicate that an evidence declaration is required. Legacy version 1 drafts can be imported in the composer; it removes the old schedule and cutoff fields, displays a migration notice, and exports version 2. An old `evidence_required` field is accepted only when it agrees with `evidence_key`, then removed.

The initial built-in band catalog includes named amateur bands from 2200 m through 3 cm (10 GHz), plus common modes (including CW, SSB, RTTY, FT8, and FT4). It does not seed bands above 10 GHz. Frequency text is a reference label, not a universal allocation: national authorizations, license privileges, and the published contest rules determine permitted use.

The initial catalog marks 2200 m, 630 m, 60 m, 30 m, 17 m, and 12 m as **no-contest bands (advisory)**, following the IARU's contest policy for narrow/secondary allocations ([IARU contest policy](https://www.iaru.org/on-the-air/iaru-contests/)). The Bands and Modes list displays this designation, and the ruleset composer displays it in red with visible text. It is advisory only: a mark never excludes a band or changes scoring automatically, and each contest's published rules remain authoritative. A global administrator can manage the designation for other entries.

The catalog data migration removes the above-10-GHz defaults from fresh installations and deactivates those legacy seeded entries on existing installations. Their stable keys and saved ruleset snapshots are preserved.

## Scoring and format mapping

- **Duplicate scope:** selected fields combine with worked callsign to define a duplicate. Adding band, mode, grid, or transmitter allows the same callsign to count separately when that field differs. The effect decides whether later duplicates are ignored, uncredited, penalized by an integer amount, or held for review. Duplicates never earn QSO points. The optional **Count for multipliers** setting allows an otherwise eligible duplicate to supply multiplier credit; it defaults off, and eligibility failures or later removal/review rules still suppress multiplier credit. If multiple duplicate rules match one contact, every matching duplicate rule must allow multiplier credit.
- **QSO points:** fixed integer points apply to eligible contacts. Lookup rules select an integer amount by exact normalized band, mode, entity, zone, continent, or exchange value. An optional default handles unlisted values; without one, unresolved values require review.
- **Score formula:** starts with a named integer variable or integer constant, then applies ordered operations. All intermediate results stay integers. Division must select floor division or rounded division and an explicit rounding convention. Example: `120 points × 8 multipliers + 10 bonus − 5 penalty = 965`.
- **Worked examples:** the composer shows examples for formula order, multiplier uniqueness scope, capped or threshold bonuses, and bounded penalties. For example, an entity worked five times on 20 m counts once at per-band scope, and the same entity on 40 m counts once more. A 2-point per-QSO bonus capped at 20 gives 14 points for 7 eligible QSOs and at most 20 for 10 or more. A 5-point penalty limited to 2 occurrences deducts no more than 10 points. The formula example is `120 points × 8 multipliers + 10 bonus − 5 penalty = 965`. These examples use integers and are illustrative; each contest's published rules determine which behavior to configure.
- **Format mapping:** enables one supported boundary format such as Cabrillo or ADI/ADIF for the contest and maps it to canonical fields and categories. Add one mapping per accepted format when the sponsor permits alternatives. Unknown fields can be preserved. CSV and native JSON are descriptive options only until an importer is implemented.

## API and administration

- `GET /api/v1/rulesets/bands` and `GET /api/v1/rulesets/modes` return active choices for the composer.
- `/api/v1/rulesets/admin/bands` and `/api/v1/rulesets/admin/modes` support independent catalog listing, creation, update, and deletion for global administrators only. Create/update/delete actions are audited. Server-side checks reject referenced-key changes and deletion; deactivate referenced entries instead. The combined operating-catalog routes remain compatibility adapters for existing API clients.
- Ruleset validation and save reject eligibility keys absent from or inactive in the managed catalog.

Run focused checks with `uv run pytest backend/tests/test_rulesets.py backend/tests/test_operating_catalog.py` and `cd frontend && npm test -- --run src/components/CategoryExchangeEditor.test.ts src/components/EligibilityCatalogEditor.test.ts src/views/RulesetComposerView.test.ts src/views/RulesetDraftSamples.test.ts src/views/OperatingCatalogAdminView.test.ts`.
