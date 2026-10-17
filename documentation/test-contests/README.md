# Test contests and generated logs

These synthetic contests exercise anonymous uploads, score calculation, and ruleset behavior:

| Folder | Import package | Format | Logs |
| --- | --- | --- | ---: |
| [`cabrillo`](cabrillo/) | `contest.json` | Cabrillo 3.0 | 110 |
| [`adif`](adif/) | `contest.json` | ADI/ADIF | 56 |
| [`advanced-cabrillo`](advanced-cabrillo/) | `contest.json` | Cabrillo 3.0 | 2,500 |

Every station and contact is synthetic. The Cabrillo results sprint has featured logs with 80, 30, and 20 QSOs; all other logs contain 5 QSOs. The ADIF sprint has featured logs with 60, 20, and 10 QSOs; all other logs contain 5 QSOs. Exactly 80% of worked-call entries in these two sprints name another participant whose log contains the reciprocal QSO; the other 20% name external stations with no log in that contest. Cabrillo QSO lines put the logging station's exchange after its callsign and the correspondent's exchange after the correspondent's callsign, as shown in the [WWROF Cabrillo QSO data specification](https://wwrof.org/cabrillo/cabrillo-qso-data/). These fixtures use sequential sent serials and include the serial received from each matched correspondent; the Cabrillo ruleset requires the serial in both directions.

The results sprints now combine contact points, a 1,000-point activity bonus for entries meeting a QSO threshold, and multiple multiplier types. The resulting top three are `K0AAA`, `K0AAB`, and `K0AAC`: scores are 87,480 / 32,960 / 22,440 in the Cabrillo set and 65,720 / 22,440 / 120 in the ADIF set. The featured contact tiers and activity bonus create a wider score spread than the earlier fixtures.

The advanced Cabrillo challenge is a separate 2,500-participant package with randomized 50–250 QSO logs across ten callsign prefixes/entities. Its deterministic generator creates reciprocal contacts and serials across 20 m, 40 m, 15 m, and 10 m sessions, varies each frequency within its band's fixture range while keeping each matched pair on the same frequency, assigns explicit Cabrillo transmitter identifiers, and schedules QSOs to satisfy the operating-time, off-time, and band-change constraints. Sessions begin at 12:00, 13:30, 15:00, and 16:30 UTC. The ruleset requires at least 60 minutes between band changes and allows at most one change in any rolling 60-minute window. Its category headers use values defined by the WWROF v3 specification; entries without an overlay omit `CATEGORY-OVERLAY` because `NONE` is not a defined overlay value. It exercises category mapping, serial exchange validation, band/mode eligibility, duplicate handling, fixed and mode/band/exchange point rules, callsign/serial/mode multipliers, conditional activity bonuses, limited per-QSO point deductions and contact removal, operating-time/off-time/transmitter constraints, award and publication hooks, and a left-to-right integer score formula. Entries score without human-review findings so the generated score run can populate standings. Rules that depend on exchange fields use the configured Cabrillo QSO columns and do not add extra positional tokens beyond the configured transmitter field.

The Cabrillo and ADIF results sprints use 20 m and vary each QSO frequency from 14.000 through 14.350 MHz. The advanced Cabrillo set uses the four scheduled HF bands described above: 20 m (14.000–14.350 MHz), 40 m (7.000–7.300 MHz), 15 m (21.000–21.450 MHz), and 10 m (28.000–29.700 MHz). Matched contacts have the same frequency in both logs. Cabrillo records frequency in kHz; ADIF records it in the standard `FREQ` field in MHz and retains `BAND: 20M`. Scoring normalizes Cabrillo kHz values to their band key while preserving the original frequency for review and export.

Every Cabrillo fixture includes a synthetic `EMAIL: <callsign>@nomail.invalid` header. The reserved `.invalid` domain ensures these addresses cannot deliver mail.

The results sprint sets contain 665 Cabrillo QSO records (532 matching and 133 unmatched) and 355 ADIF records (284 matching and 71 unmatched). The advanced Cabrillo set contains 307,417 reproducible QSO records across 2,500 logs (50 minimum, 250 maximum; randomized entries average about 123 QSOs). These counts and standings are reproducible from the checked-in generators.

The contest event windows ended on **2024-09-14**. Logs uploaded after the event end are therefore marked late, even though the separate submission cutoff is **2099-12-31 23:59:59 UTC**. By default, Contestmaster withholds late entries from result publication; these synthetic-only rulesets explicitly set `include_late: true` so their completed runs can be selected in **Result list selection**. This override does not change the default policy for any other contest. The packages use new `*-results-sprint` slugs so they can be imported alongside older copies; import creates each as a draft, so a contest manager must open it before the public upload endpoint will accept logs.

## Import and open the contests

1. Sign in as a contest manager or global administrator.
2. On the contest management page, use **Import contest** and select one of the three `contest.json` packages.
3. Repeat for each test set you want to use.
4. Edit each imported contest and change its status from **Draft** to **Open**. The event dates and 2099 cutoff are already set.
5. Start the API and frontend. The upload tool can target either the API directly or the Vite frontend proxy.

These packages use dedicated slugs to avoid conflicting with older test contests. Existing contest/ruleset versions are immutable and are not updated by the files in this repository; import the packages and upload the logs to the new contests to use their fixture-only late-entry policy. Existing entries remain attached to their original contests.

## Regenerate the logs

Run from the repository root:

```sh
python documentation/test-contests/cabrillo/generate_logs.py
python documentation/test-contests/adif/generate_logs.py
python documentation/test-contests/advanced-cabrillo/generate_logs.py
```

Each generator writes the fixture files under its own `logs/` directory, replacing only files with its extension. It produces the same contents on every run.

## Upload anonymously

The shared uploader takes the app base URL as its first argument and does not need sign-in credentials:

```sh
python documentation/test-contests/upload_logs.py http://127.0.0.1:8000
```

Or use the local frontend URL, whose Vite proxy forwards `/api` requests to the API:

```sh
python documentation/test-contests/upload_logs.py http://127.0.0.1:5173
```

Upload one set only when needed:

```sh
python documentation/test-contests/upload_logs.py http://127.0.0.1:8000 --contest cabrillo
python documentation/test-contests/upload_logs.py http://127.0.0.1:8000 --contest adif
python documentation/test-contests/upload_logs.py http://127.0.0.1:8000 --contest advanced-cabrillo
```

The API does not rate-limit anonymous log creation or log-file resubmission. Request and file size limits, accepted formats, validation, and idempotency checks still apply. The uploader proceeds immediately between files, contest sets, and retry attempts. Stable content-based idempotency keys make rerunning the tool safe for exact retries. It reports entry IDs and HTTP failures but deliberately does not display or save the receipt tokens returned by the API.

The uploader logs timestamps, batch and per-file progress, accepted entry IDs, retry reasons and delays, and bounded validation details for final failures. Per-contest and overall summaries include total, accepted, failed, retry count, elapsed seconds, and average logs per minute. Logs go to standard error, leaving standard output available for command wrappers.

## Verify the fixtures

```sh
uv run pytest documentation/test-contests/test_fixtures.py
```

The checks validate all three imported JSON schemas, generation counts and reproducibility, distinct station callsigns, the 5–80 QSO limit, the exact 80/20 reciprocal-call ratio in both results sprints, Cabrillo serial matching in both directions, the increased score spread, advanced category import and scoring paths, and successful parsing by the application's Cabrillo and ADIF importers. The uploader itself can be syntax-checked with `python -m py_compile documentation/test-contests/upload_logs.py`.
