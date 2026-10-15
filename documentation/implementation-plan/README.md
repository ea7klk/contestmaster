# Contestmaster implementation plan

This roadmap turns the product and architecture decisions in [the system overview](../README.md), [the initial rule catalog](../preliminary-ruleset/README.md), and [the master-data source catalog](../master-data/README.md) into an ordered implementation. The repository currently contains product documentation only, so this plan starts with a runnable project foundation.

## Delivery goal

Deliver a deployable web application in which a contest manager can create and configure a contest, a participant can upload a log without registering, the backend can validate and score it using a versioned ruleset, and anyone can view published results without signing in. Global administrators can administer the whole system. All persistent application data uses the Python ORM with SQLite; all score values are integers.

The initial release includes every checked rule type in the system catalog: schedule/cutoff, categories, exchange schema, QSO eligibility and duplicates, points and integer score composition, multipliers, bonuses and penalties, operating limits, log format mapping, cross-log checks and review/publication eligibility, and ruleset provenance with explainable immutable score runs.

## Phase 0 — Decisions to settle at project start

Record the selected choices in a short architecture decision log before implementation begins. The product documentation fixes the architecture boundaries but does not yet choose these details.

### Recorded decisions

- **Python REST framework and validation/schema library:** FastAPI + Pydantic. This fits the API-first design and provides typed request/response schemas with generated OpenAPI.
- **ORM and migration tools:** SQLAlchemy 2.x + Alembic. This provides the required ORM-managed SQLite access and explicit schema migrations.
- **Vue toolchain and component strategy:** Vue 3 + TypeScript + Vite + Vue Router + Pinia, with a small set of accessible application components. Use typed component boundaries and semantic HTML; avoid introducing a full UI framework until the workflows demonstrate a need.
- **Authentication, account recovery, and first administrator:** use app-managed accounts for the initial release. Hash passwords with Argon2id; use server-side sessions in `Secure`, `HttpOnly`, and `SameSite` cookies; provide single-use, expiring email reset links; and provision the first global administrator through a one-time CLI command with no default password. Design an extension point for common OIDC providers that can each be configured and activated independently in a later release. Keep local authorization roles explicit; an external identity must not gain global-administrator privileges through automatic registration or an unreviewed claim mapping. This follows [OWASP password storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html), [session management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html), and [password reset](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html) guidance.

### Decisions remaining

- How a guest entrant securely corrects or withdraws a submitted log and manages individual contacts after upload. Proposed default: allow a revised log submission tied to the same entry using a time-limited, unguessable receipt token; do not require a participant system account.
- Deployment and nightly scheduler mechanism. Keep the first deployment to one API instance and local SQLite storage.
- Which national call-district sources are in the first release, and what review workflow to use where no public machine-readable source exists.
- Whether ARRL DXCC data can be used in the hosted service. ARRL's published text list requires permission for uses beyond personal use; obtain permission before ingesting or redistributing it. Big CTY is the designated primary operational feed for the data it contains.

**Exit criteria:** decisions are recorded, supported local development commands are documented, and the repository has a clear frontend/backend layout and coding conventions.

## Phased work

### Phase 1 — Project foundation and API contract

**Depends on:** Phase 0 decisions.

1. Create frontend and backend application skeletons, dependency locking, environment configuration, formatting/linting, and a local developer workflow.
2. Define the API error envelope, API versioning policy, pagination/filter/sort conventions, authentication boundary, and OpenAPI publication.
3. Establish ORM session lifecycle, transaction helpers, migration workflow, and SQLite connection settings: foreign keys enabled, busy timeout, short write transactions, and WAL where appropriate.
4. Add a health/readiness endpoint and structured request logging with correlation IDs.

**Exit criteria:** a developer can start the API and Vue application locally; OpenAPI is available; schema changes run through migrations; no application code accesses SQLite outside the ORM.

### Phase 2 — Domain model and persistence

**Depends on:** Phase 1 project and persistence conventions.

1. Implement the first migration for users/roles, contests, ruleset versions, participants, entries, stations, QSOs, QSO decisions, score runs, per-QSO score explanations, master-data sources/runs/versions, and geographic/callsign reference tables.
2. Enforce database constraints for ownership, unique contest identifiers, valid relationships, nullable guest submitter identity, and integer score storage.
3. Store original submitted callsigns and exchanges separately from normalized/resolved values. Store contest instants and QSO timestamps in UTC at explicit precision.
4. Add revision/snapshot identifiers so an entry/log revision, ruleset version, and relevant master-data version can be tied to a score run.
5. Define retention and visibility rules for uploaded logs, participant details, admin notes, and audit history.

**Exit criteria:** migrations create the documented schema from an empty database; ORM repositories can create/read the core entities; historical records can be represented without overwriting submitted data.

### Phase 3 — Master-data ingestion

**Depends on:** Phase 2 master-data schema and ORM layer.

1. Implement a versioned `cty.dat` parser and import Big CTY as the primary operational source for callsign prefixes, DXCC entities, and callsign-based CQ/ITU zone mappings.
2. Keep CQ zones, amateur ITU zones, ITU Radio Regions, and IARU Regions in separate namespaces/tables. Add entity-zone and prefix-zone mappings with effective dates and source/version provenance.
3. Add official/public gap-filling imports or reviewed seed datasets for country/area identifiers, IARU Regions, ITU Radio Regions, and selected national call districts. Do not infer one global call-district format.
4. Implement a nightly source-check/import command. Capture source URL, release marker, fetched-at time, checksum, parser version, use terms, counts, and status for every run.
5. Validate keys, completeness, expected counts, cross-references, and effective dates before activation. Preserve the last good version on fetch/parse/validation failure; stage meaningful boundary changes for review.
6. Preserve applicable license notices with imported artifacts. Do not import or publish restricted data until its permitted use has been established.

**Exit criteria:** a clean install can load a known CTY release; repeat imports are idempotent; a failed or partial import cannot replace active data; import history and differences are reviewable; the nightly command is schedulable and observable.

### Phase 4 — Ruleset engine and initial rule catalog

**Depends on:** Phase 2 domain model; use Phase 3 reference-data identifiers for geographic and prefix rules.

1. Define a declarative, schema-validated ruleset format and a typed registry for the initial reusable rule types. Support conditional rule groups without arbitrary user-supplied code or `eval`.
2. Implement schedule resolution (including recurrence to saved UTC instants), UTC log cutoff and late-log policy, category dimensions/compatibility, and exchange schemas/validators.
3. Implement QSO eligibility predicates, duplicate-key scopes, integer point rules, multiplier definitions/scopes/eligibility, integer bonuses/penalties, and an integer-only score expression with explicit operation order and rounding.
4. Model operating-time/off-time, band-change, and transmitter constraints, clearly identifying which checks are automatic and which need entrant declarations or human review.
5. Define import/export format mappings and category mappings as configuration separate from parser code. Add hooks for cross-log checks, adjudication decisions, result publication, and award eligibility.
6. Validate required parameters and incompatible combinations. Produce a human-readable rules summary and worked examples before activation.
7. Persist ruleset key, version, source URL, source edition/year, configuration, and activation history. Existing contests and score runs retain their selected version.

**Exit criteria:** every checked item in the initial system rule catalog has a defined configuration schema, validation behavior, and execution/adjudication contract; missing or unsupported rules fail visibly rather than receiving hidden defaults.

### Phase 5 — Identity, authorization, and contest management

**Depends on:** Phases 1, 2, and 4.

1. Implement the two privileged roles: global administrator and contest manager. Provision the first global administrator through a documented secure operation.
2. Enforce authorization in the API: administrators have all privileges; managers can create/manage their own contests, edit rules, run result generation, and generate result lists only for contests they own.
3. Build Vue sign-in and contest-manager workflows, including contest list/detail, contest creation/editing, schedule/cutoff, category setup, ruleset selection, and automatic recalculation setting.
4. Implement contest status/publication transitions and validation before a contest/ruleset is made available.
5. Record administrative changes with actor, time, target, and an audit reason where appropriate.

**Exit criteria:** API authorization tests show no manager can access another manager's contest; the manager can configure and save a validated contest; public visibility is controlled by publication state.

### Phase 6 — Guest log submission and format adapters

**Depends on:** Phases 2, 4, and 5.

1. Implement unauthenticated log-submission endpoints with request/file size limits, accepted-format checks, rate limits, idempotency support, and safe filename handling.
2. Create participant and entry records from submission data without requiring a system account; keep the privileged-user submitter reference nullable.
3. Implement Cabrillo parsing first, with contest-specific header/QSO templates and category mapping; preserve unknown headers/fields for review or round-trip export.
4. Parse files outside long-lived database transactions, then persist accepted input atomically through ORM transactions.
5. Validate required records and fields; return line-level errors, warnings, accepted/rejected counts, and an import summary. Preserve original input and normalized interpretations.
6. Build Vue upload UI with progress, success/error summaries, retry behavior, and accessible status announcements.
7. Support authorized log correction/resubmission and add/edit/remove contact workflows. Keep each accepted change as a new input revision; preserve prior submissions and score-run inputs for audit and reproducibility.

**Exit criteria:** an unregistered entrant can submit a valid supported log; malformed logs return useful line-level feedback and are not partially accepted; repeated idempotent submissions do not create duplicate entries; uploaded content cannot inject executable UI content.

### Phase 7 — Adjudication, cross-log checking, and scoring

**Depends on:** Phases 2, 3, 4, and 6.

1. Implement domain services independent of HTTP and ORM for callsign normalization, exchange comparison, QSO validation, duplicate selection, contest-period/band/mode checks, and configured operating constraints.
2. Implement counterpart-log matching and configurable timestamp/exchange tolerances. Keep each checking outcome as a reasoned QSO decision.
3. Implement scoring as deterministic integer operations. Store claimed, provisional, and adjudicated scores and an immutable per-QSO breakdown of points, multipliers, bonuses, penalties, and explanations.
4. Implement manual review with reviewer, timestamp, evidence, reason, and superseding decisions that preserve the prior audit trail.
5. Tie every score run to a stable input log revision, ruleset version, and master-data snapshot where used. Keep prior runs when entries, decisions, or rules change.
6. Implement contest-level `auto_recalculate_on_upload`: trigger only after an accepted new log is committed; do not trigger for rejected uploads. Make retries safe and expose failed/in-progress runs.

**Exit criteria:** identical input revisions and versions reproduce identical results; all score fields are integers; each QSO's credit/status and every score component can be explained; automatic recalculation follows the per-contest setting and is safe to retry.

### Phase 8 — Result generation and public frontend

**Depends on:** Phases 5 and 7.

1. Implement manager actions to run/re-run result generation, review unresolved items, generate result lists, and publish a selected score run.
2. Implement public unauthenticated contest discovery and result/standings pages with category, band, mode, status, and other configured grouping filters.
3. Apply publication rules to late logs, checklogs, withdrawn, reclassified, and disqualified entries; avoid exposing private contact data or internal review notes.
4. Add paginated/filterable API endpoints and matching responsive Vue tables. Include score explanations and clear status labels for data that is public.
5. Implement reproducible result exports and versioned downloadable log/result formats required by the selected initial contests.

**Exit criteria:** a published contest result is readable without login; private/unpublished contest data is not exposed; manager-only result operations are protected; displayed totals match the persisted score run and exports.

### Phase 9 — Hardening and first deployment

**Depends on:** Phases 1–8.

1. Complete security review of authentication/session/token handling, authorization, CSRF/CORS, upload validation, rate limits, error leakage, and user-submitted content rendering.
2. Verify accessible keyboard and screen-reader operation for the rule composer, upload flow, manager pages, and standings.
3. Add operational dashboards/alerts for nightly master-data syncs, uploads, score runs, failed jobs, database errors, and API health.
4. Document configuration/secrets, database backup and restore, migration/rollback process, log retention, and incident recovery.
5. Deploy one API instance with local SQLite storage and a nightly scheduler. Test backup restoration and a full contest workflow in a staging environment before production.
6. Publish operator and participant documentation, API reference, supported format/version list, data source/license inventory, and known limitations.

**Exit criteria:** staging can complete the end-to-end acceptance scenario below; backups restore successfully; critical operations have observable outcomes and recovery steps; release artifacts and configuration are reproducible.

## End-to-end release acceptance scenario

1. A global administrator provisions a contest manager account.
2. The contest manager creates a contest with UTC start/end/cutoff times, categories, a versioned ruleset, and the automatic recalculation setting.
3. The rules composer validates the configuration, displays a readable summary, and activates the contest/ruleset version.
4. An unauthenticated entrant uploads a Cabrillo log. The system creates participant/entry records without a user account and returns import feedback.
5. The backend validates and adjudicates the QSOs, applies duplicate and cross-log rules, and creates an integer-only explainable score run tied to the exact input/rules/master-data versions.
6. The per-contest recalculation setting is honored. The manager can review decisions, generate a result list, and publish it.
7. An unauthenticated visitor can view the published standings and allowed score breakdowns; private log content and internal notes remain hidden.
8. A nightly master-data run imports or checks Big CTY and configured supplemental sources, preserves provenance, and leaves active data intact if a source fails validation.

## Cross-cutting verification gates

Each phase should include focused automated tests for its domain and API contracts, plus manual UI checks where appropriate. Before release, verify:

- All scoring values use integer types end-to-end, including API schemas, ORM columns, expressions, exports, and UI formatting.
- UTC timestamps, cutoff boundaries, and resolved recurring schedules behave consistently at exact boundary times.
- Guest uploads, manager authorization, administrator privileges, public read access, and unpublished-data privacy have explicit coverage.
- Import/recalculation retries are idempotent; partial failures do not corrupt logs, master data, or published results.
- Ruleset/master-data/source changes do not silently alter historical score runs.
- SQLite connections use the ORM, foreign keys are enabled, write transactions stay short, and backup/restore is proven.

## Deferred beyond the initial release

The current product documents identify live/near-live standings, multi-operator collaboration, additional logging integrations, multiple API instances, and a separate worker/job queue as later capabilities. Revisit those when usage, latency, or concrete interoperability requirements justify them; the first release should retain the documented single-instance, low-concurrency SQLite operating model.
