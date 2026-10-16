#!/usr/bin/env python3
"""Upload generated test logs anonymously to a running Contestmaster app."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import mimetypes
import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
CONTESTS = {
    "cabrillo": (ROOT / "cabrillo", "test-cabrillo-results-sprint"),
    "adif": (ROOT / "adif", "test-adif-ft8-results-sprint"),
}
DEFAULT_DELAY_SECONDS = 3.1
MAX_ATTEMPTS = 5
LOGGER = logging.getLogger("contestmaster.test_upload")


@dataclass(frozen=True)
class UploadResult:
    filename: str
    accepted: bool
    entry_id: int | None = None
    detail: str | None = None
    retries: int = 0
    elapsed_seconds: float = 0.0


def _base_url(value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise argparse.ArgumentTypeError("URL must include http:// or https:// and a host")
    path = parts.path.rstrip("/")
    if path.endswith("/api/v1"):
        path = path[: -len("/api/v1")]
    return urlunsplit((parts.scheme, parts.netloc, path, "", "")).rstrip("/")


def _display_url(value: str) -> str:
    """Display the endpoint without URL userinfo, query parameters, or fragments."""
    parts = urlsplit(value)
    host = parts.hostname or "unknown-host"
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    if parts.port:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, host, parts.path, "", ""))


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


def _safe_server_detail(error: HTTPError) -> str:
    """Return a short allowlisted error detail without exposing arbitrary response data."""
    try:
        payload = json.loads(error.read().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, OSError):
        return f"HTTP {error.code}"

    details: list[str] = []
    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str):
            details.append(detail)
        errors = payload.get("errors")
        if isinstance(errors, list):
            for item in errors[:3]:
                if not isinstance(item, dict):
                    continue
                line = item.get("line")
                message = item.get("message")
                if isinstance(message, str):
                    prefix = f"line {line}: " if isinstance(line, int) and line > 0 else ""
                    details.append(prefix + message)
    cleaned = " ".join(_redact(detail) for detail in details if detail.strip())
    return f"HTTP {error.code}: {cleaned[:400]}" if cleaned else f"HTTP {error.code}"


def _redact(value: str) -> str:
    value = re.sub(
        r"(?i)(receipt[ _-]?token|authorization|secret|password)\s*[:=]\s*\S+",
        r"\1=[redacted]",
        value,
    )
    return " ".join(value.split())[:240]


def upload_one(base_url: str, contest_slug: str, path: Path) -> UploadResult:
    started = time.monotonic()
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
        retries = attempt
        try:
            with urlopen(request, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
                if (
                    response.status not in {200, 201}
                    or not isinstance(result, dict)
                    or result.get("status") != "accepted"
                ):
                    return UploadResult(
                        path.name,
                        False,
                        detail=f"unexpected API response ({response.status})",
                        retries=retries,
                        elapsed_seconds=time.monotonic() - started,
                    )
                return UploadResult(
                    path.name,
                    True,
                    entry_id=result.get("entry_id"),
                    retries=retries,
                    elapsed_seconds=time.monotonic() - started,
                )
        except HTTPError as error:
            if error.code == 429 and attempt + 1 < MAX_ATTEMPTS:
                delay = _retry_after(error)
                LOGGER.warning(
                    "%s: API rate limit (HTTP 429); retry %d/%d in %.1f seconds",
                    path.name,
                    attempt + 1,
                    MAX_ATTEMPTS - 1,
                    delay,
                )
                time.sleep(delay)
                continue
            if error.code >= 500 and attempt + 1 < MAX_ATTEMPTS:
                delay = DEFAULT_DELAY_SECONDS * (attempt + 1)
                LOGGER.warning(
                    "%s: server error (HTTP %d); retry %d/%d in %.1f seconds",
                    path.name,
                    error.code,
                    attempt + 1,
                    MAX_ATTEMPTS - 1,
                    delay,
                )
                time.sleep(delay)
                continue
            return UploadResult(
                path.name,
                False,
                detail=_safe_server_detail(error),
                retries=retries,
                elapsed_seconds=time.monotonic() - started,
            )
        except (TimeoutError, URLError, OSError) as error:
            if attempt + 1 < MAX_ATTEMPTS:
                delay = DEFAULT_DELAY_SECONDS * (attempt + 1)
                reason = getattr(error, "reason", None)
                reason_text = _redact(str(reason or error))
                LOGGER.warning(
                    "%s: network error (%s); retry %d/%d in %.1f seconds",
                    path.name,
                    reason_text,
                    attempt + 1,
                    MAX_ATTEMPTS - 1,
                    delay,
                )
                time.sleep(delay)
                continue
            return UploadResult(
                path.name,
                False,
                detail=f"Network error: {_redact(str(getattr(error, 'reason', None) or error))}",
                retries=retries,
                elapsed_seconds=time.monotonic() - started,
            )
        except (UnicodeDecodeError, json.JSONDecodeError):
            return UploadResult(
                path.name,
                False,
                detail="The API returned an invalid JSON response.",
                retries=retries,
                elapsed_seconds=time.monotonic() - started,
            )
    return UploadResult(
        path.name,
        False,
        detail="Retry limit reached.",
        retries=MAX_ATTEMPTS - 1,
        elapsed_seconds=time.monotonic() - started,
    )


def _log_summary(label: str, results: list[UploadResult], elapsed_seconds: float) -> None:
    accepted = sum(result.accepted for result in results)
    failed = len(results) - accepted
    retries = sum(result.retries for result in results)
    throughput = len(results) * 60 / elapsed_seconds if elapsed_seconds > 0 else 0.0
    LOGGER.info(
        "%s summary: total=%d accepted=%d failed=%d retries=%d elapsed=%.1fs rate=%.1f logs/min",
        label,
        len(results),
        accepted,
        failed,
        retries,
        elapsed_seconds,
        throughput,
    )


def upload_set(base_url: str, name: str, delay: float) -> list[UploadResult]:
    directory, contest_slug = CONTESTS[name]
    extension = ".log" if name == "cabrillo" else ".adi"
    files = sorted((directory / "logs").glob(f"*{extension}"))
    if not files:
        raise FileNotFoundError(
            f"No {extension} files found in {directory / 'logs'}; run its generate_logs.py first."
        )
    LOGGER.info(
        "Starting %s batch: contest=%s files=%d delay=%.1fs",
        name,
        contest_slug,
        len(files),
        delay,
    )
    results = []
    started = time.monotonic()
    for index, path in enumerate(files):
        if index:
            time.sleep(delay)
        LOGGER.info("Uploading %s [%d/%d]", path.name, index + 1, len(files))
        try:
            result = upload_one(base_url, contest_slug, path)
        except OSError as error:
            result = UploadResult(
                path.name,
                False,
                detail=f"Cannot read file: {_redact(str(error))}",
            )
        results.append(result)
        if result.accepted:
            LOGGER.info(
                "Accepted %s [%d/%d] (entry=%s, retries=%d, request=%.2fs)",
                path.name,
                index + 1,
                len(files),
                result.entry_id,
                result.retries,
                result.elapsed_seconds,
            )
        else:
            LOGGER.error(
                "Failed %s [%d/%d]: %s (retries=%d, request=%.2fs)",
                path.name,
                index + 1,
                len(files),
                result.detail,
                result.retries,
                result.elapsed_seconds,
            )
    _log_summary(name, results, time.monotonic() - started)
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
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    all_results: list[UploadResult] = []
    started = time.monotonic()
    try:
        for index, selection in enumerate(selections):
            if index:
                time.sleep(args.delay)
            LOGGER.info("Using app endpoint %s", _display_url(args.url))
            all_results.extend(upload_set(args.url, selection, args.delay))
    except (FileNotFoundError, OSError) as error:
        LOGGER.error("Cannot start upload batch: %s", error)
        return 2
    failed = sum(not result.accepted for result in all_results)
    _log_summary("Overall", all_results, time.monotonic() - started)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
