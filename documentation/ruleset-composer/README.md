# Ruleset composer guidance

The Vue composer exposes the same typed ruleset definition that the API validates. A contest manager should compare every draft with the sponsor's current rules before saving or activating it. The backend remains authoritative; browser controls only help build valid configuration.

## Schedule and submissions

Contest schedules use UTC only. Fixed editions use an ISO 8601 UTC instant such as `2026-01-01T00:00:00Z`; recurring editions use a UTC calendar date, a UTC time, and a positive duration in minutes. A local start-time control has no useful meaning for a UTC event instant. Daylight-saving “fold” means the repeated local wall-clock hour when clocks move backward. Since schedule rules are UTC, a fold cannot occur and the composer/schema no longer asks for a fold value.

Supported recurrence selectors are:

- **Annual date:** same month and day every year.
- **Nth weekday:** occurrence 1–5 or last (`-1`) of a chosen weekday within a month.
- **First full weekend:** the first Saturday and Sunday pair entirely within the chosen month; the schedule starts Saturday at its configured UTC time.

The API's `POST /api/v1/rulesets/schedule-preview` resolves a recurrence for a requested year. An annual date that does not exist in a year and a fifth weekday that does not exist are rejected with a useful error.

The log submission rule is separate from schedule end. A fixed cutoff must include a UTC offset; a relative cutoff is a signed whole-minute offset after contest end. The late policy is reject, accept as late, or classify as checklog. Manager extensions are possible only when explicitly enabled.

## Categories and exchanges

A category dimension is one entry-classification axis, such as operator, power, band, mode, assistance, transmitter count, or overlay. Its choices are the values allowed on that axis. Common keys and labels are selected from the controls; choose the custom option for sponsor-specific values. Keys are stable references used by imported categories, conditions, and format mappings. Changing a label never changes a key.

An exchange schema is the ordered set of values sent, received, exchanged in both directions, or declared once for an entry. Common fields include signal report, serial, CQ/ITU zone, section, grid, state/province, check, precedence, call area, and power. The selected value type controls validation (text, integer, callsign, serial, enum, grid, or zone). Custom fields remain supported. Enum values and serial scopes are validated by the API.

## Eligibility catalogs

Band and mode catalogs are separate shared reference values, managed by global administrators in distinct Bands and Modes sections, each with its own “Add catalog item” form. Contest managers select allowed values with checkboxes. Each Configure checkbox appears directly above its matching eligible-band or allowed-mode choices. An empty selection means that dimension is unrestricted. Inactive catalog entries cannot be selected in new drafts. Existing ruleset snapshots remain unchanged; an entry referenced by a saved ruleset may be deactivated but cannot be deleted or renamed.

The initial catalog includes named amateur bands from 2200 m through the 0.2 mm / 1.4 THz region and common modes (including CW, SSB, RTTY, FT8, and FT4). Frequency text is a reference label, not a universal allocation: national authorizations, license privileges, and the published contest rules determine permitted use. Administrators may edit the catalog accordingly.

An administrator may mark a band **contest-free**. The composer displays that managed designation in red and with visible text; it is advisory and never excludes a band or changes scoring automatically.

## Scoring and format mapping

- **Duplicate scope:** selected fields combine with worked callsign to define a duplicate. Adding band, mode, grid, or transmitter allows the same callsign to count separately when that field differs. The effect decides whether later duplicates are ignored, uncredited, penalized by an integer amount, or held for review.
- **QSO points:** fixed integer points apply to eligible contacts. Lookup rules select an integer amount by exact normalized band, mode, entity, zone, continent, or exchange value. An optional default handles unlisted values; without one, unresolved values require review.
- **Score formula:** starts with a named integer variable or integer constant, then applies ordered operations. All intermediate results stay integers. Division must select floor division or rounded division and an explicit rounding convention. Example: `120 points × 8 multipliers + 10 bonus − 5 penalty = 965`.
- **Format mapping:** maps a supported boundary format such as Cabrillo, ADIF, CSV, or native JSON to the application's canonical fields and categories. Unknown fields can be preserved. A mapping does not itself add parser support for a format the application has not implemented.

## API and administration

- `GET /api/v1/rulesets/bands` and `GET /api/v1/rulesets/modes` return active choices for the composer.
- `/api/v1/rulesets/admin/bands` and `/api/v1/rulesets/admin/modes` support independent catalog listing, creation, update, and deletion for global administrators only. Create/update/delete actions are audited. Server-side checks reject referenced-key changes and deletion; deactivate referenced entries instead. The combined operating-catalog routes remain compatibility adapters for existing API clients.
- Ruleset validation and save reject eligibility keys absent from or inactive in the managed catalog.

Run focused checks with `uv run pytest backend/tests/test_rulesets.py backend/tests/test_operating_catalog.py` and `cd frontend && npm test -- --run src/components/CategoryExchangeEditor.test.ts src/components/EligibilityCatalogEditor.test.ts src/views/RulesetComposerView.test.ts src/views/RulesetDraftSamples.test.ts src/views/OperatingCatalogAdminView.test.ts`.
