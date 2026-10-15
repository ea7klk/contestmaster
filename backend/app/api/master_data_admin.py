"""Global-administrator master-data history and lifecycle operations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.api.auth import GlobalAdministrator
from backend.app.audit import record_audit_event
from backend.app.db import get_session
from backend.app.master_data.jobs import MasterDataError, activate_candidate
from backend.app.models import (
    CallsignPrefix,
    ContestEntity,
    ContestMasterDataVersion,
    CQZone,
    EntityCQZoneAssignment,
    EntityITUZoneAssignment,
    ITUZone,
    MasterDataSource,
    MasterDataSyncRun,
    MasterDataVersion,
    MasterDataVersionStatus,
    PrefixCQZoneAssignment,
    PrefixEntityAssignment,
    PrefixITUZoneAssignment,
    Qso,
    ScoreRun,
    ScoreRunMasterDataVersion,
)
from backend.app.models.enums import MasterDataRunStatus

router = APIRouter(prefix="/admin/master-data", tags=["master-data administration"])


def _reference_counts(session: Session, version_id: int) -> dict[str, int]:
    return {
        "contest": session.scalar(
            select(func.count())
            .select_from(ContestMasterDataVersion)
            .where(ContestMasterDataVersion.master_data_version_id == version_id)
        )
        or 0,
        "score_run": (
            session.scalar(
                select(func.count())
                .select_from(ScoreRunMasterDataVersion)
                .where(ScoreRunMasterDataVersion.master_data_version_id == version_id)
            )
            or 0
        )
        + (
            session.scalar(
                select(func.count())
                .select_from(ScoreRun)
                .where(ScoreRun.master_data_version_id == version_id)
            )
            or 0
        ),
        "qso_resolution": session.scalar(
            select(func.count())
            .select_from(Qso)
            .where(Qso.resolved_master_data_version_id == version_id)
        )
        or 0,
    }


def _run_output(run: MasterDataSyncRun, source: MasterDataSource) -> dict[str, object]:
    return {
        "id": run.id,
        "dataset_key": run.dataset_key,
        "source_key": source.source_key,
        "source_name": source.name,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "retrieved_at": run.retrieved_at,
        "source_url": run.source_url,
        "source_release": run.source_release,
        "checksum": run.checksum,
        "parser_version": run.parser_version,
        "status": run.status.value,
        "change_detected": run.change_detected,
        "record_counts": run.record_counts,
        "error_summary": run.error_summary,
    }


@router.get("/versions")
def list_master_data_versions(
    _principal: GlobalAdministrator,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    versions = list(
        session.scalars(
            select(MasterDataVersion).order_by(
                MasterDataVersion.dataset_key,
                MasterDataVersion.valid_from.desc(),
                MasterDataVersion.id.desc(),
            )
        )
    )
    items: list[dict[str, object]] = []
    for version in versions:
        run = session.get(MasterDataSyncRun, version.sync_run_id)
        source = session.get(MasterDataSource, run.source_id) if run else None
        if run is None or source is None:
            continue
        references = _reference_counts(session, version.id)
        deletable_status = version.status in {
            MasterDataVersionStatus.CANDIDATE,
            MasterDataVersionStatus.RETIRED,
        }
        items.append(
            {
                "id": version.id,
                "dataset_key": version.dataset_key,
                "status": version.status.value,
                "is_current": version.status is MasterDataVersionStatus.ACTIVE,
                "valid_from": version.valid_from,
                "valid_to": version.valid_to,
                "activated_at": version.activated_at,
                "created_at": version.created_at,
                "provenance": _run_output(run, source),
                "references": references,
                "can_activate": (
                    version.status is MasterDataVersionStatus.CANDIDATE
                    and run.status is MasterDataRunStatus.SUCCEEDED
                ),
                "can_delete": deletable_status and not any(references.values()),
            }
        )
    return {"items": items}


@router.get("/sync-runs")
def list_master_data_sync_runs(
    _principal: GlobalAdministrator,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    runs = list(
        session.scalars(
            select(MasterDataSyncRun)
            .order_by(MasterDataSyncRun.started_at.desc(), MasterDataSyncRun.id.desc())
            .limit(100)
        )
    )
    items: list[dict[str, object]] = []
    for run in runs:
        source = session.get(MasterDataSource, run.source_id)
        if source is not None:
            items.append(_run_output(run, source))
    return {"items": items}


@router.post("/versions/{version_id}/activate")
def activate_master_data_version(
    version_id: int,
    principal: GlobalAdministrator,
    session: Annotated[Session, Depends(get_session)],
    request: Request,
    audit_reason: Annotated[str | None, Query(max_length=2000)] = None,
) -> dict[str, object]:
    version = session.get(MasterDataVersion, version_id)
    run = session.get(MasterDataSyncRun, version.sync_run_id) if version else None
    if (
        version is None
        or version.status is not MasterDataVersionStatus.CANDIDATE
        or run is None
        or run.status is not MasterDataRunStatus.SUCCEEDED
    ):
        raise HTTPException(
            status_code=409, detail="Only a successfully validated candidate can be activated."
        )
    try:
        active = activate_candidate(session, version_id, datetime.now(UTC))
        record_audit_event(
            session,
            actor_user_id=principal.user_id,
            action="master_data.version_activated",
            target_type="master_data_version",
            target_id=active.id,
            reason=audit_reason,
            metadata={"dataset_key": active.dataset_key, "sync_run_id": active.sync_run_id},
            request_id=getattr(request.state, "request_id", None),
        )
        session.commit()
    except MasterDataError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.refresh(active)
    return {"id": active.id, "dataset_key": active.dataset_key, "status": active.status.value}


@router.delete("/versions/{version_id}", status_code=204)
def delete_master_data_version(
    version_id: int,
    principal: GlobalAdministrator,
    session: Annotated[Session, Depends(get_session)],
    request: Request,
    audit_reason: Annotated[str | None, Query(max_length=2000)] = None,
) -> None:
    version = session.get(MasterDataVersion, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Master-data version not found.")
    if version.status is MasterDataVersionStatus.ACTIVE:
        raise HTTPException(
            status_code=409, detail="The current master-data version cannot be deleted."
        )
    if version.status not in {MasterDataVersionStatus.CANDIDATE, MasterDataVersionStatus.RETIRED}:
        raise HTTPException(status_code=409, detail="This master-data version cannot be deleted.")
    references = _reference_counts(session, version.id)
    if any(references.values()):
        raise HTTPException(
            status_code=409,
            detail="Master-data version is still referenced and cannot be deleted.",
        )

    audit_version_id = version.id
    event_metadata = {"dataset_key": version.dataset_key, "sync_run_id": version.sync_run_id}
    try:
        for model in (
            PrefixEntityAssignment,
            PrefixCQZoneAssignment,
            PrefixITUZoneAssignment,
            EntityCQZoneAssignment,
            EntityITUZoneAssignment,
            CallsignPrefix,
            ContestEntity,
            CQZone,
            ITUZone,
        ):
            session.execute(delete(model).where(model.version_id == version_id))
        record_audit_event(
            session,
            actor_user_id=principal.user_id,
            action="master_data.version_deleted",
            target_type="master_data_version",
            target_id=audit_version_id,
            reason=audit_reason,
            metadata=event_metadata,
            request_id=getattr(request.state, "request_id", None),
        )
        session.delete(version)
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Master-data version is referenced by retained records and cannot be deleted.",
        ) from exc
