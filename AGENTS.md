# AGENTS.md

## Project purpose

Build a universal engine for amateur radio contest operation. Keep contest-specific rules configurable or isolated so that adding a contest does not require rewriting the core log, scoring, or standings flows. Treat published contest rules as the source of truth; record which ruleset and version produced each result.

## Architecture

- Keep the Vue frontend, Python REST API, and contest domain logic in clear layers. The API is the source of truth for persisted state and authoritative scoring.
- Keep domain rules independent of HTTP handlers, database models, and Vue components. Use explicit services or modules for log validation, scoring, multipliers, and standings.
- Model common concepts such as contests, participants, stations, contacts (QSOs), exchanges, bands, modes, logs, and results without assuming every contest uses every field or the same rules.
- Implement contest-specific behavior behind a documented ruleset interface or configuration. Avoid scattered contest-name conditionals and hidden defaults.
- Prefer small, composable changes that preserve existing public API and data compatibility. Document intentional breaking changes and migrations.

## Contest data and scoring

- Store contact timestamps in UTC and make contest start/end boundaries and time precision explicit. Convert to local time only for display or import/export formats that require it.
- Preserve submitted values alongside normalized values when normalization could lose information. Normalize callsigns and other identifiers consistently, but do not silently rewrite the participant's original submission.
- Validate QSOs and exchanges with contest-aware rules. Make duplicate detection, band/mode constraints, multipliers, penalties, and disqualification rules explicit and testable.
- Make scoring deterministic and auditable: given the same log data and ruleset version, results must be reproducible. Keep enough detail to explain score totals, claimed and credited contacts, multipliers, and penalties.
- Treat imports and exports, including common interchange formats such as Cabrillo, as boundary adapters. Validate malformed input, report actionable row-level errors, and avoid losing fields that the engine does not interpret.
- Use database constraints and transactions for invariants such as unique identifiers and atomic log/result updates. Avoid floating-point arithmetic for points; use integers or decimal types where fractions are part of a rule.

## Python REST API

- Follow the repository's chosen Python framework and formatter once established. Use type hints, clear module boundaries, and focused request/response schemas.
- Keep HTTP handlers thin. Put domain validation and scoring in reusable services, and return consistent error responses with useful field-level details.
- Publish and maintain an OpenAPI schema. Use explicit API versioning for breaking changes; paginate collection endpoints and define stable sorting and filtering behavior.
- Validate all client input on the server. Enforce authentication and authorization at the API boundary, including contest roles and ownership checks; never rely on frontend-only access control.
- Use database transactions for multi-step writes and make retryable operations safe where practical, such as with idempotency keys for log submission.
- Keep secrets and credentials out of source, logs, and API responses. Configure allowed origins, secure cookies or tokens, rate limits, and request size limits deliberately.

## Vue frontend

- Use Vue components for presentation and composition; keep contest rules and authoritative score calculations on the backend.
- Keep API calls in a shared client layer with typed request/response models, consistent error handling, and cancellation for stale requests.
- Represent loading, empty, success, validation-error, and server-error states explicitly. Preserve user input when a save fails and explain how to fix field errors.
- Build accessible forms and tables: labels, keyboard operation, semantic markup, visible focus, and status announcements for asynchronous updates.
- Keep contest, log, and standings views responsive and usable with large result sets. Prefer server-side filtering, sorting, and pagination when data grows.
- Avoid duplicating backend rules in the browser. Frontend checks may improve feedback, but the server remains authoritative.

## Security, privacy, and operations

- Collect only the personal and station data the feature needs. Define visibility and retention for logs, participant details, and adjudication notes.
- Escape and safely render imported or user-submitted content. Treat uploaded logs and filenames as untrusted input; enforce size and format limits.
- Use structured logs with request or correlation IDs, while excluding credentials, tokens, and unnecessary personal data.
- Provide migrations for schema changes and keep configuration explicit across development, test, and production environments.
- Make background imports, recalculations, and standings publication observable and safe to retry. Surface failures instead of silently publishing partial results.

## Changes and documentation

- Before changing code, inspect the existing structure and follow established conventions.
- Update API documentation and relevant user or operator documentation when behavior changes.
- Add or update focused tests for domain rules, API contracts, import/export behavior, and important UI flows when implementing features.
- Keep changes scoped. Explain assumptions when a contest rule or product behavior is not defined; do not invent a universal rule where contest rules differ.
