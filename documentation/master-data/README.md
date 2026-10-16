# Master data sources and nightly refresh

Big CTY `cty.dat` is the only externally provisioned master-data dataset in the current application. It supplies callsign-prefix mappings to contest entities, CQ zones, amateur-radio ITU zones, continents, and the associated call resolution facts. The service must preserve its required copyright/license notice. It must never ingest or redistribute the ARRL DXCC list.

Master data supports facts that can be resolved from the worked callsign. The submitted log supplies QSO exchanges such as serial numbers, sections, grids, states, provinces, or contest-specific station identifiers. The contest's published rules and configured ruleset define how those values are validated and scored. Do not create a general country/area dataset as a substitute for contest-specific scoring definitions.

## Source

| Dataset | Source | Supported use | Reuse requirements |
| --- | --- | --- | --- |
| Callsign, entity, prefix, CQ-zone, amateur ITU-zone, continent, coordinate, and UTC-offset mappings | [Big CTY `cty.dat`](https://www.country-files.com/bigcty/cty.dat). The [WSJT-X user guide](https://wsjt.sourceforge.io/wsjtx-doc/wsjtx-main-2.7.0.pdf) documents deriving DXCC entity, continent, CQ-zone, and ITU-zone data from this file. | Primary operational source for callsign-based resolution. Prefix and exact-call exceptions are retained with source/version provenance. Coordinates are reference metadata and do not imply an exact station location; an exchange or contest rule may provide more specific information. | Follow the dated upstream release and checksum. Extract and retain the accompanying copyright notice. The WSJT-X repository includes a separate [`cty.dat` copyright notice](https://github.com/WSJTX/wsjtx/blob/master/cty.dat_copyright.txt); retain the notice with any permitted redistributed copy and review the upstream terms. The hosted service must not ingest the separate ARRL DXCC list. |

CQ-zone and amateur-radio ITU-zone values remain separate namespaces. CQ and contest publications govern how their rules interpret geographic facts. A callsign-derived CTY mapping is a default for resolution, not a replacement for a contest's published exceptions or a location sent in an exchange.

## Nightly refresh

The importer enables Big CTY only. It discovers the latest dated release, verifies the dated archive link, extracts `cty.dat` and its included copyright notice, validates the complete file, and imports normalized callsign-resolution data into ORM-managed, version-scoped tables.

Use `uv run contestmaster-master-data sync` or `uv run contestmaster-master-data sync-cty` for a one-shot update; both currently sync Big CTY. Use `uv run contestmaster-master-data status` to inspect active versions and recent attempts. The API checks for a CTY version on startup and runs the same importer nightly at 02:00 UTC by default. `MASTER_DATA_SCHEDULER_ENABLED` and `MASTER_DATA_NIGHTLY_HOUR_UTC` configure the single-process timer. A database uniqueness constraint prevents overlapping CTY runs across API and CLI.

The importer records the source URL, release date, retrieval time, checksum, license notice, and sync result. It validates a complete candidate before activation, preserves the last good version on failure, and stages material entity or zone changes for review. If normalized content is unchanged, record the sync outcome without creating a new version. Each contest using callsign-derived scoring facts pins the CTY version valid at its start instant; later score runs reuse that version. Scoring that does not use callsign-derived geography does not require a master-data pin.

The one-shot CLI remains the reusable entry point for a future K3s CronJob. Public availability does not imply permission to republish; follow the CTY file's applicable notice and terms.

## Contest-specific values

Do not provision generic country names, country codes, sections, states, provinces, grids, serials, or contest station identifiers as global master data unless a supported scoring rule is shown to require an independent reference dataset. These values normally come from the received log exchange or the contest's versioned ruleset. When a contest's published rules require an official list, model that list as contest-specific ruleset data or a separately approved capability; keep the contest rules authoritative.

## References

- [WSJT-X User Guide 2.7.0](https://wsjt.sourceforge.io/wsjtx-doc/wsjtx-main-2.7.0.pdf) — documents the `cty.dat` callsign-prefix lookup for entity, continent, CQ-zone, and ITU-zone values.
- [WSJT-X `cty.dat` copyright notice](https://github.com/WSJTX/wsjtx/blob/master/cty.dat_copyright.txt) — separate data-file notice to retain with permitted use.
- [Big CTY releases](https://www.country-files.com/bigcty/) — upstream files and release dates.
