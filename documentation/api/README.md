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

Public endpoints (health, published contest listings and published results) are explicitly unauthenticated. Privileged and participant operations declare authentication dependencies in the API layer and enforce ownership/role checks in services. The foundation provides the dependency boundary; the account/session implementation is planned for Phase 5. Guest log submission and entry receipt access are intentionally public/token-scoped workflows, not privileged accounts.

## Ruleset authoring

- `GET /api/v1/rulesets/catalog` returns the typed schemas, labels, and execution expectations for the built-in rule types used by the graphical composer.
- `POST /api/v1/rulesets/validate` accepts a proposed declarative ruleset but does not save or activate it. A valid response includes the normalized metadata, configured rule-type list, readable summary, and integer-only worked formula example. Invalid configurations return the standard error envelope with rule paths and messages.
- Conditions use the declared compare/all/any/not expression tree. The API rejects unknown fact paths and unsafe regular-expression features; it never evaluates submitted Python or JavaScript.
- `EligibilityRule.eligible_if` is a positive QSO predicate over configured contact geography, entry categories/declarations, exchanges, and station callsign. A contact that fails this predicate follows the rule's explicit `not_credited` or `needs_review` action.
- Domain scoring returns pending structured workflow actions (rule ID, entry/QSO scope, stage, execution mode, and validated parameters) for cross-log, adjudication, publication, and award consumers. These are handoff requests for trusted services, not dynamically loaded user code; cross-log/adjudication work remains visible as pending review until its downstream phase handles it.
- Saving and activating rulesets is a privileged contest-manager operation. Ruleset definitions are immutable versions, and every selection change is recorded in append-only contest activation history. Current API authentication enforcement is completed in Phase 5.

## Versioning

Additive, backward-compatible fields and endpoints remain in the current API version. Removing or changing field meaning, response shape, or behavior incompatibly requires a new `/api/vN` route prefix and a documented deprecation/migration period. OpenAPI is the machine-readable contract for each version.
