# Test contests and generated logs

These two synthetic contests exercise the public log intake with no participant account:

| Folder | Import package | Format | Logs |
| --- | --- | --- | ---: |
| [`cabrillo`](cabrillo/) | `contest.json` | Cabrillo 3.0 | 110 |
| [`adif`](adif/) | `contest.json` | ADI/ADIF | 56 |

Every station and contact is synthetic. The contest event windows ended on **2024-09-14**. The separate submission cutoff is **2099-12-31 23:59:59 UTC**, and the rulesets accept late logs. Contest import creates each contest as a draft, so a contest manager must open it before the public upload endpoint will accept logs. The event being in the past does not close the submission window.

## Import and open the contests

1. Sign in as a contest manager or global administrator.
2. On the contest management page, use **Import contest** and select `cabrillo/contest.json`.
3. Repeat with `adif/contest.json`.
4. Edit each imported contest and change its status from **Draft** to **Open**. The event dates and 2099 cutoff are already set.
5. Start the API and frontend. The upload tool can target either the API directly or the Vite frontend proxy.

## Regenerate the logs

Run from the repository root:

```sh
python documentation/test-contests/cabrillo/generate_logs.py
python documentation/test-contests/adif/generate_logs.py
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
```

The default is 3.1 seconds between logs to stay below the API's per-IP limit of 20 uploads per minute. A `429` response is retried using `Retry-After` when provided. Stable content-based idempotency keys make rerunning the tool safe for exact retries. It reports entry IDs and HTTP failures but deliberately does not display or save the receipt tokens returned by the API.

## Verify the fixtures

```sh
uv run pytest documentation/test-contests/test_fixtures.py
```

The checks validate the imported JSON schema, generation counts and reproducibility, distinct station callsigns, one valid QSO per file, and successful parsing by the application's Cabrillo and ADIF importers. The uploader itself can be syntax-checked with `python -m py_compile documentation/test-contests/upload_logs.py`.
