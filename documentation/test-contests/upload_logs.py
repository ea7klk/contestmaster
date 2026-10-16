#!/usr/bin/env python3
"""Upload generated test logs anonymously to a running Contestmaster app."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
CONTESTS = {
    "cabrillo": (ROOT / "cabrillo", "test-cabrillo-sprint"),
    "adif": (ROOT / "adif", "test-adif-ft8-sprint"),
}
DEFAULT_DELAY_SECONDS = 3.1
MAX_ATTEMPTS = 5


@dataclass(frozen=True)
class UploadResult:
    filename: str
    accepted: bool
    entry_id: int | None = None
    detail: str | None = None


def _base_url(value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise argparse.ArgumentTypeError("URL must include http:// or https:// and a host")
    path = parts.path.rstrip("/")
    if path.endswith("/api/v1"):
        path = path[: -len("/api/v1")]
    return urlunsplit((parts.scheme, parts.netloc, path, "", "")).rstrip("/")


def _multipart(filename: str, content: bytes) -> tuple[bytes, str]:
    boundary = "----ContestmasterTestUploadBoundary7MA4YWxkTrZu0gW"
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    safe_name = Path(filename).name.replace('"', "")
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{safe_name}"\r\n'
        f"Content-Type: {mime}\r\n\r\n"
    ).encode("ascii") + content + f"\r\n--{boundary}--\r\n".encode("ascii")
    return body, f"multipart/form-data; boundary={boundary}"


def _retry_after(error: HTTPError) -> float:
    value = error.headers.get("Retry-After", "")
    try:
        return max(float(value), DEFAULT_DELAY_SECONDS)
    except ValueError:
        return DEFAULT_DELAY_SECONDS


def upload_one(base_url: str, contest_slug: str, path: Path) -> UploadResult:
    content = path.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    idempotency_key = f"test-{contest_slug}-{digest[:48]}"
    body, content_type = _multipart(path.name, content)
    url = f"{base_url}/api/v1/public/contests/{quote(contest_slug, safe='')}/logs"
    request = Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": content_type,
            "Content-Length": str(len(body)),
            "Idempotency-Key": idempotency_key,
            "Accept": "application/json",
        },
    )
    for attempt in range(MAX_ATTEMPTS):
        try:
            with urlopen(request, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
                if response.status not in {200, 201} or result.get("status") != "accepted":
                    return UploadResult(
                        path.name,
                        False,
                        detail=f"unexpected API response ({response.status})",
                    )
                return UploadResult(path.name, True, entry_id=result.get("entry_id"))
        except HTTPError as error:
            if error.code == 429 and attempt + 1 < MAX_ATTEMPTS:
                time.sleep(_retry_after(error))
                continue
            if error.code >= 500 and attempt + 1 < MAX_ATTEMPTS:
                time.sleep(DEFAULT_DELAY_SECONDS * (attempt + 1))
                continue
            # Deliberately avoid printing the response body; it can include receipt tokens.
            return UploadResult(path.name, False, detail=f"HTTP {error.code}")
        except (TimeoutError, URLError, OSError) as error:
            if attempt + 1 < MAX_ATTEMPTS:
                time.sleep(DEFAULT_DELAY_SECONDS * (attempt + 1))
                continue
            return UploadResult(path.name, False, detail=type(error).__name__)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return UploadResult(path.name, False, detail="invalid JSON response")
    return UploadResult(path.name, False, detail="retry limit reached")


def upload_set(base_url: str, name: str, delay: float) -> list[UploadResult]:
    directory, contest_slug = CONTESTS[name]
    extension = ".log" if name == "cabrillo" else ".adi"
    files = sorted((directory / "logs").glob(f"*{extension}"))
    if not files:
        raise FileNotFoundError(
            f"No {extension} files found in {directory / 'logs'}; run its generate_logs.py first."
        )
    results = []
    for index, path in enumerate(files):
        if index:
            time.sleep(delay)
        result = upload_one(base_url, contest_slug, path)
        results.append(result)
        if result.accepted:
            print(f"{name}: accepted {path.name} (entry {result.entry_id})")
        else:
            print(f"{name}: failed {path.name} ({result.detail})", file=sys.stderr)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "url",
        type=_base_url,
        help="app base URL, for example http://127.0.0.1:8000 or http://127.0.0.1:5173",
    )
    parser.add_argument(
        "--contest",
        choices=("cabrillo", "adif", "all"),
        default="all",
        help="fixture set to upload (default: all)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY_SECONDS,
        help=(
            f"seconds between uploads; minimum is {DEFAULT_DELAY_SECONDS:g} "
            "to stay under the local API limit"
        ),
    )
    args = parser.parse_args()
    if args.delay < DEFAULT_DELAY_SECONDS:
        parser.error(f"--delay must be at least {DEFAULT_DELAY_SECONDS:g} seconds")
    selections = ("cabrillo", "adif") if args.contest == "all" else (args.contest,)
    all_results: list[UploadResult] = []
    try:
        for index, selection in enumerate(selections):
            if index:
                time.sleep(args.delay)
            print(f"Uploading {selection} fixture logs to {args.url}")
            all_results.extend(upload_set(args.url, selection, args.delay))
    except (FileNotFoundError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 2
    failed = sum(not result.accepted for result in all_results)
    print(f"Finished: {len(all_results) - failed} accepted, {failed} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
