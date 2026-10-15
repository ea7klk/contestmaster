# Supported log formats

## Import

The first release accepts UTF-8 text Cabrillo files with a `.log`, `.cbr`, `.cabrillo`, or `.txt` filename suffix. The importer reads a conservative Cabrillo-style subset; it does not currently validate a declared Cabrillo version or claim complete conformance to every Cabrillo 2.0/3.0 extension. File size is limited to 5 MiB; the full multipart request is limited to 5 MiB plus 64 KiB overhead. Parsing is line-oriented and bounded at 100,000 lines, 8,192 characters per line, and 50,000 QSO records.

Contest-specific exchanges are mapped using the configured exchange schema and field order. The `CALLSIGN` and `CONTEST` headers are required exactly once, and at least one complete QSO record is required. The contest header must match the selected contest name or slug. QSO records need valid date/time, callsign, band, mode, and exchange tokens for that contest's schema. Cabrillo extensions and unknown headers are retained as source metadata where possible, but are not guaranteed to round-trip byte-for-byte in exports. Unsupported records, malformed UTF-8, ambiguous exchange token counts, and values that violate the selected contest rules are reported for correction or review.

Acceptance of a Cabrillo file does not mean the entrant's claims are adjudicated or credited. Ruleset validation, cross-log checking, duplicate selection, manual review, and publication policy are separate steps.

## Export

The public standings export currently supports deterministic `results-v1` JSON and CSV. An authorized entrant can download the exact stored original Cabrillo revision through a receipt token or a verified participant session. Generating contest-specific Cabrillo result files and additional sponsor formats is not currently supported.

Ruleset format mapping is configuration for field interpretation; it does not imply an importer exists for every listed format. Only the UTF-8 Cabrillo subset above is enabled for log upload today.
