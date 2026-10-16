# Security review and accessible operation

## Security review findings

Phase 9 reviewed account authentication, session and participant-token handling, API role/ownership checks, CSRF/CORS, uploaded logs, request limits, rate limiting, exception handling, structured logs, and public rendering.

- Privileged sessions and participant access use protected, expiring credentials; reset and magic-link tokens are single use. Guest entry tokens are entry-scoped and persisted as digests. Audit records preserve privileged state changes.
- API routes apply server-side role and contest-ownership checks. Public result routes return published snapshots and do not include original logs, QSOs, participant email, or internal notes.
- CORS uses an explicit origin allowlist. State-changing participant-session requests require CSRF protection. Production/staging configuration rejects insecure cookies, weak/default receipt secrets, non-HTTPS origins/frontend URL, absent email delivery, and disabled scheduling.
- JSON and multipart requests have explicit size limits. Cabrillo and ADI/ADIF parsing limit line count, line length, and QSO count. Filenames are reduced to safe basenames and are not used as paths. Parsing completes before accepted data is written in a short ORM transaction.
- IP-based in-process rate limits cover authentication, magic-link, guest log, and entry-access operations. They are intentionally single-process controls, not a replacement for reverse-proxy abuse prevention or a distributed rate limiter.
- Unexpected API errors return a stable generic response. Logs avoid exception payloads and secrets; the request ID can be used to correlate safe server events. Frontend user-supplied values are rendered by Vue text interpolation, not interpreted as HTML.

### Residual risks and deployment controls

- There is no external staging environment, production deployment, penetration test, or third-party security assessment in this repository. Run those before hosting real contests.
- Process-local rate limits reset on restart and do not coordinate between workers. Keep one API process; add edge rate limits before public launch.
- A same-site deployment behind correctly configured HTTPS is assumed. Configure TLS, trusted proxy headers, host validation, request limits, and access-log redaction at the reverse proxy. Do not expose the metrics endpoint publicly.
- Email delivery security and account recovery operations depend on the selected SMTP provider and its account controls.

## Manual accessibility checklist

Automated axe checks run in jsdom for the composer, upload, manager, participant access, master-data administration, result-management, and standings views. They complement these manual checks and do not replace assistive-technology testing.

| Check | How to verify | Status for this phase |
| --- | --- | --- |
| Keyboard-only navigation | Tab and Shift+Tab through sign-in, contest composer, upload, manager, result tables, and admin pages; confirm visible focus and logical order. Activate controls with Enter/Space. | Automated DOM checks pass; manual full-browser keyboard sweep remains an operator/release check. |
| Form errors | Submit empty/invalid required fields; confirm the error text identifies the field and remains available to keyboard and screen-reader users. | Covered by component behavior/tests where present; complete the route-level manual sweep before public release. |
| Async status | Upload a valid/invalid file and trigger load/save actions; confirm busy, success, and failure announcements are exposed through semantic status/live regions. | DOM semantics checked by axe; test with a screen reader before production. |
| Tables | Navigate results and admin tables; verify header associations, action names, and row status. | Automated view checks pass; full screen-reader table review remains a release check. |
| Contrast and zoom | Inspect focus indicators, text, links, contest-free labels, and status at 200% zoom and with a contrast analyzer. | Not fully measured by jsdom; perform in a real browser. |
| Screen readers | Test current Chrome + NVDA on Windows and Safari + VoiceOver on macOS, including file-picker and upload feedback. | Not tested in this environment; do not treat as verified. |

The automated accessibility suite runs with the frontend unit tests. The jsdom canvas warning from axe's contrast analyzer means color contrast still requires a real-browser/manual check. Color is not the only indicator for contest-free operating bands; the interface also provides text and accessible state.
