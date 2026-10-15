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
- **Guest and registered participant access:** guests receive an entry-scoped receipt token for correction/resubmission and contact management; registered contest participants use email magic links to access only entries associated with their verified participant identity. Participant access does not create a privileged system role. Store only hashes of guest receipt tokens; let contest managers set expiry and close/revoke or rotate a grant. Preserve every accepted change as a new log revision. Display/download the guest secret at submission time, and never write it to application logs.
- **Initial startup and master-data scheduling:** start the stack from CLI on one host with SQLite on local storage. Run nightly master-data provisioning through an internal API timer, and trigger an immediate initial import at API startup if no active master-data version exists. Keep the importer callable as an independent job, expose provisioning status, and require valid master data for dependent scoring. Run a single API process initially; make imports idempotent and prevent overlapping runs. Prepare the same importer entry point for a future managed container platform, using K3s CronJobs to create one-shot Jobs.
- **DXCC reference data licensing:** exclude the ARRL DXCC list from the hosted service indefinitely; do not download, ingest, copy, or redistribute that list. Continue using permitted Big CTY `cty.dat` operational mappings with its required license notice, and use each contest's published rules as the authority for scoring. Do not use ADIF enumerations as a licensing workaround.

### Decisions remaining

None. All current Phase 0 decisions have been recorded.

**Exit criteria:** decisions are recorded, supported local development commands are documented, and the repository has a clear frontend/backend layout and coding conventions.

## Phased work

### Phase 1 — Project foundation and API contract

**Depends on:** Phase 0 decisions.

1. Create frontend and backend application skeletons, dependency locking, environment configuration, formatting/linting, and a local developer workflow.
2. Define the API error envelope, API versioning policy, pagination/filter/sort conventions, authentication boundary, and OpenAPI publication.
3. Establish ORM session lifecycle, transaction helpers, migration workflow, and SQLite connection settings: foreign keys enabled, busy timeout, short write transactions, and WAL where appropriate.
4. Add a health/readiness endpoint and structured request logging with correlation IDs.

**Exit criteria:** a developer can start the stack from CLI with the documented command; OpenAPI is available; schema changes run through migrations; no application code accesses SQLite outside the ORM.

### Phase 2 — Domain model and persistence

**Depends on:** Phase 1 project and persistence conventions.

1. Implement the first migration for users/roles, participants and verified emails, contests, ruleset versions, entries, guest entry-access grants, stations, QSOs, QSO decisions, score runs, per-QSO score explanations, master-data sources/runs/versions, and geographic/callsign reference tables.
2. Enforce database constraints for ownership, unique contest identifiers, valid relationships, nullable guest submitter identity, hashed entry-token storage, and integer score storage.
3. Store original submitted callsigns and exchanges separately from normalized/resolved values. Store contest instants and QSO timestamps in UTC at explicit precision.
4. Add revision/snapshot identifiers so an entry/log revision, ruleset version, and relevant master-data version can be tied to a score run.
5. Define retention and visibility rules for uploaded logs, participant details, admin notes, and audit history.

**Exit criteria:** migrations create the documented schema from an empty database; ORM repositories can create/read the core entities; historical records can be represented without overwriting submitted data.

### Phase 3 — Master-data ingestion

**Depends on:** Phase 2 master-data schema and ORM layer.

1. Implement a versioned `cty.dat` parser and import Big CTY as the permitted primary operational source for callsign prefixes, DXCC mappings, and callsign-based CQ/ITU zone mappings. Preserve its applicable copyright/license notice; never ingest the separate ARRL DXCC list.
2. Keep CQ zones, amateur ITU zones, ITU Radio Regions, and IARU Regions in separate namespaces/tables. Add entity-zone and prefix-zone mappings with effective dates and source/version provenance.
3. Add official/public gap-filling imports for country/area identifiers and IARU/ITU regions. UNGEGN WGN currently supplies an enabled, versioned reference for 193 UN member-country names and M49 codes; keep broader territory/area coverage unresolved until a permitted machine-readable source is established.
4. Implement the master-data source-check/import as an idempotent callable job and CLI command. Capture source URL, release marker, fetched-at time, checksum, parser version, use terms, counts, and status for every run.
5. Add an internal API scheduler that invokes the job at startup when no active version exists and nightly thereafter. Prevent overlapping executions, expose provisioning status, and report failures. Keep scheduling separate from import logic so a future K3s CronJob can launch the same one-shot command.
6. Validate keys, completeness, expected counts, cross-references, and effective dates before activation. Preserve the last good version on fetch/parse/validation failure; stage meaningful boundary changes for review.
7. Preserve applicable license notices with imported artifacts. Do not import or publish restricted data until its permitted use has been established.
8. Give each dataset version an explicit UTC validity interval. After a contest has started, pin the version of each required dataset whose half-open interval contains the contest start instant to that contest. Store contest-to-version and score-run-to-version references so deletion safeguards and later scoring use the same selected versions. If no version covers the contest start, block scoring that depends on it.
9. Compare each successfully parsed dataset's canonical checksum with its current version. Record an `unchanged` sync run without creating a `MasterDataVersion` or changing validity intervals when content is identical; create and activate a new version only for a validated data change.

**Exit criteria:** a clean install can load a known CTY release and the enabled permitted gap-filling datasets; repeat imports are idempotent and unchanged content creates no version; a failed or partial import cannot replace active data; contest-start selection matches effective intervals and pins exact versions; import history and differences are reviewable; the internal API timer and one-shot CLI job are observable and safe to retry. The importer has adapters for Big CTY and UNGEGN WGN's 193 country-name/M49 records. Phase 3 remains incomplete until broader country/area coverage and IARU/ITU Radio Region sources are resolved.

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
3. Implement email magic-link verification and sign-in for registered contest participants, scoped only to that participant's entries and profile. Do not map participant identities to either privileged role.
4. Build Vue privileged sign-in and contest-manager workflows, including contest list/detail, contest creation/editing, schedule/cutoff, category setup, ruleset selection, and automatic recalculation setting.
5. Implement contest status/publication transitions and validation before a contest/ruleset is made available. Let managers set guest access expiry and close/revoke or rotate entry grants.
6. Record administrative changes with actor, time, target, and an audit reason where appropriate.
7. Build a global-administrator-only master-data version section in the Vue application and matching protected API operations. Show dataset versions, effective intervals, provenance, sync results, and references; allow activation of validated candidates and deletion only for old non-current versions with no contest, score-run, QSO-resolution, or other retained-record references. Enforce the role check in the API and reference checks in the API/database, not only in the UI.

**Exit criteria:** API authorization tests show no manager can access another manager's contest or global master-data administration; global administrators can review version history and delete only eligible unreferenced old versions; the manager can configure and save a validated contest; public visibility is controlled by publication state.

### Phase 6 — Guest log submission and format adapters

**Depends on:** Phases 2, 4, and 5.

1. Implement unauthenticated log-submission endpoints with request/file size limits, accepted-format checks, rate limits, idempotency support, and safe filename handling.
2. Create participant and entry records from submission data without requiring a system account; keep the privileged-user submitter reference nullable. Associate verified participant identities when the entrant has registered.
3. Implement Cabrillo parsing first, with contest-specific header/QSO templates and category mapping; preserve unknown headers/fields for review or round-trip export.
4. Parse files outside long-lived database transactions, then persist accepted input atomically through ORM transactions.
5. Validate required records and fields; return line-level errors, warnings, accepted/rejected counts, and an import summary. Preserve original input and normalized interpretations.
6. Build Vue upload UI with progress, success/error summaries, retry behavior, and accessible status announcements.
7. Support guest correction/resubmission and add/edit/remove contact workflows using a receipt token scoped to one entry. Registered participants may use verified email magic links to manage their associated entries. Managers control guest token expiry and can close, revoke, or rotate access. Keep each accepted change as a new input revision; preserve prior submissions and score-run inputs for audit and reproducibility.

**Exit criteria:** an unregistered entrant can submit a valid supported log and use only the associated entry's receipt token; a registered participant can use an expiring email magic link limited to their entries; managers can end guest access; malformed logs return useful line-level feedback and are not partially accepted; repeated idempotent submissions do not create duplicate entries; uploaded content cannot inject executable UI content.

### Phase 7 — Adjudication, cross-log checking, and scoring

**Depends on:** Phases 2, 3, 4, and 6.

1. Implement domain services independent of HTTP and ORM for callsign normalization, exchange comparison, QSO validation, duplicate selection, contest-period/band/mode checks, and configured operating constraints.
2. Implement counterpart-log matching and configurable timestamp/exchange tolerances. Keep each checking outcome as a reasoned QSO decision.
3. Implement scoring as deterministic integer operations. Store claimed, provisional, and adjudicated scores and an immutable per-QSO breakdown of points, multipliers, bonuses, penalties, and explanations.
4. Implement manual review with reviewer, timestamp, evidence, reason, and superseding decisions that preserve the prior audit trail.
5. Tie every score run to a stable input log revision, ruleset version, and master-data snapshot where used. Keep prior runs when entries, decisions, or rules change.
6. Implement contest-level `auto_recalculate_on_upload`: trigger only after an accepted new log is committed; do not trigger for rejected uploads. Make retries safe and expose failed/in-progress runs.
7. For master-data-dependent rules, use the dataset versions pinned to the contest by the contest-start validity check. Record every selected dataset/version reference on each score run; never substitute the latest active version. Report and block scoring when any required dataset lacks a version valid at contest start.

**Exit criteria:** identical input revisions, ruleset versions, and contest-start master-data version sets reproduce identical results; all score fields are integers; each QSO's credit/status and every score component can be explained; automatic recalculation follows the per-contest setting and is safe to retry.

### Phase 8 — Result generation and public frontend

**Depends on:** Phases 5 and 7.

1. Implement manager actions to run/re-run result generation, review unresolved items, generate result lists, and publish a selected score run.
2. Implement public unauthenticated contest discovery and result/standings pages with category, band, mode, status, and other configured grouping filters.
3. Apply publication rules to late logs, checklogs, withdrawn, reclassified, and disqualified entries; avoid exposing private contact data or internal review notes.
4. Add paginated/filterable API endpoints and matching responsive Vue tables. Include score explanations and clear status labels for data that is public.
5. Implement reproducible result exports and versioned downloadable log/result formats required by the selected initial contests.
6. Implement a shared Vue application footer on every route. List each external licensed dataset used by the application and link directly to its license or use terms; keep this inventory synchronized with enabled master-data sources.

**Exit criteria:** a published contest result is readable without login; private/unpublished contest data is not exposed; manager-only result operations are protected; displayed totals match the persisted score run and exports; every frontend page includes the dataset attribution footer and working license/terms links.

### Phase 9 — Hardening and first deployment

**Depends on:** Phases 1–8.

1. Complete security review of authentication/session/token handling, authorization, CSRF/CORS, upload validation, rate limits, error leakage, and user-submitted content rendering.
2. Verify accessible keyboard and screen-reader operation for the rule composer, upload flow, manager pages, and standings.
3. Add operational dashboards/alerts for nightly master-data syncs, uploads, score runs, failed jobs, database errors, and API health.
4. Document configuration/secrets, database backup and restore, migration/rollback process, log retention, and incident recovery.
5. Start the initial single-host stack from CLI with one API process and local SQLite storage; run nightly provisioning through the internal API timer. Test backup restoration and a full contest workflow in a staging environment before production. Keep a standalone importer command that can later be run by a K3s CronJob as a one-shot Job.
6. Publish operator and participant documentation, API reference, supported format/version list, data source/license inventory, and known limitations; verify that every licensed dataset in use appears in the footer with its license or terms link.

**Exit criteria:** staging can complete the end-to-end acceptance scenario below; backups restore successfully; critical operations have observable outcomes and recovery steps; release artifacts and configuration are reproducible.

## End-to-end release acceptance scenario

1. A global administrator provisions a contest manager account.
2. The contest manager creates a contest with UTC start/end/cutoff times, categories, a versioned ruleset, and the automatic recalculation setting.
3. The rules composer validates the configuration, displays a readable summary, and activates the contest/ruleset version.
4. An unauthenticated entrant uploads a Cabrillo log. The system creates participant/entry records without a user account and returns import feedback.
5. The backend validates and adjudicates the QSOs, applies duplicate and cross-log rules, and creates an integer-only explainable score run tied to the exact input/rules/master-data versions.
6. The per-contest recalculation setting is honored. The manager can review decisions, generate a result list, and publish it.
7. An unauthenticated visitor can view the published standings and allowed score breakdowns; private log content and internal notes remain hidden.
8. On a clean start, the API immediately invokes the master-data job because no active version exists; thereafter its nightly timer imports or checks Big CTY and configured supplemental sources. It preserves provenance, creates no duplicate version for unchanged data, and leaves active data intact if a source fails validation. At contest start, it pins the effective master-data version set used by all later scoring. A global administrator can inspect versions and safely delete only unreferenced old versions. The same importer job can run once from CLI.

## Cross-cutting verification gates

Each implementation issue must include meaningful, behavior-focused unit tests for the code it changes, including relevant boundary conditions and failure paths. Add integration/API/UI coverage where unit tests cannot establish the contract, and record test commands and outcomes in comments on the child and parent issues. Before release, verify:

- All scoring values use integer types end-to-end, including API schemas, ORM columns, expressions, exports, and UI formatting.
- UTC timestamps, cutoff boundaries, and resolved recurring schedules behave consistently at exact boundary times.
- Guest uploads, manager authorization, administrator privileges, public read access, and unpublished-data privacy have explicit coverage.
- Import/recalculation retries are idempotent; partial failures do not corrupt logs, master data, or published results.
- Ruleset/master-data/source changes do not silently alter historical score runs.
- Contest scoring uses the master-data dataset versions valid at contest start, and unchanged nightly source checks do not create duplicate versions.
- Only global administrators can manage master-data versions; deletion is rejected while a version is current or referenced by a contest, score run, QSO resolution, or other retained record.
- SQLite connections use the ORM, foreign keys are enabled, write transactions stay short, and backup/restore is proven.

## Deferred beyond the initial release

The current product documents identify live/near-live standings, multi-operator collaboration, additional logging integrations, multiple API instances, and migration of nightly scheduling to managed K3s CronJobs as later capabilities. Revisit those when usage, latency, or operational requirements justify them; the first release should retain the documented single-process, low-concurrency SQLite operating model.
