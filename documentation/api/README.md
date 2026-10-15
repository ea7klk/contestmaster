# API conventions

The REST API uses the `/api/v1` prefix. FastAPI publishes OpenAPI JSON at `/api/v1/openapi.json` and interactive documentation at `/api/v1/docs`; the schema is generated from typed request and response models.

## Error envelope

Errors have one stable JSON shape:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed.",
    "request_id": "server-generated-or-accepted-id",
    "details": [{ "location": ["query", "page"], "message": "Input should be greater than or equal to 1", "type": "greater_than_equal" }]
  }
}
```

`details` is omitted when no field-level details apply. Unexpected server failures return a generic message and never disclose exception details. A request ID is accepted from `X-Request-ID` only when it contains 1–128 ASCII letters, digits, dots, underscores, colons, or hyphens; otherwise the server generates a UUID. The value is echoed in the response header and included in request logs.

## Collections

Collection endpoints use one-based `page` (default `1`) and `page_size` (default `50`, maximum `100`). Responses include `items` and `meta` with page, page size, total count, and page count. Collection handlers whitelist allowed `sort` fields per resource and use a deterministic unique key as a secondary sort; unknown sort fields are rejected. `order` is `asc` or `desc`. Filters are explicitly documented per collection, use exact-match semantics unless an endpoint documents another operator, and combine with AND. Stable pagination requires a stable sort; use cursor pagination only if a future collection's update volume needs it.

## Authentication boundary

Privileged accounts use `POST /api/v1/auth/login`, `POST /api/v1/auth/logout`, and `GET /api/v1/auth/me`. Login uses email/password and issues an opaque server-side session in an `HttpOnly`, `SameSite=Strict` cookie. Mutating authenticated requests require the matching `X-CSRF-Token` header. `POST /api/v1/auth/admin/users` lets only global administrators create contest-manager accounts. Managers cannot provision users or acquire a privileged role through participant identity flows.

`/api/v1/contests` supports authenticated, paginated contest listing and manager-owned contest create/read/update operations. Manager list and detail access are filtered by owner in the API; a foreign contest ID is reported as not found. Global administrators can view all contests. List filters include exact `status`; supported sort keys are `id`, `name`, `slug`, `starts_at`, `ends_at`, and `created_at`, with a stable ID tie-breaker. New contests start in `draft`; status publication transitions and results are separate operations. Contest times must include UTC offsets, while submission cutoff remains separate from contest end.

Contest creation never accepts an owner identity from the request; the API assigns the authenticated account. All mutating privileged operations require both a valid session and CSRF token. Contest-scoped score-run review, QSO decisions, and Phase 8 result publication require the owner or a global administrator.

Public endpoints (health, published contest listings and published results) are explicitly unauthenticated. Guest log submission and entry receipt access are intentionally public/token-scoped workflows, not privileged accounts.

Participant email access uses `POST /api/v1/participants/auth/request-link` and `POST /api/v1/participants/auth/consume-link`. The request has a generic `202` response, creates an unprivileged participant identity if the email is new, and sends a 15-minute single-use verification/sign-in link when SMTP is configured. Only a hash of the token is stored, and requesting a replacement invalidates older links. Successful consumption marks the email verified and sets a separate participant-only session cookie; it never creates or grants a system role. `GET /api/v1/participants/auth/me` and `/entries` expose only that verified participant's identity and entries. `POST /api/v1/participants/auth/logout` revokes the participant session and requires its CSRF cookie/header pair.

Global administrators manage master-data history through `GET /api/v1/admin/master-data/versions` and `/sync-runs`, `POST /versions/{version_id}/activate`, and `DELETE /versions/{version_id}`. Every route requires a global-administrator session; mutations also require CSRF. Version records include effective dates, source/run provenance, checksum, status, no-change sync outcomes, and contest/score-run/QSO reference counts. Activation accepts only successful candidate runs. Deletion accepts only candidate/retired versions with no retained references, removes the snapshot rows but retains sync/audit history, and is protected by both API checks and database foreign-key/active-version constraints. Activation and deletion may include an optional `audit_reason` query parameter.

Contest managers may change an owned contest through `draft → open → closed → published`; a closed contest may be reopened, and a published contest may be withdrawn to closed. Opening or publishing requires a saved ruleset that still validates. `GET /api/v1/public/contests` and `GET /api/v1/public/contests/{slug}` expose only published contest metadata.

After an entry exists, its manager may call `PUT /api/v1/contests/{contest_id}/entries/{entry_id}/access-grant` with `operation` set to `create`, `set_expiry`, `revoke`, or `rotate`. Grant expiry is optional and must be a timezone-aware future instant when set. Create and rotate return an opaque `receipt_token` once; only its SHA-256 digest is retained. The route verifies both contest ownership and that the entry belongs to that contest. These operations are audited without storing the secret token.

## Log submission and entry corrections

- `GET /api/v1/public/submittable-contests` lists open contests whose submission cutoff is in the future.
- `POST /api/v1/public/contests/{contest_slug}/logs` accepts a multipart `file` plus required `Idempotency-Key`. The adapter supports UTF-8 Cabrillo files with `.log`, `.cbr`, `.cabrillo`, or `.txt` suffixes, up to 5 MiB. It requires exactly one `CALLSIGN` and `CONTEST` header and at least one complete QSO. The contest header must match the selected contest name or slug.
- The API limits full multipart requests to 5 MiB plus 64 KiB overhead and applies a 20-uploads-per-minute per-source-address limit in the initial single-process deployment. Upload filenames are reduced to safe basenames and never used as filesystem paths.
- Valid submissions create participant/entry records without a privileged account, an entry-scoped receipt grant, an immutable first revision, station and QSO rows in one ORM transaction. A supplied email matching an existing participant email links to that participant; new addresses remain unverified until the email magic-link flow confirms them.
- Idempotency keys are stored only as SHA-256 digests scoped to the contest. Repeating the same key and file returns the same entry and same deterministic receipt token; using that key for different content returns `409`. In production, `ENTRY_RECEIPT_SECRET` must remain stable and contain at least 32 random bytes. Receipt tokens are returned to the submitter, while persistence stores only their digest.
- Malformed files return HTTP `422` with line-scoped error codes and messages. Rejected input creates no participant, entry, or QSO rows. Warnings and unmapped categories are reported separately. Unknown headers and extra QSO fields are retained in revision metadata.
- Parsing and validation finish before the short persistence transaction begins. The exact UTF-8 input text, content digest, safe filename, import metadata, and normalized contacts are stored in ORM-managed revisions and child records. Each revision records whether it came from public submission, an entry receipt, or a verified participant session; participant revisions reference the verified email identity without storing session or receipt secrets.
- `GET /api/v1/public/entries/{entry_id}` and the entry correction/contact routes require a valid `X-Entry-Receipt` token or a verified participant session associated with the entry. Participant mutations also require the participant CSRF token. Invalid or expired grants do not reveal whether an entry exists.
- `PUT /api/v1/public/entries/{entry_id}/log` appends a full Cabrillo resubmission using `Idempotency-Key`. `POST /contacts`, `PUT /contacts/{contact_id}`, and `DELETE /contacts/{contact_id}` append contact changes as new immutable revisions. Contact IDs apply only to the current revision; prior revisions remain available for reproducibility.
- Managers may set grant expiry, revoke access, or rotate a receipt token through the contest access-grant endpoint above. Receipt secrets and idempotency keys are never written to logs.
- When `auto_recalculate_on_upload` is enabled, a successful new submission or full-log resubmission triggers scoring only after the accepted revision commits. Rejected requests and idempotent replays do not create another run. Upload responses include run IDs and statuses; scoring failures do not invalidate an accepted log.
- `GET /api/v1/contests/{contest_id}/score-runs` lists claimed, provisional, and adjudicated integer scores, input digest, status, timestamps, and failure details for the contest owner or a global administrator.
- `GET /api/v1/contests/{contest_id}/score-runs/{score_run_id}` returns that run with its per-QSO credited/status result, integer points/bonuses/penalties, multiplier keys, reason codes, and explanation. Both score-run endpoints require contest ownership and return `404` for foreign contest/run references.
- `POST /api/v1/contests/{contest_id}/qsos/{qso_id}/decisions` appends a manual decision. Its JSON body has `status` (`credited`, `not_credited`, or `needs_review`), `reason_code`, `reason`, and optional JSON `evidence`. The API stores reviewer and UTC timestamp, links the new row to the superseded decision, audits the change, then recalculates against that decision. Decisions and completed score runs are append-only.

## Result review, publication, and public standings

- `POST /api/v1/contests/{contest_id}/results/generate` requires manager/global-admin access and an `Idempotency-Key`. It reruns scoring for the contest and returns run IDs plus unresolved review items. `GET /api/v1/contests/{contest_id}/results/review` returns candidates, policy, and unresolved items for the authorized manager workspace.
- `POST /api/v1/contests/{contest_id}/results/publish` accepts `score_run_ids` and an optional audit reason. Only closed or already published contests can publish. Each selected run must be the latest completed run for its entry and match the current input revision. Publication atomically creates a sealed, immutable numbered snapshot and makes the contest public. Withdrawing a published contest returns it to closed; publishing again appends a new snapshot.
- Publication policy defaults exclude withdrawn entries and withhold late, checklog, and unresolved entries. Reclassified and disqualified entries are included with explicit status by default; disqualified score is zero and unranked. A declarative `result_publication` workflow hook can set boolean `include_late`, `include_checklog`, `include_needs_review`, `include_reclassified`, and `include_disqualified` values. No public response contains raw QSOs, private log files, participant contact details, or internal review notes.
- `GET /api/v1/public/contests` is unauthenticated and paginated; it lists only currently published contests. `GET /api/v1/public/contests/{slug}/results` returns the latest immutable snapshot with `page`, `page_size`, `sort` (`placement`, `score`, `callsign`, `status`), `order`, configured `category`/`value`, `band`, `mode`, and result `status` filters. Unknown category dimensions/values are rejected. The response includes aggregate score explanation, category values, status, available filters, publication number/digest, and pagination metadata.
- `GET /api/v1/public/contests/{slug}/results/entries/{result_entry_id}` returns one public-safe snapshot row. `GET /api/v1/public/contests/{slug}/results/export?format=json|csv` downloads the full publication as deterministic `results-v1` JSON or CSV and sets `X-Contestmaster-Export-Version: results-v1`. Sponsor-specific exports are deferred until an initial contest requires and defines one.
- `GET /api/v1/public/entries/{entry_id}/revisions/{revision_id}/download` downloads the exact original Cabrillo revision. It requires that entry's valid receipt token or associated verified participant session; it is not a public result download. Managers can review original logs through the existing manager entry workflow.

## Ruleset authoring

The graphical composer uses UTC-only schedules with API-resolved recurrence previews. See [Ruleset composer guidance](../ruleset-composer/README.md) for schedule, category, exchange, eligibility catalog, scoring, and format explanations. Active shared band/mode choices are available at `GET /api/v1/rulesets/operating-catalog`. Global administrators manage them at `/api/v1/rulesets/admin/operating-catalog`; managers cannot modify this catalog. Eligibility keys must refer to active catalog items when a ruleset is validated or saved. Catalog edits are audited, and referenced keys cannot be renamed or deleted (deactivate them instead).

`POST /api/v1/rulesets/schedule-preview` accepts `{ "year": 2026, "schedule": { ... } }` with a typed UTC `ScheduleRule`; it returns `starts_at` and `ends_at` as UTC ISO 8601 instants. Unsupported or nonexistent dates return 422 validation errors.

- `GET /api/v1/rulesets/catalog` returns the typed schemas, labels, and execution expectations for the built-in rule types used by the graphical composer.
- `POST /api/v1/rulesets/validate` accepts a proposed declarative ruleset but does not save or activate it. A valid response includes the normalized metadata, configured rule-type list, readable summary, and integer-only worked formula example. Invalid configurations return the standard error envelope with rule paths and messages.
- `GET /api/v1/rulesets/versions` lists immutable saved versions for authenticated administrators and managers. `POST /api/v1/rulesets/versions` stores a validated version, is idempotent for identical content, and rejects attempts to reuse a key/version with different content.
- `PUT /api/v1/contests/{contest_id}/ruleset` activates a saved version for a draft contest. The API checks contest ownership, revalidates the immutable version, and appends activation provenance. Managers cannot activate rules for another manager's contest.
- Administrative account creation, contest creation/updates/status changes, ruleset version creation/activation, entry receipt-grant changes, and master-data version activation/deletion append `audit_events` in the same ORM transaction as the operation. Events include the acting account where present, UTC occurrence time, target, request ID, safe allowlisted metadata, and an optional reason. Audit rows are protected against update and delete by database triggers.
- Conditions use the declared compare/all/any/not expression tree. The API rejects unknown fact paths and unsafe regular-expression features; it never evaluates submitted Python or JavaScript.
- `EligibilityRule.eligible_if` is a positive QSO predicate over configured contact geography, entry categories/declarations, exchanges, and station callsign. A contact that fails this predicate follows the rule's explicit `not_credited` or `needs_review` action.
- Cross-log matching runs only when the ruleset has a `workflow_hook` at stage `cross_log`. It compares reciprocal normalized callsigns, band/mode when present on both logs, UTC timestamps, and swapped exchange values. Optional `timestamp_tolerance_seconds` (default 300) and per-field integer `numeric_exchange_tolerances` configure matching. Outcomes retain a reason code and counterpart evidence. Missing or mismatched counterparts remain review findings unless `require_counterpart: true` is explicitly configured.
- Cabrillo exchange tokens map to semantic exchange fields in the configured exchange-rule order only when the token count matches; otherwise the submitted raw exchange is retained for review and the scorer does not guess a mapping.
- Rules that consume `entity`, `cq_zone`, `itu_zone`, or `continent` require a `cty` version pinned for the contest-start instant. Each score run records all contest pins used. If a required pin is missing or invalid, scoring fails with the dataset key rather than falling back to the latest active version.
- Domain scoring returns pending structured workflow actions for publication and award consumers. These are handoff requests for trusted services, not dynamically loaded user code.
- Saving and activating rulesets is a privileged contest-manager operation. Ruleset definitions are immutable versions, and every selection change is recorded in append-only contest activation history. Current API authentication enforcement is completed in Phase 5.

## Versioning

Additive, backward-compatible fields and endpoints remain in the current API version. Removing or changing field meaning, response shape, or behavior incompatibly requires a new `/api/vN` route prefix and a documented deprecation/migration period. OpenAPI is the machine-readable contract for each version.
