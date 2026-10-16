# Supported log formats

## Import

The first release accepts UTF-8 Cabrillo 2.0 and 3.0 log files with a `.log`, `.cbr`, `.cabrillo`, or `.txt` filename suffix. Versioned logs must start with `START-OF-LOG: 2.0` or `START-OF-LOG: 3.0` and end with `END-OF-LOG:`. A declared version other than 2.0 or 3.0, or a missing version after the colon, is rejected with a line-scoped error. The parser also accepts the older unversioned `START-OF-LOG` / `END-OF-LOG` markers as a compatibility extension; this does not mean that unversioned files conform to either specification. WWROF now marks v2 deprecated and recommends v3; v3 is intended to be backward compatible with v2 ([Cabrillo overview](https://wwrof.org/cabrillo/), [v3 header specification](https://wwrof.org/cabrillo/cabrillo-v3-header/), [QSO data specification](https://wwrof.org/cabrillo/cabrillo-qso-data/)).

This is version-aware support for the common header and QSO structure, not complete conformance to every sponsor-specific Cabrillo extension or template. Contest rules still define the QSO exchange columns through the ruleset's format mapping. Standard ten-field QSO records are parsed; trailing transmitter identifiers and other extra fields are preserved for review. V3 `CATEGORY-*` headers can be mapped using configured category mappings. The legacy v2 combined `CATEGORY` header is retained as an unknown header for review and is not automatically split into dimensions. The source text is retained exactly for later review or download. File size is limited to 5 MiB; the full multipart request is limited to 5 MiB plus 64 KiB overhead. Parsing is line-oriented and bounded at 100,000 lines, 8,192 characters per line, and 50,000 QSO records.

Contest-specific exchanges are mapped using the configured exchange schema and field order. The `CALLSIGN` and `CONTEST` headers are required exactly once, and at least one complete QSO record is required. The contest header must match the selected contest name or slug. QSO records need valid date/time, callsign, band, mode, and exchange tokens for that contest's schema. Cabrillo extensions and unknown headers are retained as source metadata where possible, but are not guaranteed to round-trip byte-for-byte in exports. Unsupported records, malformed UTF-8, ambiguous exchange token counts, and values that violate the selected contest rules are reported for correction or review.

Acceptance of a Cabrillo file does not mean the entrant's claims are adjudicated or credited. Ruleset validation, cross-log checking, duplicate selection, manual review, and publication policy are separate steps.

## Export

The public standings export currently supports deterministic `results-v1` JSON and CSV. An authorized entrant can download the exact stored original Cabrillo revision through a receipt token or a verified participant session. Generating contest-specific Cabrillo result files and additional sponsor formats is not currently supported.

Ruleset format mapping is configuration for field interpretation; it does not imply an importer exists for every listed format. Only the UTF-8 Cabrillo subset above is enabled for log upload today.
