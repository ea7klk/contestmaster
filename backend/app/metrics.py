"""Low-cardinality Prometheus metrics for first-deployment operations."""

from __future__ import annotations

import time

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

registry = CollectorRegistry(auto_describe=True)

HTTP_REQUESTS = Counter(
    "contestmaster_http_requests_total",
    "HTTP requests handled by Contestmaster.",
    ("method", "status_class"),
    registry=registry,
)
HTTP_DURATION = Histogram(
    "contestmaster_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ("method",),
    registry=registry,
)
UPLOADS = Counter(
    "contestmaster_log_uploads_total",
    "Guest and participant log upload requests by outcome.",
    ("outcome",),
    registry=registry,
)
SCORE_RUNS = Counter(
    "contestmaster_score_runs_total",
    "Score runs completed or failed.",
    ("outcome",),
    registry=registry,
)
MASTER_DATA_SYNCS = Counter(
    "contestmaster_master_data_syncs_total",
    "Master-data synchronization attempts by configured dataset and outcome.",
    ("dataset", "outcome"),
    registry=registry,
)
MASTER_DATA_SYNC_LAST_ATTEMPT = Gauge(
    "contestmaster_master_data_sync_last_attempt_timestamp_seconds",
    "Unix timestamp of the last completed master-data synchronization attempt.",
    ("dataset",),
    registry=registry,
)
MASTER_DATA_SYNC_LAST_SUCCESS = Gauge(
    "contestmaster_master_data_sync_last_success_timestamp_seconds",
    "Unix timestamp of the last successful master-data synchronization.",
    ("dataset",),
    registry=registry,
)
DATABASE_ERRORS = Counter(
    "contestmaster_database_errors_total",
    "Database driver operations that raised an exception.",
    registry=registry,
)

_METHODS = {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"}
_DATASETS = {"cty", "countries-ungegn-wgn", "countries-unsd-m49"}
for _dataset in _DATASETS:
    MASTER_DATA_SYNC_LAST_ATTEMPT.labels(_dataset).set(0)
    MASTER_DATA_SYNC_LAST_SUCCESS.labels(_dataset).set(0)


def normalized_method(method: str) -> str:
    value = method.upper()
    return value if value in _METHODS else "OTHER"


def normalized_status_class(status_code: int) -> str:
    value = status_code // 100
    return f"{value}xx" if 1 <= value <= 5 else "other"


def record_http_request(method: str, status_code: int, duration_seconds: float) -> None:
    safe_method = normalized_method(method)
    HTTP_REQUESTS.labels(safe_method, normalized_status_class(status_code)).inc()
    HTTP_DURATION.labels(safe_method).observe(max(0.0, duration_seconds))


def record_upload(status_code: int) -> None:
    outcome = (
        "accepted" if 200 <= status_code < 300 else "rejected" if status_code < 500 else "failed"
    )
    UPLOADS.labels(outcome).inc()


def record_score_run(outcome: str) -> None:
    SCORE_RUNS.labels("completed" if outcome == "completed" else "failed").inc()


def record_master_data_sync(dataset: str, status: str) -> None:
    if dataset not in _DATASETS:
        return
    outcome = status if status in {"changed", "unchanged", "candidate", "failed"} else "completed"
    now = time.time()
    MASTER_DATA_SYNCS.labels(dataset, outcome).inc()
    MASTER_DATA_SYNC_LAST_ATTEMPT.labels(dataset).set(now)
    if outcome != "failed":
        MASTER_DATA_SYNC_LAST_SUCCESS.labels(dataset).set(now)


def record_database_error() -> None:
    DATABASE_ERRORS.inc()
