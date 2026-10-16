# Contestmaster: initial product and architecture overview

This document captures an initial direction for Contestmaster, a universal engine for amateur radio contests. It is a starting point: contest rules vary, so confirm each rule against the published rules for the selected contest before implementing it.

For the ordered delivery sequence, task breakdown, and release acceptance criteria, see the [implementation plan](implementation-plan/README.md).

Operational and user guides: [operators](operations/README.md), [participants](participants/README.md), [supported file formats](formats/README.md), and [security/accessibility review](security/README.md).

## Initial feature list

### Core platform

- Create and configure contests with a name, operating start/end times, a separate log submission cutoff, supported entry categories, and a selected ruleset and version.
- Create participant and station records from contest entry details; participants can submit logs without registering for a system account.
- Record contacts (QSOs) with UTC time, callsigns, band, mode, and contest-specific exchange data.
- Validate entries and contacts against the active contest ruleset, with clear field-level feedback.
- Calculate reproducible integer-only scores, multipliers, penalties, and standings. Retain a breakdown so an organizer can explain how a result was reached.
- Let participants upload logs without a system account. Guests manage an entry with its receipt token; registered participants can use email magic links for entries associated with their verified email. Provide public contest result and standings views without login, alongside organizer views for managing contests.

### Log handling

- Add, edit, and remove contacts through the application.
- Upload logs through the participant interface and import or export them through contest-enabled Cabrillo and ADI/ADIF format adapters.
- Report malformed rows and rule violations with source-line feedback and without partially accepting an invalid log. Preserve the exact submitted source, unknown headers, and unmapped fields.
- Make upload retries idempotent per contest and content. Bound request and file sizes, sanitize filenames, and apply rate limits. Return an entry-scoped receipt token and store only its digest.
- Detect likely duplicate contacts and show how each contact was credited during scoring.

### Contest administration

- Create and configure contests with UTC start/end instants, optional periodicity, and a separate log submission cutoff. Use the graphical ruleset composer for reusable categories, bands, modes, exchange definitions, late-submission policy, and scoring rules. Global administrators maintain the shared band/mode catalog; contest managers select eligible values in their rulesets.
- Review submitted logs, run or rerun adjudication, and publish standings.
- Keep score runs tied to the exact ruleset version and input data used to produce them.
- Let contest managers review unresolved scoring items, generate result lists, and publish immutable numbered result snapshots. Public standings expose aggregate score explanations and configured entry categories, not raw QSOs or private review data.
- Track adjudication decisions and score changes for later review.
- Let global administrators review master-data versions and their effective intervals, provenance, sync outcomes, and references in a protected administration section. Permit deletion only for non-current versions not referenced by a contest or score run.

### System roles and access

The system has two privileged account roles. A participant is a contest identity, not a privileged system account, and does not need to register before submitting a log. A participant who registers and verifies an email address can request a short-lived, single-use email magic link to access only associated entries. This access never grants a global administrator or contest manager role.

- **Global administrator:** has all privileges across the system and all contests.
- **Contest manager:** can create and manage their own contests, configure those contests' rules and automatic recalculation setting, run contest result generation, and generate contest result lists. Contest managers do not have global administrator privileges.
- **Guest log submitter:** can submit a contest log without an account and use an entry-scoped receipt token to manage that entry. Store only a token hash; the contest manager controls its expiry and can close, revoke, or rotate it. The submission is associated with a participant/entry record, while its system-account submitter reference remains empty.
- **Registered participant:** can verify an email address and use a short-lived, single-use email magic link to manage only entries associated with that identity. Participant identity and entry access do not grant privileged system roles.
- **Public visitor:** can view contest results and standings in the web frontend without an account. Viewing results does not grant contest-management privileges.

Only global administrators can access master-data version management in the web application. The API must enforce the same role restriction. Global administrators can inspect version and sync history, activate validated candidate versions, and delete eligible old versions. Contest managers and public visitors cannot list, activate, or delete shared master data.

### Later capabilities

- Support additional contest formats by adding rulesets and import/export adapters rather than changing the common log workflow.
- Add live or near-live standings, multi-operator workflows, and richer log checking as requirements become clear.
- Add integrations such as external log submission or radio logging software only when a concrete interoperability need is defined.

## Initial system ruleset

The checked items in [Initial reusable rule catalog of the system](preliminary-ruleset/README.md#initial-reusable-rule-catalog-of-the-system) are adopted as Contestmaster's initial built-in reusable rule catalog. The Vue rule composer and Python ruleset interface should support these rule types from the initial implementation:

- Late-submission handling policy; UTC event dates, periodicity, and submission cutoff are contest configuration.
- Entry category dimensions and compatibility constraints.
- Declarative exchange schemas and field validators.
- QSO eligibility predicates and configurable duplicate scope.
- Integer QSO-point rules and integer-only score composition.
- Multiplier source, uniqueness scope, and eligibility.
- Bonus and penalty rules with thresholds, caps, ordering, and evidence requirements.
- Operating-time, off-time, band-change, and transmitter constraints.
- Log import/export schemas and category mapping.
- Cross-log checks, review decisions, publication, and award eligibility.
- Ruleset edition/source provenance and immutable score-run explanations.

This is the system's set of reusable rule capabilities, not one universal contest configuration. A contest manager configures the parameters and selects applicable types for each contest; the published rules for that contest govern. Each saved configuration is validated and versioned, and each score run records the exact ruleset version and explanation used.

IARU organizational regions are outside the current release: they are not a first-class master-data set, built-in contest condition, or ruleset configuration field. The active database schema and data model do not store them. Amateur-radio ITU zones remain a separate, supported contest reference and must not be conflated with IARU organizational regions. Revisit IARU-region support in the [standalone backlog issue](https://github.com/ea7klk/contestmaster/issues/77), outside the current implementation phases.

## Architecture overview

The Vue application handles contest setup, manager-authored Markdown contest descriptions, log entry, log-file selection and upload, administration, standings display, and a simple graphical rule composer for contest managers. Participants can upload logs and anyone can view contest results and standings without creating system accounts; privileged contest-management actions require authentication. Public contest details display the manager's description above a generated ruleset summary. The frontend sanitizes rendered Markdown; the summary includes category dimensions and configured choices, but can be imprecise, so the sponsor's official rules remain authoritative. The frontend sends API requests and multipart log uploads to the Python REST API. The API authenticates privileged actions, checks global administrator or contest-manager permissions, accepts eligible log submissions without an account, passes uploaded files to import adapters, applies contest domain services, and accesses SQLite only through the ORM persistence layer using ORM-managed connections and sessions. Scoring is performed by a versioned ruleset implementation behind a stable interface; the browser may provide immediate convenience checks, but the backend remains authoritative.

```mermaid
flowchart LR
    Participant[Log submitter; account optional] --> Web[Vue web application]
    Visitor[Unauthenticated results viewer] --> Web
    PrivilegedUser[Global administrator or contest manager] --> Web
    Web --> Composer[Graphical contest rule composer]
    Web -->|global-admin configuration| CatalogAdmin[Band and mode catalog administration]
    Composer -->|rule configuration| API[Python REST API]
    CatalogAdmin -->|catalog reads and protected changes| API
    Web -->|HTTPS REST / JSON and multipart log uploads| API[Python REST API]
    Web -->|public contest details, results, and standings| API
    API -->|privileged actions| Auth[Role and contest-scope authorization]
    API --> Domain[Contest domain services]
    Domain --> Validation[Log and exchange validation]
    Domain --> Rules[Versioned contest rulesets]
    Domain -->|when enabled by contest setting| Scoring[Integer scoring and adjudication]
    API --> Store[ORM persistence layer]
    API -->|before serving requests| SchemaMigration[Consolidated Alembic baseline and later revisions]
    SchemaMigration --> Store
    Store -->|ORM-managed connection and session| DB[(SQLite)]
    Store -->|catalog and rule versions| OperatingCatalog[band_catalog_items, mode_catalog_items, ruleset_versions]
    API -->|account-free log upload| Adapters[Import and export adapters]
    Adapters -->|accepted new log| Domain
    Adapters --> Formats[Cabrillo, ADI/ADIF and other log formats]
    Timer[Internal API startup and nightly scheduler] -->|invokes| MasterImport[CTY cty.dat import job]
    StackCLI[Stack CLI] -->|starts| API
    MasterCLI[Master-data CLI] -->|one-shot sync| MasterImport
    DBCLI[Database maintenance CLI] -->|offline backup, integrity check, restore| Store
    API -->|low-cardinality metrics| Prometheus[Prometheus scraper]
    Prometheus --> Dashboard[Operations dashboard and alerts]
    CTYSource[Big CTY cty.dat] --> MasterImport
    MasterImport -->|ORM-managed writes| Store
    Store --> ReferenceData[(Versioned master data)]
```

### Main boundaries

- **Vue frontend:** presents workflows, sends typed API requests, lets participants upload log files without requiring accounts, displays contest results and standings publicly without login, and provides contest management with JSON contest import, Markdown contest descriptions, and draft editing of saved rulesets as new immutable versions. Render manager-authored contest descriptions safely from Markdown source. The public details page places this description above a generated category/rules overview that may be imprecise; the official contest rules remain authoritative. The graphical composer validates and reviews contest rules. Show upload progress, import summaries, and actionable row-level errors. Render a shared footer on every route, including public and authenticated pages, listing each external licensed dataset used by the application with a direct link to its license or use terms. Keep the attribution list synchronized with enabled sources. Keep contest rules and final score calculations on the server.
- **Python REST API:** owns the external API contract, input validation, role and contest-scope authorization for privileged actions, account-free log submission, public read access to contest results and standings, and ORM-managed transaction boundaries. Use ORM-managed connections and sessions for all application database access; application code must not open direct sqlite3 connections or issue database operations outside the ORM. Publish an OpenAPI description.
- **Contest domain:** models common contest concepts and exposes services for callsign normalization, QSO validation, duplicate selection, counterpart-log matching, scoring, and adjudication. Keep pure rule checks independent of HTTP and SQLite; ORM orchestration records immutable decisions and score runs at the application boundary.
- **Rulesets:** define reusable categories, exchange interpretation, QSO eligibility predicates over contact geography, entry categories/declarations, and the station callsign, plus multipliers, penalties, and rounding rules. Contest start/end instants, periodicity, and log submission cutoff belong to contest configuration and are excluded from rulesets. The ruleset's submission rule only selects late-log handling. The API exposes a typed built-in rule catalog and a no-save validation endpoint that returns configuration errors, a readable summary, and an integer worked-score example. Configured cross-log workflow hooks control reciprocal-contact tolerances and whether missing/mismatched counterpart contacts require review. Submitted configuration never executes code. Contest managers author configuration through the graphical composer; validated versions are append-only, activation history is recorded per contest, and score runs retain their selected version.
- **Operating catalogs:** store reusable bands and modes in independent ORM-managed `band_catalog_items` and `mode_catalog_items` tables. The API exposes active values through separate resources; the global-admin page has distinct Bands and Modes sections, each with its own “Add catalog item” form. Eligibility selections persist stable keys in immutable ruleset configuration JSON; no foreign-key relationship makes historical snapshots depend on mutable catalog rows. Contest-free marks are advisory metadata shown in the composer and do not change scoring.
- **Adapters:** translate files and external formats into and out of the common domain model. The API enforces upload limits and passes file contents to import adapters. Keep format parsing separate from validation and scoring.
- **Master-data refresh:** the initial single API process invokes a reusable, idempotent Big CTY `cty.dat` import at startup if no active CTY version exists, then runs it nightly. The same job can run once from CLI and later from a K3s CronJob as a one-shot Job. It records provenance and source terms, validates complete candidate versions, then activates safe updates through ORM-managed writes. Prevent overlapping imports, expose provisioning status, keep the last valid version active on failures, and queue interpreted boundary changes for review. Scoring that depends on callsign-derived geography pins the CTY version valid at the contest's start instant. Contest-specific identifiers come from the log exchange or ruleset.
- **Master-data version governance:** CTY is the only provisioned dataset. When a contest's rules use callsign-derived facts, pin the CTY version whose effective UTC interval contains the contest start instant; keep the reference on the contest and each score run so later imports cannot change historical interpretation. An unchanged nightly check records its sync run but creates no new data version. The global-administrator-only web section lists versions, supports activation of validated candidates, and allows deletion only for non-current versions with no contest, score-run, QSO-resolution, or other retained-record references. Enforce the role check in the API and reference restrictions in the database.
- **Global administration:** the master-data version management section is visible and accessible only to global administrators. Contest managers and public visitors cannot list, activate, or delete master-data versions.
- **Initial operations:** start the stack from CLI on one host with SQLite on local storage. Run one API process so the internal timer has a single owner; keep the nightly importer independent of HTTP startup and callable as a standalone job for future K3s scheduling.
- **Observability and recovery:** expose a protected, optional Prometheus metrics endpoint with low-cardinality counters and timings. The starter scrape configuration, dashboard, and alert rules are under `ops/observability`. Use the offline `contestmaster-db` CLI for integrity checks, verified SQLite backups, and staged atomic restore; stop the API during database maintenance. See the [operations guide](operations/README.md), [security review/accessibility checklist](security/README.md), [participant guide](participants/README.md), and [supported format list](formats/README.md).
- **SQLite:** stores application state for the initial low-concurrency deployment. All application reads and writes pass through the ORM-managed persistence layer and connections. Use ORM-compatible migrations and enforce important invariants with foreign keys, unique constraints, and transactions.
- **Schema lifecycle:** the current schema is created by one consolidated Alembic baseline. API startup applies that baseline on a new database and any later pending revisions before accepting requests. Each future data-model change is a separate Alembic revision above the baseline; the baseline stays fixed. A compatibility-only archive upgrades databases stamped with the previous migration history.

### SQLite operating guidance

SQLite fits the expected low concurrency and keeps initial deployment simple. It supports multiple readers but serializes writes, so keep write transactions short and avoid holding them open during parsing, scoring, or network calls. Enable foreign key enforcement on every connection, use a busy timeout, and consider WAL mode for reader/writer overlap. Keep the database on local storage; do not use a shared network filesystem as a multi-host database. Start with one API process and no separate job queue; move long-running recalculations to a worker only if usage or response times require it. Back up the database and test restores before relying on it for contest records.

## Initial data model

The model below is a starting point. Contest ruleset configuration is authored in the visual composer, validated by the API, and saved as a versioned configuration. Privileged system roles are only for global administrators and contest managers; participant records are contest identities and do not require a privileged account. Verified participant emails support short-lived, single-use magic-link sign-in scoped to associated entries. An entry's submitter_user_id is nullable when a participant uploads a log as a guest. Guest receipt grants are scoped to one entry, manager-controlled for expiry and revocation, and store only a token hash. The exact original Cabrillo or ADI/ADIF input and import metadata are retained with each immutable entry revision; normalized station and QSO values use child rows. A unique contest-scoped idempotency digest points to each accepted request. Preserve submitted values when normalization is needed for matching or scoring. CTY is currently the only provisioned master-data dataset; a contest pins its CTY version at the start instant only when its rules use callsign-derived facts, and dependent score runs retain that reference.

The active ORM schema and migration baseline contain no IARU-region table, entity assignment, or IARU-region-to-zone mapping. Contest ruleset configuration has no built-in IARU-region condition or lookup. Rule versions and activations use ORM-managed tables; the `ruleset_activations` rows append the selected version, actor, timestamp, and configuration digest without mutating its immutable definition. Bands and modes are separate ORM entities in `band_catalog_items` and `mode_catalog_items`, with distinct admin forms and distinct composer API resources. Eligibility rules store selected stable keys in immutable ruleset configuration; catalog keys cannot be renamed or deleted while referenced by saved rulesets, and deactivation removes an item from new selections without altering historical snapshots.

```mermaid
erDiagram
    SYSTEM_USER ||--o{ CONTEST : owns
    SYSTEM_USER o|--o{ ENTRY : submits
    CONTEST ||--o{ ENTRY : accepts
    PARTICIPANT ||--o{ ENTRY : identifies
    PARTICIPANT ||--o{ PARTICIPANT_EMAIL : verifies
    PARTICIPANT_EMAIL ||--o{ PARTICIPANT_MAGIC_LINK : authenticates
    PARTICIPANT_EMAIL ||--o{ PARTICIPANT_SESSION : signs_in
    CONTEST ||--o{ RULESET_VERSION : selects
    CONTEST ||--o{ RULESET_ACTIVATION : history
    RULESET_VERSION ||--o{ RULESET_ACTIVATION : activated
    SYSTEM_USER o|--o{ RULESET_ACTIVATION : activates
    CONTEST ||--o{ CONTEST_MASTER_DATA_VERSION : pins
    MASTER_DATA_VERSION ||--o{ CONTEST_MASTER_DATA_VERSION : selected_for
    ENTRY ||--o{ ENTRY_REVISION : receives
    ENTRY_REVISION ||--o{ STATION : uses
    ENTRY_REVISION ||--o{ QSO : records
    QSO ||--o{ QSO_DECISION : receives
    ENTRY ||--o{ SCORE_RUN : has
    CONTEST ||--o{ RESULT_PUBLICATION : publishes
    RESULT_PUBLICATION ||--o{ RESULT_PUBLICATION_ENTRY : snapshots
    ENTRY ||--o{ RESULT_PUBLICATION_ENTRY : represents
    SCORE_RUN ||--o{ RESULT_PUBLICATION_ENTRY : selected_run
    ENTRY ||--o{ ENTRY_ACCESS_GRANT : grants
    CONTEST ||--o{ LOG_SUBMISSION_REQUEST : deduplicates
    ENTRY ||--o{ LOG_SUBMISSION_REQUEST : identifies
    ENTRY_REVISION ||--o{ SCORE_RUN : scores
    RULESET_VERSION ||--o{ SCORE_RUN : evaluates
    SCORE_RUN ||--o{ SCORE_RUN_MASTER_DATA_VERSION : records
    MASTER_DATA_VERSION ||--o{ SCORE_RUN_MASTER_DATA_VERSION : used_by
    SCORE_RUN ||--o{ QSO_SCORE : explains
    QSO ||--o{ QSO_SCORE : credited_in
    CONTEST_ENTITY o|--o{ QSO : resolves
    CQ_ZONE o|--o{ QSO : resolves
    ITU_ZONE o|--o{ QSO : resolves
    CONTEST ||--o{ ADMIN_NOTE : contains
    SYSTEM_USER o|--o{ AUDIT_EVENT : performs
    SYSTEM_USER o|--o{ ADMIN_NOTE : writes

    SYSTEM_USER {
        integer id PK
        text username UK
        text role
    }
    CONTEST {
        integer id PK
        integer owner_user_id FK
        text name
        text description "nullable Markdown source"
        text starts_at_utc
        text ends_at_utc
        json periodicity
        text log_submission_cutoff_at_utc
        text status
        integer ruleset_version_id FK
        integer auto_recalculate_on_upload
    }
    CONTEST_MASTER_DATA_VERSION {
        integer id PK
        integer contest_id FK
        text dataset_key
        integer master_data_version_id FK
        text pinned_at_utc
    }
    PARTICIPANT {
        integer id PK
        text display_name
        text callsign_submitted
        text callsign_normalized
    }
    PARTICIPANT_EMAIL {
        integer id PK
        integer participant_id FK
        text email_normalized UK
        text verified_at_utc
    }
    PARTICIPANT_SESSION {
        integer id PK
        integer participant_email_id FK
        text token_hash UK
        text csrf_token_hash
        text created_at_utc
        text expires_at_utc
        text revoked_at_utc
    }
    PARTICIPANT_MAGIC_LINK {
        integer id PK
        integer participant_email_id FK
        text token_hash UK
        text created_at_utc
        text expires_at_utc
        text consumed_at_utc
    }
    RULESET_VERSION {
        integer id PK
        text ruleset_key
        text version
        text source_url
        text source_edition
        text rule_type_keys_json
        text configuration_json
    }
    BAND_CATALOG_ITEM {
        integer id PK
        text key
        text label
        text description
        text frequency_range
        integer sort_order
        integer is_active
        integer contest_free
    }
    MODE_CATALOG_ITEM {
        integer id PK
        text key
        text label
        text description
        integer sort_order
        integer is_active
    }
    RULESET_ACTIVATION {
        integer id PK
        integer contest_id FK
        integer ruleset_version_id FK
        integer activated_by_user_id FK
        text configuration_sha256
        text activated_at_utc
    }
    ENTRY {
        integer id PK
        integer contest_id FK
        integer participant_id FK
        integer submitter_user_id FK
        text category_values_json
        integer is_late
        text submitted_at_utc
        text status
    }
    ENTRY_REVISION {
        integer id PK
        integer entry_id FK
        integer revision_number
        text input_format
        text storage_key
        text original_content
        text import_metadata_json
        text content_sha256
        integer received_by_participant_email_id FK
        text received_via
        text submitted_at_utc
        text received_at_utc
    }
    ENTRY_ACCESS_GRANT {
        integer id PK
        integer entry_id FK
        text token_hash UK
        text created_at_utc
        text expires_at_utc
        text revoked_at_utc
    }
    LOG_SUBMISSION_REQUEST {
        integer id PK
        integer contest_id FK
        text key_sha256
        text content_sha256
        integer entry_id FK
        text created_at_utc
    }
    STATION {
        integer id PK
        integer entry_revision_id FK
        text callsign_submitted
        text callsign_normalized
        text station_configuration_json
    }
    QSO {
        integer id PK
        integer entry_revision_id FK
        text occurred_at_utc
        text callsign_submitted
        text callsign_normalized
        text band
        text mode
        text exchange_sent_submitted_json
        text exchange_sent_normalized_json
        text exchange_received_submitted_json
        text exchange_received_normalized_json
        integer resolved_master_data_version_id FK
        integer worked_entity_id FK
        integer worked_cq_zone_id FK
        integer worked_itu_zone_id FK
    }
    QSO_DECISION {
        integer id PK
        integer qso_id FK
        integer reviewer_user_id FK
        integer supersedes_decision_id FK
        text status
        text source
        text reason_code
        text reason
        text evidence_json
        text created_at_utc
    }
    SCORE_RUN {
        integer id PK
        integer entry_id FK
        integer entry_revision_id FK
        integer ruleset_version_id FK
        text input_digest
        text ruleset_snapshot_json
        text master_data_snapshot_json
        text explanation_json
        text status
        text created_at_utc
        integer claimed_points
        integer points
        integer multiplier_count
        integer bonus_points
        integer penalty_points
        integer final_score
        integer adjudicated_score
    }
    RESULT_PUBLICATION {
        integer id PK
        integer contest_id FK
        integer publication_number
        text source_digest
        integer entry_count
        integer withheld_count
        integer published_by_user_id FK
        text published_at_utc
        integer is_sealed
    }
    RESULT_PUBLICATION_ENTRY {
        integer id PK
        integer publication_id FK
        integer entry_id FK
        integer score_run_id FK
        text callsign
        text category_values_json
        text status
        integer score
        integer points
        integer multiplier_count
        integer bonus_points
        integer penalty_points
        integer qso_count
        integer credited_qso_count
        integer placement
        text explanation_json
    }
    SCORE_RUN_MASTER_DATA_VERSION {
        integer id PK
        integer score_run_id FK
        text dataset_key
        integer master_data_version_id FK
    }
    QSO_SCORE {
        integer id PK
        integer score_run_id FK
        integer qso_id FK
        integer entry_revision_id FK
        integer credited
        text status
        integer points
        integer bonus_points
        text reason_codes_json
        text multiplier_keys_json
        text explanation
    }
    ADMIN_NOTE {
        integer id PK
        integer contest_id FK
        integer entry_id FK
        integer author_user_id FK
        text body
    }
    AUDIT_EVENT {
        integer id PK
        integer actor_user_id FK
        text action
        text target_type
        text target_id
        text occurred_at_utc
    }
```

`CONTEST.description` is an existing nullable text column. It stores the manager-authored Markdown source; rendering and HTML sanitization happen in the frontend, so Markdown support required no schema migration. This authored description is separate from the ruleset-derived “Contest rules at a glance” overview. The overview expands category dimensions, required/optional selections, choices, declaration markings, and mutually exclusive dimensions, but may be imprecise and does not replace the sponsor's official published rules.

`BAND_CATALOG_ITEM` and `MODE_CATALOG_ITEM` are independent global-admin-managed reference tables. Both have stable keys, labels, descriptions, sort order, and active state. Bands additionally store frequency reference text and the advisory contest-free mark. The active band catalog ends at 10 GHz and marks 2200 m, 630 m, 60 m, 30 m, 17 m, and 12 m as no-contest advisory bands; higher-frequency legacy catalog keys remain inactive for compatibility with saved rulesets. The consolidated Alembic baseline creates and seeds these tables. `RULESET_VERSION.configuration_json` stores selected band/mode keys in the immutable ruleset snapshot. This intentional JSON reference avoids making historical versions depend on mutable catalog rows; referenced keys cannot be renamed or deleted, and deactivation does not rewrite saved rulesets.

### Data and scoring conventions

- Store contest start, end, and log submission cutoff as separate UTC timestamps with a documented, consistent precision. The cutoff is independent of the operating end time and governs acceptance of new log submissions. SQLite can store them as ISO 8601 text; convert to local time at display or file-format boundaries.
- Use integer values only for points, bonuses, penalties, multipliers, intermediate score values, and final scores. Never use floating-point or decimal values for scoring. If a published rule yields a fractional result, apply its specified rounding rule and keep the stored result an integer.
- Keep each score run immutable or auditable: a changed log or ruleset should produce a new run, not silently rewrite the prior explanation.
- A manager publication copies selected latest completed runs into a sealed, immutable snapshot with a numbered publication and source digest. Re-publication appends a snapshot. Withdrawn entries are excluded; late, checklog, and unresolved entries are withheld by default; reclassified and disqualified entries are included with status labels by default. Disqualified entries have zero score and no placement. A `result_publication` ruleset hook may explicitly change these inclusion booleans.
- Public standings and `results-v1` JSON/CSV exports are generated from publication snapshots, never from mutable current score-run state. Public responses include aggregate score explanations and configured categories only; original logs remain receipt/participant/manager scoped.
- Keep ruleset versions, accepted entry revisions, station/QSO input, adjudication decisions, and audit events append-only. A completed score run and its per-QSO explanations are immutable at the database level; corrections create a new revision or score run. Private staff notes can be edited, with material administrative actions recorded in the audit trail.
- Honor the contest's auto_recalculate_on_upload setting after a new log has been accepted and imported. A rejected or malformed upload must not trigger automatic result generation.
- Treat JSON configuration and exchange payloads as untrusted input. Validate their schema and preserve the original submitted exchange when a normalized interpretation is stored.
- Add indexes based on actual query needs, especially for contacts by entry, time, band, and callsign. Keep uniqueness rules contest-aware; a duplicate definition can vary by ruleset.

### Retention and visibility defaults

Treat these as product defaults to confirm for the deployment's jurisdiction and contest requirements. Restrict access in API serialization as well as the UI; hiding a link is not authorization.

- Keep original uploaded log files private. Entrants can access their own entry through its receipt grant or verified participant access; the contest's managers and global administrators can access it for adjudication. Public result pages never expose original files, raw QSO records, participant email addresses, receipt-token hashes, or private staff notes.
- Retain the original uploaded file until 12 months after the result is final, then remove the blob unless an appeal, dispute, or legal hold is active. Keep the revision metadata and cryptographic digest for provenance after blob deletion; do not overwrite an earlier revision when a replacement is submitted.
- Retain parsed QSO input, adjudication decisions, ruleset/master-data snapshots, and score explanations for five years after final results to support reproducibility and appeals. Mark this as a configurable deployment policy; a legal hold extends retention.
- Keep verified participant email addresses and account recovery/access records private. Expire and remove consumed or expired magic-link token hashes after 30 days. Revoke entry grants at closure or expiry and retain only non-secret audit metadata about that action.
- Limit administrative notes to authorized staff for the associated contest. Retain audit events for three years; audit metadata must not contain credentials, bearer tokens, raw log data, email bodies, or unnecessary personal data.
- Provide an authorized deletion/anonymization workflow after applicable retention ends. Preserve contest result records and non-identifying score evidence where required, and record the deletion action without copying the deleted personal data into the audit event.

## Geographic and callsign master data

Designate permitted Big CTY `cty.dat` data as the only externally provisioned master-data source for nightly imports and callsign resolution, preserving its applicable license notice. Its callsign mappings cover prefixes, DXCC entities, continents, CQ zones, and amateur-radio ITU zones. The hosted service will never ingest or redistribute the ARRL DXCC list; contest-published rules remain authoritative for scoring definitions and exceptions. Keep CQ zones and amateur ITU zones distinct. Contest-specific sections, states, provinces, grids, serials, and station identifiers come from submitted exchanges and configured rulesets.

Use normalized ORM tables and effective-dated assignments. An entity can span more than one zone, and a zone can include parts of several entities, so zone membership must not be a single zone column on the entity. A logged callsign, portable prefix, operating location, or a contest's own definitions may be needed to resolve the right zone. Keep international prefix-block allocation separate from the prefix rules a contest uses to parse a callsign.

The [master-data guide](master-data/README.md) identifies the CTY source, update approach, and reuse limitations. The nightly importer saves retrieval metadata and checksums, validates a complete candidate dataset before activation, and retains prior versions. A timeout, parse error, empty response, or incomplete download must leave the last valid data active. Public availability does not grant permission to redistribute a dataset: follow CTY's applicable notice and terms.

```mermaid
erDiagram
    MASTER_DATA_SOURCE ||--o{ MASTER_DATA_SYNC_RUN : supplies
    MASTER_DATA_SYNC_RUN ||--o{ MASTER_DATA_VERSION : produces
    CONTEST ||--o{ CONTEST_MASTER_DATA_VERSION : pins
    CONTEST_MASTER_DATA_VERSION }o--|| MASTER_DATA_VERSION : selects
    SCORE_RUN ||--o{ SCORE_RUN_MASTER_DATA_VERSION : records
    SCORE_RUN_MASTER_DATA_VERSION }o--|| MASTER_DATA_VERSION : uses
    MASTER_DATA_VERSION ||--o{ CQ_ZONE : versions
    MASTER_DATA_VERSION ||--o{ ITU_ZONE : versions
    MASTER_DATA_VERSION ||--o{ CONTEST_ENTITY : versions
    MASTER_DATA_VERSION ||--o{ CALLSIGN_PREFIX : versions
    CONTEST_ENTITY ||--o{ ENTITY_CQ_ZONE_ASSIGNMENT : assigned
    CQ_ZONE ||--o{ ENTITY_CQ_ZONE_ASSIGNMENT : contains
    CONTEST_ENTITY ||--o{ ENTITY_ITU_ZONE_ASSIGNMENT : assigned
    ITU_ZONE ||--o{ ENTITY_ITU_ZONE_ASSIGNMENT : contains
    CONTEST_ENTITY ||--o{ PREFIX_ENTITY_ASSIGNMENT : associated
    CALLSIGN_PREFIX ||--o{ PREFIX_ENTITY_ASSIGNMENT : allocated
    CALLSIGN_PREFIX ||--o{ PREFIX_CQ_ZONE_ASSIGNMENT : maps
    CQ_ZONE ||--o{ PREFIX_CQ_ZONE_ASSIGNMENT : resolves
    CALLSIGN_PREFIX ||--o{ PREFIX_ITU_ZONE_ASSIGNMENT : maps
    ITU_ZONE ||--o{ PREFIX_ITU_ZONE_ASSIGNMENT : resolves

    MASTER_DATA_SOURCE {
        integer id PK
        text source_key UK
        text name
        text canonical_url
        integer source_priority
        text authority_role
        text use_terms_url
        text license_notice
        integer enabled
        text created_at_utc
        text updated_at_utc
    }
    MASTER_DATA_SYNC_RUN {
        integer id PK
        integer source_id FK
        text dataset_key
        text started_at_utc
        text finished_at_utc
        text retrieved_at_utc
        text source_url
        text source_release
        text checksum
        text parser_version
        text record_counts_json
        text status
        integer change_detected
        text error_summary
    }
    MASTER_DATA_VERSION {
        integer id PK
        integer sync_run_id FK
        text dataset_key
        text source_release
        text retrieved_at_utc
        text valid_from_utc
        text valid_to_utc
        text checksum
        text activated_at_utc
        text status
        text created_at_utc
    }
    CQ_ZONE {
        integer id PK
        integer version_id FK
        text code
        text name
        text definition
    }
    ITU_ZONE {
        integer id PK
        integer version_id FK
        text code
        text name
        text definition
    }
    CONTEST_ENTITY {
        integer id PK
        integer version_id FK
        text namespace
        text authority_code
        text name
        text entity_type "sovereign_country, territory, award_entity, contest_entity, other"
        text continent
        real latitude
        real longitude
        real utc_offset
        text valid_from
        text valid_to
    }
    CALLSIGN_PREFIX {
        integer id PK
        integer version_id FK
        text prefix_pattern
        text allocation_type
        text continent_override
        real latitude_override
        real longitude_override
        real utc_offset_override
        text valid_from
        text valid_to
    }
    PREFIX_ENTITY_ASSIGNMENT {
        integer id PK
        integer entity_id FK
        integer prefix_id FK
        integer version_id FK
        text valid_from
        text valid_to
        text source_note
    }
    PREFIX_CQ_ZONE_ASSIGNMENT {
        integer id PK
        integer prefix_id FK
        integer cq_zone_id FK
        integer version_id FK
        text valid_from
        text valid_to
        text override_note
    }
    PREFIX_ITU_ZONE_ASSIGNMENT {
        integer id PK
        integer prefix_id FK
        integer itu_zone_id FK
        integer version_id FK
        text valid_from
        text valid_to
        text override_note
    }
    ENTITY_CQ_ZONE_ASSIGNMENT {
        integer entity_id PK,FK
        integer cq_zone_id PK,FK
        integer version_id FK
        text valid_from
        text valid_to
        text boundary_note
    }
    ENTITY_ITU_ZONE_ASSIGNMENT {
        integer entity_id PK,FK
        integer itu_zone_id PK,FK
        integer version_id FK
        text valid_from
        text valid_to
        text boundary_note
    }
```

The diagram is logical rather than a required physical schema. Big CTY is the only enabled source, stored under dataset key `cty`; it supplies callsign-derived entity, prefix, CQ-zone, ITU-zone, continent, and geographic reference facts, while contest publications govern how those facts are interpreted. Source and version records retain provenance, license/use terms, checksums, and effective intervals. The source priority and authority role fields describe source metadata; they do not arbitrate between feeds in this CTY-only setup. `namespace` and `entity_type` distinguish award-defined entities (such as DXCC) from contest-defined entities. The diagram names the current ORM tables, including `prefix_entity_assignments`, `entity_cq_zone_assignments`, `entity_itu_zone_assignments`, `prefix_cq_zone_assignments`, and `prefix_itu_zone_assignments`; they carry effective dates and source/version provenance. Prefix assignments support more than one allocation target and time period. Prefix-based zone mappings from Big CTY support callsign resolution; they do not replace a contest's published exceptions or a location supplied in a QSO exchange. Preserve old versions referenced by historical logs or score runs. All tables and sync operations use the Python ORM and ORM-managed transactions. Contest-specific station and exchange identifiers belong in each contest's ruleset.

On startup, import Big CTY if no active CTY version exists; then check it nightly. Expose whether initial provisioning is pending, active, or failed. Rules that use callsign-derived facts require a CTY version valid at contest start, and scoring must block if no version covers that instant. Validate a complete CTY candidate before activation, preserve the last good version on failure, and stage material changes for review. The dated release and checksum identify upstream changes; unchanged normalized content records a successful sync without creating a new version or changing effective intervals. A global administrator can inspect source/run/version metadata and activate validated candidates in the web UI. Deletion is allowed only for a non-current version with no contest, score-run, QSO-resolution, or other retained-record references; keep versions needed for historical result reproduction.
