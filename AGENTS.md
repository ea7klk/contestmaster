# AGENTS.md

## Project purpose

Build a universal engine for amateur radio contest operation. Keep contest-specific rules configurable or isolated so that adding a contest does not require rewriting the core log, scoring, or standings flows. Treat published contest rules as the source of truth; record which ruleset and version produced each result.

## Architecture

- Keep the Vue frontend, Python REST API, and contest domain logic in clear layers. The API is the source of truth for persisted state and authoritative scoring.
- Keep domain rules independent of HTTP handlers, database models, and Vue components. Use explicit services or modules for log validation, scoring, multipliers, and standings.
- Model common concepts such as contests, participants, stations, contacts (QSOs), exchanges, bands, modes, logs, and results without assuming every contest uses every field or the same rules.
- Implement contest-specific behavior behind a documented ruleset interface or configuration. Avoid scattered contest-name conditionals and hidden defaults.
- Keep amateur bands and operating modes in separate ORM entities and tables that only global administrators can change. Give each a distinct management section and API resource; each admin section has its own “Add catalog item” workflow. Eligibility rules store stable catalog keys; inactive entries cannot be selected for new rulesets. A contest-free mark is an advisory notice and must not silently alter eligibility or scoring.
- Keep ruleset schedule instants and recurrence calculations in UTC. Do not add local-time or daylight-saving fold settings to contest schedules.
- Let contest managers create and edit ruleset configuration with a simple graphical rule composer in the Vue frontend. Validate the composed configuration on the backend, version it, and keep executable contest logic behind the ruleset interface.
- Treat the checked “Initial reusable rule catalog of the system” in `documentation/preliminary-ruleset/README.md` as the initial baseline of rule types supported by Contestmaster. Distinguish this built-in capability catalog from each contest's configured and versioned ruleset values.
- Prefer small, composable changes that preserve existing public API and data compatibility. Document intentional breaking changes and migrations.

## Contest data and scoring

- Store contact timestamps in UTC and make contest start/end boundaries and time precision explicit. Convert to local time only for display or import/export formats that require it.
- Model each contest's log submission cutoff separately from its start and end times. Validate new log submissions against the cutoff in UTC; do not assume contest end time is the submission deadline.
- Preserve submitted values alongside normalized values when normalization could lose information. Normalize callsigns and other identifiers consistently, but do not silently rewrite the participant's original submission.
- Validate QSOs and exchanges with contest-aware rules. Make duplicate detection, band/mode constraints, multipliers, penalties, and disqualification rules explicit and testable.
- Make scoring deterministic and auditable: given the same log data and ruleset version, results must be reproducible. Keep enough detail to explain score totals, claimed and credited contacts, multipliers, and penalties.
- Publish results only as immutable, numbered snapshots of explicitly selected latest completed score runs. A later publication appends a snapshot; it must not mutate an earlier publication. Record a deterministic digest of the selected source runs.
- Keep publication policy explicit for late, checklog, withdrawn, unresolved, reclassified, and disqualified entries. Default to withholding late/checklog/unresolved and withdrawn entries; expose reclassified/disqualified status clearly, with disqualified entries scoring zero and receiving no placement. Allow only validated declarative ruleset options to override inclusion policy.
- Make result recalculation a per-contest setting controlled by the contest manager. When enabled, a newly accepted log upload triggers result generation for that contest; failed or rejected uploads do not.
- Treat imports and exports, including common interchange formats such as Cabrillo, as boundary adapters. Validate malformed input, report actionable row-level errors, and avoid losing fields that the engine does not interpret.
- Use database constraints and transactions for invariants such as unique identifiers and atomic log/result updates. Represent points, bonuses, penalties, multipliers, intermediate scores, and final scores with integer values only; never use floating-point or decimal values for scoring. If a contest rule produces a fractional result, apply its specified rounding rule and keep the resulting scoring value an integer.
- Store reusable geographic and callsign reference data in ORM-managed master tables for CQ zones, amateur-radio ITU zones, contest entities/countries, and prefixes. Keep these concepts distinct; an award entity is not necessarily a sovereign country.
- Do not add IARU organizational-region master data, built-in contest conditions, or ruleset configuration fields to the current phased implementation. Revisit only under the standalone [backlog issue](https://github.com/ea7klk/contestmaster/issues/77); keep amateur-radio ITU zones separate.
- Keep required master-data provisioning limited to datasets consumed by supported scoring and workflows; each contest's published rules remain authoritative.
- Designate Big CTY `cty.dat` as the primary operational source for nightly master-data imports and callsign resolution, including contest entity, prefix, CQ-zone, and ITU-zone mappings. Use field-specific public authority sources to validate it and supply data it does not contain, such as country/area identifiers. Keep the UNGEGN WGN country reference and UNSD M49 country-or-area list in separate effective-dated dataset versions; the M49 adapter stores only published names and numeric codes as-is. Contest-published rules remain authoritative for adjudication.
- Never download, ingest, copy, or redistribute the ARRL DXCC list in the hosted service. Use permitted Big CTY operational mappings with their license notice and contest-published rules for contest scoring; do not treat ADIF enumerations as a licensing workaround.
- Refresh enabled master-data sources nightly through an observable, retryable import job. Record source URL, source/version date, retrieval time, checksum, license/use terms, and sync status. Preserve effective dates and historical versions so existing contest results remain reproducible.
- Give every master-data dataset version an explicit UTC effective interval `[valid_from, valid_to)`. For a contest, pin the version of each required dataset whose interval contains the contest start instant; use that same pinned set for all later score runs. Never substitute the latest active version when scoring a historical contest, and block dependent scoring if no version covers the contest start.
- Compare normalized dataset content before version creation. A nightly run with no content changes records its sync outcome but must not create a new master-data version or alter effective intervals.
- Restrict master-data version management in the web application and API to global administrators. Global administrators may activate validated candidates; activation starts a new effective interval and must not alter versions already pinned to contests. Allow deletion only for non-current versions with no contest, score-run, QSO-resolution, or other retained-record references; enforce role checks in the API and deletion guards server-side and preserve versions needed by historical results.
- Keep import logic independent from the scheduler. Initially expose the master-data importer as an idempotent one-shot CLI job and invoke it nightly from an internal timer owned by the single API process; on startup, trigger an immediate import if no active master-data version exists. Prevent overlapping runs, expose provisioning status, and make failures observable. Do not score calls that require master data until each required dataset has a version valid at the contest start instant and that version set is pinned to the contest. Start the stack from CLI on one host. Preserve the same job entry point for a future K3s CronJob that creates one-shot Jobs.
- Never replace valid master data with an empty or partial response. Validate imports before activation, retain the last good version on failure, and stage ambiguous or materially changed source data for review. Public availability does not imply permission to republish; enable feeds only when their terms allow the intended use or permission has been obtained.
- Project decision: use United Nations Statistics Division M49 country/area names and numeric codes as published, without modifying those values or creating derived M49 geographic classifications. Credit the M49 standard in the shared frontend footer, explain that its values are used as published, and link to both the official M49 source and UN website terms. Keep M49 distinct from contest award entities and contest scoring definitions.

## Python REST API

- Follow the repository's chosen Python framework and formatter once established. Use type hints, clear module boundaries, and focused request/response schemas.
- Create and use the project-local Python virtual environment (`.venv`) managed by the checked-in `uv.lock`; do not install application or development dependencies globally. Use the Python version recorded in `.python-version`.
- Developers may install local toolchain managers required for project work (for example, `uv` in the user-local bin directory and nvm under the user's home directory); do not require a globally installed project toolchain.
- Use the Node version recorded in `.nvmrc`. nvm is the recommended per-user Node version manager; document a direct Node.js installation as an alternative.
- Keep HTTP handlers thin. Put domain validation and scoring in reusable services, and return consistent error responses with useful field-level details.
- Enforce request-body size limits even when a client omits `Content-Length`; test both declared and streamed/chunked oversized request bodies.
- Publish and maintain an OpenAPI schema. Use explicit API versioning for breaking changes; paginate collection endpoints and define stable sorting and filtering behavior.
- Validate all client input on the server. Enforce authentication and authorization at the API boundary, including contest roles and ownership checks; never rely on frontend-only access control.
- Use only two privileged system roles: global administrators, who have all system privileges, and contest managers, who can create and manage their own contests, configure those contests' rules, run result generation, and generate contest result lists. Keep contest-manager access scoped to contests they own.
- Do not require a system account for participants to submit logs. Keep participant identity separate from privileged system accounts and allow guest log submissions.
- Accept bounded UTF-8 Cabrillo uploads through the public API. Parse and validate before opening the persistence transaction, reject invalid files as a whole with source-line errors, and preserve the original input and unrecognized source values for review.
- Make upload retries idempotent per contest and content. Hash receipt tokens in persistence; configure a stable production `ENTRY_RECEIPT_SECRET` of at least 32 random bytes so exact retries recover the same receipt without storing the token in plaintext. Never include idempotency keys or receipt tokens in logs.
- Append an immutable entry revision for every accepted resubmission or contact correction. Keep QSO rows attached to their input revision and authorize guest access with a live entry-scoped receipt or a verified participant session limited to associated entries.
- Record the access channel and associated verified participant identity on revisions where available, while never persisting session or receipt tokens.
- Make contest results and standings viewable in the Vue frontend without authentication. Keep result generation and contest-management actions protected by the appropriate privileged role.
- Build public standings and result exports only from published snapshots. Expose aggregate score explanations and configured public categories; never expose raw QSOs, original log files, participant contact data, receipt secrets, or internal review notes.
- Use a Python ORM for all application database access, including connection and session lifecycle; do not open direct sqlite3 connections or issue database operations outside the ORM. Keep ORM models and queries behind a persistence layer so domain services remain independent of storage. Use ORM-managed transactions for multi-step writes and make retryable operations safe where practical, such as with idempotency keys for log submission.
- Keep secrets and credentials out of source, logs, and API responses. Configure allowed origins, secure cookies or tokens, rate limits, and request size limits deliberately.

## Vue frontend

- Use Vue components for presentation and composition; keep contest rules and authoritative score calculations on the backend.
- Keep API calls in a shared client layer with typed request/response models, consistent error handling, and cancellation for stale requests.
- Render a shared site footer on every frontend route, including public, upload, sign-in, and administration pages. Identify each external licensed dataset used by the application and link its label directly to the applicable license or use terms. Keep the attribution inventory synchronized with enabled master-data sources, and make the links accessible by keyboard and assistive technology.
- The footer must identify M49 separately from the UNGEGN WGN API: M49 numeric codes are used as published, without modification or derived geographic classifications, and the attribution links to the M49 standard and UN website terms.
- Support log-file selection and upload through the shared API client. Show upload progress, import summaries, and actionable row-level errors; treat frontend checks as convenience and validate file contents, size, and format on the backend.
- Represent loading, empty, success, validation-error, and server-error states explicitly. Preserve user input when a save fails and explain how to fix field errors.
- Keep automated axe checks for core routes in the frontend test suite; document real-browser keyboard, contrast, and screen-reader checks and clearly distinguish combinations that were not manually tested.
- Build accessible forms and tables: labels, keyboard operation, semantic markup, visible focus, and status announcements for asynchronous updates.
- Keep contest, log, and standings views responsive and usable with large result sets. Prefer server-side filtering, sorting, and pagination when data grows.
- Show public upcoming and currently running contests in a distinct home-page section using the public API. Display UTC start/end times, keep unpublished contests private, and remove a contest when its end instant is reached. Each item should link to public details; the main account-free log-submission action stays prominent.
- Keep the labelled hamburger menu visible and left-aligned at every screen width. It controls a collapsed navigation panel and must preserve keyboard access, focus behavior, and role-based links.
- Avoid duplicating backend rules in the browser. Frontend checks may improve feedback, but the server remains authoritative.

## Security, privacy, and operations

- Collect only the personal and station data the feature needs. Define visibility and retention for logs, participant details, and adjudication notes.
- Escape and safely render imported or user-submitted content. Treat uploaded logs and filenames as untrusted input; enforce size and format limits.
- Use structured logs with request or correlation IDs, while excluding credentials, tokens, and unnecessary personal data.
- Provide migrations for schema changes and keep configuration explicit across development, test, and production environments.
- Make background imports, recalculations, and standings publication observable and safe to retry. Surface failures instead of silently publishing partial results.
- For the initial single-host SQLite deployment, expose backup, restore, and integrity-check operations through the ORM-backed `contestmaster-db` CLI. Perform these offline with the API stopped, validate a staged restore before replacement, and document the restore test evidence.

## Changes and documentation

- License Contestmaster's original software under AGPL-3.0-only. Keep its license and copyright notices with distributions. Third-party datasets, contest rules, and other imported materials retain their own terms; the project license does not grant rights to them.
- Before changing code, inspect the existing structure and follow established conventions.
- Update API documentation and relevant user or operator documentation when behavior changes.
- Write meaningful tests alongside implementation. Prefer behavior-focused unit tests for domain rules, parsing, scoring, validation, and state transitions; cover boundary cases and failure paths. Add integration/API/UI tests where unit tests cannot verify cross-layer behavior. Run the relevant tests and record their exact commands and outcomes; do not add tests that only restate implementation details.
- Keep changes scoped. Explain assumptions when a contest rule or product behavior is not defined; do not invent a universal rule where contest rules differ.
- Group related changes into sensible commits instead of committing each file or small edit separately. Use explicit commit subjects; add a concise multi-line body when it helps explain scope, design choices, or verification performed.

## GitHub phase tracking

- Track each phase in `documentation/implementation-plan/README.md` with one GitHub parent issue and a matching phase milestone. Create one linked GitHub sub-issue for every numbered implementation-plan item; Phase 0 decision bullets are child issues too and should reflect their already-recorded completion state.
- Keep parent and child issue bodies aligned with the implementation plan, including acceptance criteria and relevant test expectations. Use GitHub's parent/sub-issue relationship, assign every issue to its phase milestone, and keep a parent checklist of its child issues.
- Before closing a child issue, update its issue-body acceptance checklist: check each criterion only after its implementation, documentation, tests, and verification evidence are complete; leave unmet criteria unchecked and explain blockers in a comment. Verify the saved checklist has no unchecked criteria before closing. When revisiting a closed issue to correct tracking, update the body and add a comment documenting the correction.
- Record implementation work and progress in comments on both the child issue and its parent. Comment when work starts, when a material implementation or scope change occurs, and when an item completes or is blocked. Include status, relevant commit/PR and paths, tests run with outcomes, and any remaining work or blocker. Update the parent comment when phase-level progress or exit criteria change.
- Close a child only after its acceptance criteria are met and required tests pass. Close its parent and milestone only after all children are complete and the phase exit criteria are satisfied. Keep the issue comments as the progress history; do not rely only on local notes or commit messages.
