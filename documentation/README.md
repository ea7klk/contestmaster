# Contestmaster: initial product and architecture overview

This document captures an initial direction for Contestmaster, a universal engine for amateur radio contests. It is a starting point: contest rules vary, so confirm each rule against the published rules for the selected contest before implementing it.

## Initial feature list

### Core platform

- Create and configure contests with a name, schedule, supported entry categories, and a selected ruleset and version.
- Create participant and station records from contest entry details; participants can submit logs without registering for a system account.
- Record contacts (QSOs) with UTC time, callsigns, band, mode, and contest-specific exchange data.
- Validate entries and contacts against the active contest ruleset, with clear field-level feedback.
- Calculate reproducible integer-only scores, multipliers, penalties, and standings. Retain a breakdown so an organizer can explain how a result was reached.
- Let participants upload logs without a system account. Provide organizer views for managing contests and reviewing results.

### Log handling

- Add, edit, and remove contacts through the application.
- Upload logs through the participant interface and import or export them through format adapters, starting with Cabrillo where appropriate.
- Report malformed rows and rule violations without silently discarding submitted data.
- Detect likely duplicate contacts and show how each contact was credited during scoring.

### Contest administration

- Configure ruleset options, contest dates, categories, bands, modes, and exchange definitions.
- Review submitted logs, run or rerun adjudication, and publish standings.
- Keep score runs tied to the exact ruleset version and input data used to produce them.
- Track adjudication decisions and score changes for later review.

### System roles and access

The system has two privileged account roles. A participant is a contest identity, not a system account, and does not need to register before submitting a log.

- **Global administrator:** has all privileges across the system and all contests.
- **Contest manager:** can create and manage their own contests, configure those contests' rules, run contest result generation, and generate contest result lists. Contest managers do not have global administrator privileges.
- **Log submitter:** can submit a contest log without an account. The submission is associated with a participant/entry record, while its system-account submitter reference remains empty.

### Later capabilities

- Support additional contest formats by adding rulesets and import/export adapters rather than changing the common log workflow.
- Add live or near-live standings, multi-operator workflows, and richer log checking as requirements become clear.
- Add integrations such as external log submission or radio logging software only when a concrete interoperability need is defined.

## Architecture overview

The Vue application handles contest setup, log entry, log-file selection and upload, administration, and standings display. Participants can upload logs without creating system accounts; privileged contest-management actions require authentication. It sends API requests and multipart log uploads to the Python REST API. The API authenticates privileged actions, checks global administrator or contest-manager permissions, accepts eligible log submissions without an account, passes uploaded files to import adapters, applies contest domain services, and accesses SQLite only through the ORM persistence layer using ORM-managed connections and sessions. Scoring is performed by a versioned ruleset implementation behind a stable interface; the browser may provide immediate convenience checks, but the backend remains authoritative.

```mermaid
flowchart LR
    Participant[Log submitter; account optional] --> Web[Vue web application]
    PrivilegedUser[Global administrator or contest manager] --> Web
    Web -->|HTTPS REST / JSON and multipart log uploads| API[Python REST API]
    API -->|privileged actions| Auth[Role and contest-scope authorization]
    API --> Domain[Contest domain services]
    Domain --> Validation[Log and exchange validation]
    Domain --> Rules[Versioned contest rulesets]
    Domain --> Scoring[Integer scoring and adjudication]
    API --> Store[ORM persistence layer]
    Store -->|ORM-managed connection and session| DB[(SQLite)]
    API -->|account-free log upload| Adapters[Import and export adapters]
    Adapters --> Formats[Cabrillo and other log formats]
```

### Main boundaries

- **Vue frontend:** presents workflows, sends typed API requests, and lets participants select and upload log files without requiring system accounts. Show upload progress, import summaries, and actionable row-level errors. Keep contest rules and final score calculations on the server.
- **Python REST API:** owns the external API contract, input validation, role and contest-scope authorization for privileged actions, account-free log submission, and ORM-managed transaction boundaries. Use ORM-managed connections and sessions for all application database access; application code must not open direct sqlite3 connections or issue database operations outside the ORM. Publish an OpenAPI description.
- **Contest domain:** models common contest concepts and exposes services for validation, scoring, adjudication, and standings. Keep it independent of HTTP and SQLite.
- **Rulesets:** define contest-specific categories, exchange interpretation, QSO eligibility, multipliers, penalties, and rounding rules. Store the ruleset identifier and version with each contest and score run.
- **Adapters:** translate files and external formats into and out of the common domain model. The API enforces upload limits and passes file contents to import adapters. Keep format parsing separate from validation and scoring.
- **SQLite:** stores application state for the initial low-concurrency deployment. All application reads and writes pass through the ORM-managed persistence layer and connections. Use ORM-compatible migrations and enforce important invariants with foreign keys, unique constraints, and transactions.

### SQLite operating guidance

SQLite fits the expected low concurrency and keeps initial deployment simple. It supports multiple readers but serializes writes, so keep write transactions short and avoid holding them open during parsing, scoring, or network calls. Enable foreign key enforcement on every connection, use a busy timeout, and consider WAL mode for reader/writer overlap. Keep the database on local storage; do not use a shared network filesystem as a multi-host database. Start with one API deployment and no separate job queue; move long-running recalculations to a worker only if usage or response times require it. Back up the database and test restores before relying on it for contest records.

## Initial data model

The model below is a starting point. System accounts are only for global administrators and contest managers; participant records are contest identities and do not require an account. An entry's submitter_user_id is nullable when a participant uploads a log as a guest. Keep common fields relational and allow contest-specific exchanges and rule configuration to be stored as validated structured data. Preserve submitted values when normalization is needed for matching or scoring.

```mermaid
erDiagram
    SYSTEM_USER ||--o{ CONTEST : owns
    SYSTEM_USER o|--o{ ENTRY : submits
    CONTEST ||--o{ ENTRY : accepts
    PARTICIPANT ||--o{ ENTRY : identifies
    CONTEST ||--o{ RULESET_VERSION : selects
    ENTRY ||--o{ STATION : uses
    ENTRY ||--o{ QSO : records
    QSO ||--o{ QSO_DECISION : receives
    ENTRY ||--o{ SCORE_RUN : has
    RULESET_VERSION ||--o{ SCORE_RUN : evaluates
    SCORE_RUN ||--o{ QSO_SCORE : explains

    SYSTEM_USER {
        integer id PK
        text username UK
        text role
    }
    CONTEST {
        integer id PK
        integer owner_user_id FK
        text name
        text starts_at_utc
        text ends_at_utc
        text status
        integer ruleset_version_id FK
    }
    PARTICIPANT {
        integer id PK
        text display_name
        text callsign
    }
    RULESET_VERSION {
        integer id PK
        text ruleset_key
        text version
        text configuration_json
    }
    ENTRY {
        integer id PK
        integer contest_id FK
        integer participant_id FK
        integer submitter_user_id FK
        text category
        text submitted_at_utc
        text status
    }
    STATION {
        integer id PK
        integer entry_id FK
        text callsign
        text station_configuration_json
    }
    QSO {
        integer id PK
        integer entry_id FK
        text occurred_at_utc
        text callsign_submitted
        text callsign_normalized
        text band
        text mode
        text exchange_submitted_json
    }
    QSO_DECISION {
        integer id PK
        integer qso_id FK
        text status
        text reason
    }
    SCORE_RUN {
        integer id PK
        integer entry_id FK
        integer ruleset_version_id FK
        text created_at_utc
        integer points
        integer multiplier_count
        integer penalty_points
        integer final_score
    }
    QSO_SCORE {
        integer id PK
        integer score_run_id FK
        integer qso_id FK
        integer credited
        integer points
        text multiplier_keys_json
        text explanation
    }
```

### Data and scoring conventions

- Use UTC timestamps with a documented, consistent precision. SQLite can store them as ISO 8601 text; convert to local time at display or file-format boundaries.
- Use integer values only for points, bonuses, penalties, multipliers, intermediate score values, and final scores. Never use floating-point or decimal values for scoring. If a published rule yields a fractional result, apply its specified rounding rule and keep the stored result an integer.
- Keep each score run immutable or auditable: a changed log or ruleset should produce a new run, not silently rewrite the prior explanation.
- Treat JSON configuration and exchange payloads as untrusted input. Validate their schema and preserve the original submitted exchange when a normalized interpretation is stored.
- Add indexes based on actual query needs, especially for contacts by entry, time, band, and callsign. Keep uniqueness rules contest-aware; a duplicate definition can vary by ruleset.
