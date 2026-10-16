# Test contests and generated logs

These synthetic contests exercise anonymous uploads, score calculation, and ruleset behavior:

| Folder | Import package | Format | Logs |
| --- | --- | --- | ---: |
| [`cabrillo`](cabrillo/) | `contest.json` | Cabrillo 3.0 | 110 |
| [`adif`](adif/) | `contest.json` | ADI/ADIF | 56 |
| [`advanced-cabrillo`](advanced-cabrillo/) | `contest.json` | Cabrillo 3.0 | 32 |

Every station and contact is synthetic. The Cabrillo results sprint has featured logs with 80, 30, and 20 QSOs; all other logs contain 5 QSOs. The ADIF sprint has featured logs with 60, 20, and 10 QSOs; all other logs contain 5 QSOs. Exactly 80% of worked-call entries in these two sprints name another participant whose log contains the reciprocal QSO; the other 20% name external stations with no log in that contest. Cabrillo QSO lines put the logging station's exchange after its callsign and the correspondent's exchange after the correspondent's callsign, as shown in the [WWROF Cabrillo QSO data specification](https://wwrof.org/cabrillo/cabrillo-qso-data/). These fixtures use sequential sent serials and include the serial received from each matched correspondent; the Cabrillo ruleset requires the serial in both directions.

The results sprints now combine contact points, a 1,000-point activity bonus for entries meeting a QSO threshold, and multiple multiplier types. The resulting top three are `K0AAA`, `K0AAB`, and `K0AAC`: scores are 87,480 / 32,960 / 22,440 in the Cabrillo set and 65,720 / 22,440 / 120 in the ADIF set. The featured contact tiers and activity bonus create a wider score spread than the earlier fixtures.

The advanced Cabrillo challenge is a separate 32-participant package with 206 QSOs. It intentionally includes one repeated contact in `K0AAA.log`. Its ruleset exercises five category dimensions, Cabrillo category mapping, serial exchange validation, conditional band/mode eligibility, duplicate penalties, fixed and mode/band/exchange point rules, callsign/serial/mode multipliers, conditional activity bonuses, limited per-QSO point deductions and contact removal, operating-time/off-time/transmitter constraints, conditional cross-log and adjudication hooks, award and publication hooks, and a left-to-right integer score formula. Its generated top three are `K0AAA`, `K0AAB`, and `K0AAC`, with scores of 21,344 / 8,487 / 1,534. The challenge also generates review outcomes that can be included by its fixture-only publication policy. Rules that depend on exchange fields use the Cabrillo parser's supported QSO columns and do not add extra positional tokens to the Cabrillo QSO record.

Both fixture sets use the 20 m band and vary each QSO frequency from 14.000 through 14.350 MHz. Matched contacts have the same frequency in both logs. Cabrillo records frequency in kHz; ADIF records it in the standard `FREQ` field in MHz and retains `BAND: 20M`.

Every Cabrillo fixture includes a synthetic `EMAIL: <callsign>@nomail.invalid` header. The reserved `.invalid` domain ensures these addresses cannot deliver mail.

The results sprint sets contain 665 Cabrillo QSO records (532 matching and 133 unmatched) and 355 ADIF records (284 matching and 71 unmatched). The advanced Cabrillo set contains 205 graph-generated records plus one intentional duplicate. These counts and standings are reproducible from the checked-in generators.

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

The API accepts up to 60 anonymous log submissions per IP in any rolling 60-second window. The uploader defaults to 1.1 seconds between logs, staying just below that limit, and rejects `--delay` values below 1.1 seconds. A `429` response is retried using `Retry-After` when provided, with at least the default delay. Stable content-based idempotency keys make rerunning the tool safe for exact retries. It reports entry IDs and HTTP failures but deliberately does not display or save the receipt tokens returned by the API.

The uploader logs timestamps, batch and per-file progress, accepted entry IDs, retry reasons and delays, and bounded validation details for final failures. Per-contest and overall summaries include total, accepted, failed, retry count, elapsed seconds, and average logs per minute. Logs go to standard error, leaving standard output available for command wrappers.

## Verify the fixtures

```sh
uv run pytest documentation/test-contests/test_fixtures.py
```

The checks validate all three imported JSON schemas, generation counts and reproducibility, distinct station callsigns, the 5–80 QSO limit, the exact 80/20 reciprocal-call ratio in both results sprints, Cabrillo serial matching in both directions, the increased score spread, advanced category import and scoring paths, and successful parsing by the application's Cabrillo and ADIF importers. The uploader itself can be syntax-checked with `python -m py_compile documentation/test-contests/upload_logs.py`.
