# Ruleset composer guidance

The Vue composer exposes the same typed ruleset definition that the API validates. A contest manager should compare every draft with the sponsor's current rules before saving or activating it. The backend remains authoritative; browser controls only help build valid configuration.

## Import contests and edit saved rulesets

From **Contest manager**, choose **Import contest** and select a JSON package containing a `contest` object and a `ruleset` object. The contest object uses UTC start, end, and submission-cutoff timestamps plus optional periodicity; the ruleset object uses schema version 2 described in [ruleset drafts](../ruleset-drafts/README.md). The API validates both together, creates a manager-owned draft, saves and assigns its immutable ruleset version, and commits the operation atomically. If the file is malformed, the contest is invalid, an operating-catalog key is unavailable, or either record conflicts, no partial import is retained.

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

The example's empty `rules` array is a shape illustration only; a real ruleset must include and validate all required rule types. The contest manager shows the contest list above the create/edit form; filter it by name, URL slug, or status. The list is keyboard-scrollable when it grows. The **Edit ruleset** action on a contest opens its saved version in the graphic composer. At the top of the composer, **Continue from a saved ruleset** browses any saved version, including versions not assigned to a contest; filter the scrollable list by ruleset key, version, source edition, or rule type, then select a version to load it. A loaded version becomes a new draft: enter a new version identifier and save. Existing versions are immutable, and editing does not change a contest's current assignment. Select the newly saved version from the contest manager when ready.

## Schedule and submissions

The contest manager owns UTC start and end instants and optional periodicity. Configure one-time or recurring schedule details in the contest form; schedule settings are not part of a reusable ruleset. Enter actual event instants in UTC. For recurring contests, choose annual date, nth weekday, or first full weekend, and preview a selected UTC year. A local start-time control adds no information to a UTC event instant. Daylight-saving “fold” means the repeated local wall-clock hour when clocks move backward; UTC scheduling has no fold.

Supported recurrence selectors are:

- **Annual date:** same month and day every year.
- **Nth weekday:** occurrence 1–5 or last (`-1`) of a chosen weekday within a month.
- **First full weekend:** the first Saturday and Sunday pair entirely within the chosen month; the schedule starts Saturday at its configured UTC time.

The API's `POST /api/v1/contests/schedule-preview` previews the contest's recurrence for a requested year. An annual date that does not exist in a year and a fifth weekday that does not exist are rejected with a useful error.

Contest configuration owns the separate UTC log submission cutoff. The ruleset's log-submission policy only determines whether uploads beyond that cutoff are rejected, accepted as late, or classified as checklog. Manager extensions are possible only when explicitly enabled by the ruleset.

## Categories and exchanges

A category dimension is one entry-classification axis, such as operator, power, band, mode, assistance, transmitter count, or overlay. Its choices are the values allowed on that axis. Common keys and labels are selected from the controls; choose the custom option for sponsor-specific values. Keys are stable references used by imported categories, conditions, and format mappings. Changing a label never changes a key.

An exchange schema is the ordered set of values sent, received, exchanged in both directions, or declared once for an entry. Common fields include signal report, serial, CQ/ITU zone, section, grid, state/province, check, precedence, call area, and power. The selected value type controls validation (text, integer, callsign, serial, enum, grid, or zone). Custom fields remain supported. Enum values and serial scopes are validated by the API.

## Eligibility catalogs

Band and mode catalogs are separate shared reference values, managed by global administrators in distinct Bands and Modes sections, each with its own “Add catalog item” form. Contest managers select allowed values with checkboxes. Each Configure checkbox appears directly above its matching eligible-band or allowed-mode choices. An empty selection means that dimension is unrestricted. Inactive catalog entries cannot be selected in new drafts. Existing ruleset snapshots remain unchanged; an entry referenced by a saved ruleset may be deactivated but cannot be deleted or renamed.

Boolean rule settings use one checkbox each; they do not have a separate “Configure” switch. Schema version 2 removes the schedule rule and cutoff timestamps from reusable rulesets. The bonus rule uses the presence of `evidence_key` to indicate that an evidence declaration is required. Legacy version 1 drafts can be imported in the composer; it removes the old schedule and cutoff fields, displays a migration notice, and exports version 2. An old `evidence_required` field is accepted only when it agrees with `evidence_key`, then removed.

The initial built-in band catalog includes named amateur bands from 2200 m through 3 cm (10 GHz), plus common modes (including CW, SSB, RTTY, FT8, and FT4). It does not seed bands above 10 GHz. Frequency text is a reference label, not a universal allocation: national authorizations, license privileges, and the published contest rules determine permitted use.

The initial catalog marks 2200 m, 630 m, 60 m, 30 m, 17 m, and 12 m as **no-contest bands (advisory)**, following the IARU's contest policy for narrow/secondary allocations ([IARU contest policy](https://www.iaru.org/on-the-air/iaru-contests/)). The Bands and Modes list displays this designation, and the ruleset composer displays it in red with visible text. It is advisory only: a mark never excludes a band or changes scoring automatically, and each contest's published rules remain authoritative. A global administrator can manage the designation for other entries.

The catalog data migration removes the above-10-GHz defaults from fresh installations and deactivates those legacy seeded entries on existing installations. Their stable keys and saved ruleset snapshots are preserved.

## Scoring and format mapping

- **Duplicate scope:** selected fields combine with worked callsign to define a duplicate. Adding band, mode, grid, or transmitter allows the same callsign to count separately when that field differs. The effect decides whether later duplicates are ignored, uncredited, penalized by an integer amount, or held for review.
- **QSO points:** fixed integer points apply to eligible contacts. Lookup rules select an integer amount by exact normalized band, mode, entity, zone, continent, or exchange value. An optional default handles unlisted values; without one, unresolved values require review.
- **Score formula:** starts with a named integer variable or integer constant, then applies ordered operations. All intermediate results stay integers. Division must select floor division or rounded division and an explicit rounding convention. Example: `120 points × 8 multipliers + 10 bonus − 5 penalty = 965`.
- **Format mapping:** enables one supported boundary format such as Cabrillo or ADI/ADIF for the contest and maps it to canonical fields and categories. Add one mapping per accepted format when the sponsor permits alternatives. Unknown fields can be preserved. CSV and native JSON are descriptive options only until an importer is implemented.

## API and administration

- `GET /api/v1/rulesets/bands` and `GET /api/v1/rulesets/modes` return active choices for the composer.
- `/api/v1/rulesets/admin/bands` and `/api/v1/rulesets/admin/modes` support independent catalog listing, creation, update, and deletion for global administrators only. Create/update/delete actions are audited. Server-side checks reject referenced-key changes and deletion; deactivate referenced entries instead. The combined operating-catalog routes remain compatibility adapters for existing API clients.
- Ruleset validation and save reject eligibility keys absent from or inactive in the managed catalog.

Run focused checks with `uv run pytest backend/tests/test_rulesets.py backend/tests/test_operating_catalog.py` and `cd frontend && npm test -- --run src/components/CategoryExchangeEditor.test.ts src/components/EligibilityCatalogEditor.test.ts src/views/RulesetComposerView.test.ts src/views/RulesetDraftSamples.test.ts src/views/OperatingCatalogAdminView.test.ts`.
