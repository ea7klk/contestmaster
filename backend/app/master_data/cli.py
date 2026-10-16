"""One-shot master-data import and status commands."""

from __future__ import annotations

import argparse
import json
import logging
import sys

from sqlalchemy import desc, select

from backend.app.db import SessionFactory
from backend.app.master_data.jobs import sync_cty
from backend.app.models import MasterDataSyncRun, MasterDataVersion, MasterDataVersionStatus

logger = logging.getLogger("contestmaster.master_data.cli")


def _sync_enabled() -> tuple[dict[str, object], bool]:
    outcomes: list[dict[str, object]] = []
    failed = False
    for dataset_key, importer in (("cty", sync_cty),):
        try:
            outcomes.append({"dataset_key": dataset_key, **importer(SessionFactory)})
        except Exception as exc:
            logger.exception("master_data_sync_error", extra={"dataset_key": dataset_key})
            outcomes.append({"dataset_key": dataset_key, "error": str(exc)})
            failed = True
    return {"sources": outcomes}, failed


def _status() -> dict[str, object]:
    with SessionFactory() as session:
        active = list(
            session.scalars(
                select(MasterDataVersion)
                .where(MasterDataVersion.status == MasterDataVersionStatus.ACTIVE)
                .order_by(MasterDataVersion.dataset_key)
            )
        )
        runs = list(
            session.scalars(
                select(MasterDataSyncRun).order_by(desc(MasterDataSyncRun.started_at)).limit(20)
            )
        )
        return {
            "active_versions": [
                {
                    "dataset_key": version.dataset_key,
                    "version_id": version.id,
                    "source_release": version.source_release,
                    "valid_from": version.valid_from.isoformat(),
                    "valid_to": version.valid_to.isoformat() if version.valid_to else None,
                    "checksum": version.checksum,
                }
                for version in active
            ],
            "recent_runs": [
                {
                    "id": run.id,
                    "dataset_key": run.dataset_key,
                    "status": run.status.value,
                    "started_at": run.started_at.isoformat(),
                    "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                    "change_detected": run.change_detected,
                    "error": run.error_summary,
                }
                for run in runs
            ],
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="contestmaster-master-data")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("sync", help="Fetch and import the enabled CTY master-data source")
    subparsers.add_parser("sync-cty", help="Fetch and import the latest Big CTY release once")
    subparsers.add_parser("status", help="Show active versions and recent sync runs")
    args = parser.parse_args(argv)
    try:
        if args.command == "sync":
            result, failed = _sync_enabled()
        elif args.command == "sync-cty":
            result = sync_cty(SessionFactory)
            failed = False
        else:
            result = _status()
            failed = False
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, default=str))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
