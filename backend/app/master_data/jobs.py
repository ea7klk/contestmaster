"""Transactional import and version-selection services for master data."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta

from sqlalchemy import insert, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.master_data.cty import (
    DATASET_KEY,
    PARSER_VERSION,
    RSS_URL,
    SOURCE_KEY,
    TERMS_URL,
    CTYRelease,
    fetch_latest_archive,
    parse_archive,
)
from backend.app.master_data.m49 import (
    DATASET_KEY as M49_DATASET_KEY,
)
from backend.app.master_data.m49 import (
    PARSER_VERSION as M49_PARSER_VERSION,
)
from backend.app.master_data.m49 import (
    SOURCE_KEY as M49_SOURCE_KEY,
)
from backend.app.master_data.m49 import (
    SOURCE_URL as M49_SOURCE_URL,
)
from backend.app.master_data.m49 import (
    USE_TERMS_URL as M49_USE_TERMS_URL,
)
from backend.app.master_data.m49 import (
    M49CountryAreaData,
    fetch_country_areas,
)
from backend.app.master_data.ungegn import (
    API_DOCS_URL as UNGEGN_API_DOCS_URL,
)
from backend.app.master_data.ungegn import (
    DATASET_KEY as UNGEGN_DATASET_KEY,
)
from backend.app.master_data.ungegn import (
    PARSER_VERSION as UNGEGN_PARSER_VERSION,
)
from backend.app.master_data.ungegn import (
    SOURCE_KEY as UNGEGN_SOURCE_KEY,
)
from backend.app.master_data.ungegn import (
    SOURCE_URL as UNGEGN_SOURCE_URL,
)
from backend.app.master_data.ungegn import (
    USE_TERMS_URL as UNGEGN_USE_TERMS_URL,
)
from backend.app.master_data.ungegn import (
    WgnCountryData,
    fetch_countries,
)
from backend.app.models import (
    CallsignPrefix,
    Contest,
    ContestEntity,
    ContestMasterDataVersion,
    CQZone,
    EntityCQZoneAssignment,
    EntityITUZoneAssignment,
    EntityType,
    ITUZone,
    MasterDataAuthorityRole,
    MasterDataRunStatus,
    MasterDataSource,
    MasterDataSyncRun,
    MasterDataVersion,
    MasterDataVersionStatus,
    PrefixCQZoneAssignment,
    PrefixEntityAssignment,
    PrefixITUZoneAssignment,
)
from backend.app.models.master_data import CQZone as CQZoneModel
from backend.app.models.types import utc_now

logger = logging.getLogger("contestmaster.master_data")
FetchArchive = Callable[[], tuple[bytes, str, str, datetime]]
RUN_STALE_AFTER = timedelta(hours=6)


class MasterDataError(RuntimeError):
    pass


class MissingContestMasterData(MasterDataError):
    def __init__(self, dataset_keys: Iterable[str]) -> None:
        self.dataset_keys = tuple(sorted(set(dataset_keys)))
        super().__init__(
            "No master-data version covers contest start for: " + ", ".join(self.dataset_keys)
        )


class ContestMasterDataAlreadyPinned(MasterDataError):
    pass


def _ensure_cty_source(session: Session) -> MasterDataSource:
    source = session.scalar(
        select(MasterDataSource).where(MasterDataSource.source_key == SOURCE_KEY)
    )
    if source is None:
        source = MasterDataSource(
            source_key=SOURCE_KEY,
            name="Big CTY",
            canonical_url=RSS_URL,
            source_priority=0,
            authority_role=MasterDataAuthorityRole.PRIMARY_OPERATIONAL,
            use_terms_url=TERMS_URL,
            license_notice=None,
            enabled=True,
        )
        session.add(source)
        session.flush()
    return source


def _create_run(session_factory: sessionmaker[Session]) -> int:
    with session_factory.begin() as session:
        source = _ensure_cty_source(session)
        active = session.scalar(
            select(MasterDataSyncRun).where(
                MasterDataSyncRun.source_id == source.id,
                MasterDataSyncRun.dataset_key == DATASET_KEY,
                MasterDataSyncRun.status == MasterDataRunStatus.RUNNING,
            )
        )
        now = utc_now()
        if active is not None:
            if active.started_at >= now - RUN_STALE_AFTER:
                raise MasterDataError(f"A Big CTY sync run ({active.id}) is already running")
            active.status = MasterDataRunStatus.FAILED
            active.finished_at = now
            active.error_summary = "Marked failed because its running lease exceeded six hours."
        session.flush()
        run = MasterDataSyncRun(
            source_id=source.id,
            dataset_key=DATASET_KEY,
            started_at=now,
            parser_version=PARSER_VERSION,
            status=MasterDataRunStatus.RUNNING,
        )
        session.add(run)
        session.flush()
        return run.id


def _finish_failed(session_factory: sessionmaker[Session], run_id: int, error: Exception) -> None:
    with session_factory.begin() as session:
        run = session.get(MasterDataSyncRun, run_id)
        if run is not None:
            run.status = MasterDataRunStatus.FAILED
            run.finished_at = utc_now()
            run.error_summary = str(error)[:2000]


def _create_ungegn_run(session_factory: sessionmaker[Session]) -> int:
    with session_factory.begin() as session:
        source = session.scalar(
            select(MasterDataSource).where(MasterDataSource.source_key == UNGEGN_SOURCE_KEY)
        )
        if source is None:
            source = MasterDataSource(
                source_key=UNGEGN_SOURCE_KEY,
                name="UNGEGN World Geographical Names country reference",
                canonical_url=UNGEGN_SOURCE_URL,
                source_priority=60,
                authority_role=MasterDataAuthorityRole.GAP_FILLING,
                use_terms_url=UNGEGN_USE_TERMS_URL,
                license_notice=(
                    "UNGEGN describes WGN API data as open access, publicly available "
                    "without restriction."
                ),
                enabled=True,
            )
            session.add(source)
            session.flush()
        source.canonical_url = UNGEGN_SOURCE_URL
        source.use_terms_url = UNGEGN_USE_TERMS_URL
        source.license_notice = (
            "UNGEGN describes WGN API data as open access, publicly available without restriction. "
            f"API specification: {UNGEGN_API_DOCS_URL}"
        )
        source.enabled = True
        active = session.scalar(
            select(MasterDataSyncRun).where(
                MasterDataSyncRun.source_id == source.id,
                MasterDataSyncRun.dataset_key == UNGEGN_DATASET_KEY,
                MasterDataSyncRun.status == MasterDataRunStatus.RUNNING,
            )
        )
        now = utc_now()
        if active is not None:
            if active.started_at >= now - RUN_STALE_AFTER:
                raise MasterDataError(f"An UNGEGN WGN sync run ({active.id}) is already running")
            active.status = MasterDataRunStatus.FAILED
            active.finished_at = now
            active.error_summary = "Marked failed because its running lease exceeded six hours."
        session.flush()
        run = MasterDataSyncRun(
            source_id=source.id,
            dataset_key=UNGEGN_DATASET_KEY,
            started_at=now,
            parser_version=UNGEGN_PARSER_VERSION,
            status=MasterDataRunStatus.RUNNING,
        )
        session.add(run)
        session.flush()
        return run.id


def _persist_ungegn_data(
    session: Session, run: MasterDataSyncRun, source_data: WgnCountryData
) -> MasterDataVersion:
    current = session.scalar(
        select(MasterDataVersion).where(
            MasterDataVersion.dataset_key == UNGEGN_DATASET_KEY,
            MasterDataVersion.status == MasterDataVersionStatus.ACTIVE,
        )
    )
    candidate = session.scalar(
        select(MasterDataVersion).where(
            MasterDataVersion.dataset_key == UNGEGN_DATASET_KEY,
            MasterDataVersion.checksum == source_data.normalized_checksum,
            MasterDataVersion.status == MasterDataVersionStatus.CANDIDATE,
        )
    )
    run.retrieved_at = source_data.retrieved_at
    run.source_url = UNGEGN_SOURCE_URL
    run.source_release = "WGN API current"
    run.checksum = source_data.response_sha256
    run.record_counts = {"countries": len(source_data.countries)}
    if current is not None and current.checksum == source_data.normalized_checksum:
        run.status = MasterDataRunStatus.SUCCEEDED
        run.change_detected = False
        run.finished_at = utc_now()
        return current
    if candidate is not None:
        run.status = MasterDataRunStatus.SUCCEEDED
        run.change_detected = False
        run.finished_at = utc_now()
        return candidate

    changed = current is not None
    version = MasterDataVersion(
        sync_run_id=run.id,
        dataset_key=UNGEGN_DATASET_KEY,
        source_release="WGN API current",
        retrieved_at=source_data.retrieved_at,
        checksum=source_data.normalized_checksum,
        activated_at=None if changed else source_data.retrieved_at,
        valid_from=source_data.retrieved_at,
        status=(MasterDataVersionStatus.CANDIDATE if changed else MasterDataVersionStatus.ACTIVE),
    )
    session.add(version)
    session.flush()
    session.add_all(
        [
            ContestEntity(
                version_id=version.id,
                namespace="UN-M49",
                authority_code=country.m49_code,
                name=country.name,
                entity_type=EntityType.OTHER,
            )
            for country in source_data.countries
        ]
    )
    run.change_detected = True
    run.status = MasterDataRunStatus.SUCCEEDED
    run.finished_at = utc_now()
    run.error_summary = (
        "Changed country reference staged for global administrator review." if changed else None
    )
    return version


def _create_m49_run(session_factory: sessionmaker[Session]) -> int:
    with session_factory.begin() as session:
        source = session.scalar(
            select(MasterDataSource).where(MasterDataSource.source_key == M49_SOURCE_KEY)
        )
        if source is None:
            source = MasterDataSource(
                source_key=M49_SOURCE_KEY,
                name="UN Statistics Division M49 country-or-area list",
                canonical_url=M49_SOURCE_URL,
                source_priority=70,
                authority_role=MasterDataAuthorityRole.GAP_FILLING,
                use_terms_url=M49_USE_TERMS_URL,
                license_notice=(
                    "UN M49 country-or-area names and numeric codes are used as published. "
                    "See UN website terms of use."
                ),
                enabled=True,
            )
            session.add(source)
            session.flush()
        source.canonical_url = M49_SOURCE_URL
        source.use_terms_url = M49_USE_TERMS_URL
        source.license_notice = (
            "UN M49 country-or-area names and numeric codes are used as published, without "
            "modification or derived M49 classifications. See UN website terms of use."
        )
        source.enabled = True
        active = session.scalar(
            select(MasterDataSyncRun).where(
                MasterDataSyncRun.source_id == source.id,
                MasterDataSyncRun.dataset_key == M49_DATASET_KEY,
                MasterDataSyncRun.status == MasterDataRunStatus.RUNNING,
            )
        )
        now = utc_now()
        if active is not None:
            if active.started_at >= now - RUN_STALE_AFTER:
                raise MasterDataError(f"An UN M49 sync run ({active.id}) is already running")
            active.status = MasterDataRunStatus.FAILED
            active.finished_at = now
            active.error_summary = "Marked failed because its running lease exceeded six hours."
        session.flush()
        run = MasterDataSyncRun(
            source_id=source.id,
            dataset_key=M49_DATASET_KEY,
            started_at=now,
            parser_version=M49_PARSER_VERSION,
            status=MasterDataRunStatus.RUNNING,
        )
        session.add(run)
        session.flush()
        return run.id


def _persist_m49_data(
    session: Session, run: MasterDataSyncRun, source_data: M49CountryAreaData
) -> MasterDataVersion:
    current = session.scalar(
        select(MasterDataVersion).where(
            MasterDataVersion.dataset_key == M49_DATASET_KEY,
            MasterDataVersion.status == MasterDataVersionStatus.ACTIVE,
        )
    )
    candidate = session.scalar(
        select(MasterDataVersion).where(
            MasterDataVersion.dataset_key == M49_DATASET_KEY,
            MasterDataVersion.checksum == source_data.normalized_checksum,
            MasterDataVersion.status == MasterDataVersionStatus.CANDIDATE,
        )
    )
    run.retrieved_at = source_data.retrieved_at
    run.source_url = M49_SOURCE_URL
    run.source_release = "UNSD M49 overview current"
    run.checksum = source_data.response_sha256
    run.record_counts = {"country_areas": len(source_data.country_areas)}
    if current is not None and current.checksum == source_data.normalized_checksum:
        run.status = MasterDataRunStatus.SUCCEEDED
        run.change_detected = False
        run.finished_at = utc_now()
        return current
    if candidate is not None:
        run.status = MasterDataRunStatus.SUCCEEDED
        run.change_detected = False
        run.finished_at = utc_now()
        return candidate

    changed = current is not None
    version = MasterDataVersion(
        sync_run_id=run.id,
        dataset_key=M49_DATASET_KEY,
        source_release="UNSD M49 overview current",
        retrieved_at=source_data.retrieved_at,
        checksum=source_data.normalized_checksum,
        activated_at=None if changed else source_data.retrieved_at,
        valid_from=source_data.retrieved_at,
        status=(MasterDataVersionStatus.CANDIDATE if changed else MasterDataVersionStatus.ACTIVE),
    )
    session.add(version)
    session.flush()
    session.add_all(
        [
            ContestEntity(
                version_id=version.id,
                namespace="UN-M49",
                authority_code=country_area.m49_code,
                name=country_area.name,
                entity_type=EntityType.OTHER,
            )
            for country_area in source_data.country_areas
        ]
    )
    run.change_detected = True
    run.status = MasterDataRunStatus.SUCCEEDED
    run.finished_at = utc_now()
    run.error_summary = (
        "Changed country-or-area reference staged for global administrator review."
        if changed
        else None
    )
    return version


def _active_boundary_map(session: Session, version_id: int) -> dict[str, tuple[str, int, int]]:
    rows = session.execute(
        select(
            CallsignPrefix.prefix_pattern,
            ContestEntity.authority_code,
            CQZoneModel.code,
            ITUZone.code,
        )
        .join(PrefixEntityAssignment, PrefixEntityAssignment.prefix_id == CallsignPrefix.id)
        .join(ContestEntity, ContestEntity.id == PrefixEntityAssignment.entity_id)
        .join(PrefixCQZoneAssignment, PrefixCQZoneAssignment.prefix_id == CallsignPrefix.id)
        .join(CQZoneModel, CQZoneModel.id == PrefixCQZoneAssignment.cq_zone_id)
        .join(PrefixITUZoneAssignment, PrefixITUZoneAssignment.prefix_id == CallsignPrefix.id)
        .join(ITUZone, ITUZone.id == PrefixITUZoneAssignment.itu_zone_id)
        .where(CallsignPrefix.version_id == version_id)
    ).all()
    return {prefix: (entity, int(cq), int(itu)) for prefix, entity, cq, itu in rows}


def _has_boundary_changes(
    session: Session, current: MasterDataVersion, release: CTYRelease
) -> bool:
    prior = _active_boundary_map(session, current.id)
    for entity in release.entities:
        for prefix in entity.prefixes:
            prefix_key = ("=" if prefix.exact_callsign else "") + prefix.pattern
            old = prior.get(prefix_key)
            new = (entity.primary_prefix, prefix.cq_zone, prefix.itu_zone)
            if old is not None and old != new:
                return True
    return False


def _persist_release(
    session: Session, run: MasterDataSyncRun, release: CTYRelease
) -> MasterDataVersion:
    source = session.get(MasterDataSource, run.source_id)
    if source is not None:
        source.license_notice = release.license_notice
    current = session.scalar(
        select(MasterDataVersion).where(
            MasterDataVersion.dataset_key == DATASET_KEY,
            MasterDataVersion.status == MasterDataVersionStatus.ACTIVE,
        )
    )
    existing_candidate = session.scalar(
        select(MasterDataVersion).where(
            MasterDataVersion.dataset_key == DATASET_KEY,
            MasterDataVersion.checksum == release.normalized_checksum,
            MasterDataVersion.status == MasterDataVersionStatus.CANDIDATE,
        )
    )
    run.retrieved_at = release.retrieved_at
    run.source_url = release.archive_url
    run.source_release = release.release
    run.checksum = release.archive_sha256
    run.record_counts = {
        "entities": len(release.entities),
        "prefixes": sum(len(entity.prefixes) for entity in release.entities),
    }

    if current is not None and current.checksum == release.normalized_checksum:
        run.status = MasterDataRunStatus.SUCCEEDED
        run.change_detected = False
        run.finished_at = utc_now()
        return current
    if existing_candidate is not None:
        run.status = MasterDataRunStatus.SUCCEEDED
        run.change_detected = False
        run.finished_at = utc_now()
        return existing_candidate

    boundary_review = current is not None and _has_boundary_changes(session, current, release)
    if current is not None and not boundary_review:
        if release.retrieved_at <= current.valid_from:
            raise MasterDataError("A new active version must begin after the current version")
        current.status = MasterDataVersionStatus.RETIRED
        current.valid_to = release.retrieved_at
    version = MasterDataVersion(
        sync_run_id=run.id,
        dataset_key=DATASET_KEY,
        source_release=release.release,
        retrieved_at=release.retrieved_at,
        checksum=release.normalized_checksum,
        activated_at=None if boundary_review else release.retrieved_at,
        valid_from=release.retrieved_at,
        valid_to=None,
        status=(
            MasterDataVersionStatus.CANDIDATE if boundary_review else MasterDataVersionStatus.ACTIVE
        ),
    )
    session.add(version)
    session.flush()

    cq_codes = sorted(
        {entity.cq_zone for entity in release.entities}
        | {prefix.cq_zone for entity in release.entities for prefix in entity.prefixes}
    )
    itu_codes = sorted(
        {entity.itu_zone for entity in release.entities}
        | {prefix.itu_zone for entity in release.entities for prefix in entity.prefixes}
    )
    cq_rows = {
        code: CQZone(version_id=version.id, code=str(code), name=f"CQ Zone {code}")
        for code in cq_codes
    }
    itu_rows = {
        code: ITUZone(version_id=version.id, code=str(code), name=f"ITU Zone {code}")
        for code in itu_codes
    }
    session.add_all([*cq_rows.values(), *itu_rows.values()])
    session.flush()

    run.change_detected = True
    entity_values = [
        {
            "version_id": version.id,
            "namespace": "CTY",
            "authority_code": entity_data.primary_prefix,
            "name": entity_data.name,
            "entity_type": EntityType.AWARD_ENTITY,
            "continent": entity_data.continent,
            "latitude": entity_data.latitude,
            "longitude": entity_data.longitude,
            "utc_offset": entity_data.utc_offset,
        }
        for entity_data in release.entities
    ]
    entity_ids = (
        session.execute(insert(ContestEntity).returning(ContestEntity.id), entity_values)
        .scalars()
        .all()
    )
    entity_assignments_cq = []
    entity_assignments_itu = []
    prefix_rows = []
    for entity_id, entity_data in zip(entity_ids, release.entities, strict=True):
        entity_assignments_cq.append(
            {
                "version_id": version.id,
                "entity_id": entity_id,
                "cq_zone_id": cq_rows[entity_data.cq_zone].id,
            }
        )
        entity_assignments_itu.append(
            {
                "version_id": version.id,
                "entity_id": entity_id,
                "itu_zone_id": itu_rows[entity_data.itu_zone].id,
            }
        )
        prefix_rows.extend((entity_id, prefix_data) for prefix_data in entity_data.prefixes)
    session.execute(insert(EntityCQZoneAssignment), entity_assignments_cq)
    session.execute(insert(EntityITUZoneAssignment), entity_assignments_itu)
    prefix_values = [
        {
            "version_id": version.id,
            "prefix_pattern": ("=" if prefix_data.exact_callsign else "") + prefix_data.pattern,
            "allocation_type": "exact_callsign" if prefix_data.exact_callsign else "prefix",
            "continent_override": prefix_data.continent,
            "latitude_override": prefix_data.latitude,
            "longitude_override": prefix_data.longitude,
            "utc_offset_override": prefix_data.utc_offset,
        }
        for _, prefix_data in prefix_rows
    ]
    prefix_ids = (
        session.execute(insert(CallsignPrefix).returning(CallsignPrefix.id), prefix_values)
        .scalars()
        .all()
    )
    prefix_assignments_entity = []
    prefix_assignments_cq = []
    prefix_assignments_itu = []
    for (entity_id, prefix_data), prefix_id in zip(prefix_rows, prefix_ids, strict=True):
        note = f"Big CTY {release.release}"
        prefix_assignments_entity.append(
            {
                "version_id": version.id,
                "prefix_id": prefix_id,
                "entity_id": entity_id,
                "source_note": note,
            }
        )
        prefix_assignments_cq.append(
            {
                "version_id": version.id,
                "prefix_id": prefix_id,
                "cq_zone_id": cq_rows[prefix_data.cq_zone].id,
                "override_note": note,
            }
        )
        prefix_assignments_itu.append(
            {
                "version_id": version.id,
                "prefix_id": prefix_id,
                "itu_zone_id": itu_rows[prefix_data.itu_zone].id,
                "override_note": note,
            }
        )
    session.execute(insert(PrefixEntityAssignment), prefix_assignments_entity)
    session.execute(insert(PrefixCQZoneAssignment), prefix_assignments_cq)
    session.execute(insert(PrefixITUZoneAssignment), prefix_assignments_itu)
    run.status = MasterDataRunStatus.SUCCEEDED
    run.finished_at = utc_now()
    run.error_summary = (
        "Candidate requires global administrator review because an existing callsign prefix "
        "changed contest entity or zone assignment."
        if boundary_review
        else None
    )
    return version


def sync_cty(
    session_factory: sessionmaker[Session], fetch_archive: FetchArchive = fetch_latest_archive
) -> dict[str, int | str | bool | None]:
    """Fetch, validate, and transactionally import Big CTY; safe to retry after failure."""
    run_id = _create_run(session_factory)
    try:
        archive_bytes, release_date, archive_url, retrieved_at = fetch_archive()
        release = parse_archive(archive_bytes, release_date, archive_url, retrieved_at)
        with session_factory.begin() as session:
            run = session.get(MasterDataSyncRun, run_id)
            if run is None:
                raise MasterDataError(f"Sync run {run_id} disappeared")
            version = _persist_release(session, run, release)
            version_id = version.id if version else None
            status = run.status.value
            changed = run.change_detected
            counts = dict(run.record_counts)
        logger.info(
            "master_data_sync_finished",
            extra={
                "run_id": run_id,
                "status": status,
                "changed": changed,
                "version_id": version_id,
            },
        )
        return {
            "run_id": run_id,
            "status": status,
            "changed": changed,
            "version_id": version_id,
            **counts,
        }
    except Exception as exc:
        _finish_failed(session_factory, run_id, exc)
        logger.exception("master_data_sync_failed", extra={"run_id": run_id})
        raise


def sync_ungegn_countries(
    session_factory: sessionmaker[Session], fetch_data=fetch_countries
) -> dict[str, int | str | bool | None]:
    """Refresh the UNGEGN WGN reference for UN member-country names and M49 codes."""
    run_id = _create_ungegn_run(session_factory)
    try:
        source_data = fetch_data()
        with session_factory.begin() as session:
            run = session.get(MasterDataSyncRun, run_id)
            if run is None:
                raise MasterDataError(f"UNGEGN WGN sync run {run_id} disappeared")
            version = _persist_ungegn_data(session, run, source_data)
            result = {
                "run_id": run_id,
                "status": run.status.value,
                "changed": run.change_detected,
                "version_id": version.id,
                **run.record_counts,
            }
        logger.info("ungegn_wgn_master_data_sync_finished", extra=result)
        return result
    except Exception as exc:
        _finish_failed(session_factory, run_id, exc)
        logger.exception("ungegn_wgn_master_data_sync_failed", extra={"run_id": run_id})
        raise


def sync_m49_country_areas(
    session_factory: sessionmaker[Session], fetch_data=fetch_country_areas
) -> dict[str, int | str | bool | None]:
    """Refresh the official UNSD M49 country-or-area reference as published."""
    run_id = _create_m49_run(session_factory)
    try:
        source_data = fetch_data()
        with session_factory.begin() as session:
            run = session.get(MasterDataSyncRun, run_id)
            if run is None:
                raise MasterDataError(f"UN M49 sync run {run_id} disappeared")
            version = _persist_m49_data(session, run, source_data)
            result = {
                "run_id": run_id,
                "status": run.status.value,
                "changed": run.change_detected,
                "version_id": version.id,
                **run.record_counts,
            }
        logger.info("unsd_m49_master_data_sync_finished", extra=result)
        return result
    except Exception as exc:
        _finish_failed(session_factory, run_id, exc)
        logger.exception("unsd_m49_master_data_sync_failed", extra={"run_id": run_id})
        raise


def activate_candidate(
    session: Session, version_id: int, activated_at: datetime | None = None
) -> MasterDataVersion:
    """Activate a validated candidate and preserve the previous version interval."""
    moment = activated_at or utc_now()
    candidate = session.get(MasterDataVersion, version_id)
    if candidate is None or candidate.status != MasterDataVersionStatus.CANDIDATE:
        raise MasterDataError("Only an existing candidate master-data version can be activated")
    current = session.scalar(
        select(MasterDataVersion).where(
            MasterDataVersion.dataset_key == candidate.dataset_key,
            MasterDataVersion.status == MasterDataVersionStatus.ACTIVE,
        )
    )
    if current is not None:
        if moment <= current.valid_from:
            raise MasterDataError("Candidate activation must occur after the active version began")
        current.status = MasterDataVersionStatus.RETIRED
        current.valid_to = moment
    candidate.status = MasterDataVersionStatus.ACTIVE
    candidate.valid_from = moment
    candidate.valid_to = None
    candidate.activated_at = moment
    session.flush()
    return candidate


def pin_contest_versions(
    session: Session,
    contest_id: int,
    required_datasets: Iterable[str],
    now: datetime | None = None,
) -> list[ContestMasterDataVersion]:
    """Pin each required version whose UTC effective interval contains contest start."""
    contest = session.get(Contest, contest_id)
    if contest is None:
        raise MasterDataError(f"Contest {contest_id} does not exist")
    moment = now or utc_now()
    if moment < contest.starts_at:
        raise MasterDataError("Master-data versions can be pinned only after contest start")
    dataset_keys = tuple(sorted(set(required_datasets)))
    existing = list(
        session.scalars(
            select(ContestMasterDataVersion)
            .where(ContestMasterDataVersion.contest_id == contest_id)
            .order_by(ContestMasterDataVersion.dataset_key)
        )
    )
    if existing:
        existing_keys = {item.dataset_key for item in existing}
        if existing_keys != set(dataset_keys):
            raise ContestMasterDataAlreadyPinned(
                "Contest already has a different master-data dataset set pinned"
            )
        return existing

    matches: dict[str, MasterDataVersion] = {}
    missing: list[str] = []
    for dataset in dataset_keys:
        versions = list(
            session.scalars(
                select(MasterDataVersion).where(
                    MasterDataVersion.dataset_key == dataset,
                    MasterDataVersion.valid_from <= contest.starts_at,
                    (MasterDataVersion.valid_to.is_(None))
                    | (MasterDataVersion.valid_to > contest.starts_at),
                    MasterDataVersion.status.in_(
                        [MasterDataVersionStatus.ACTIVE, MasterDataVersionStatus.RETIRED]
                    ),
                )
            )
        )
        if len(versions) != 1:
            missing.append(dataset)
        else:
            matches[dataset] = versions[0]
    if missing:
        raise MissingContestMasterData(missing)
    selected = [
        ContestMasterDataVersion(
            contest_id=contest_id,
            dataset_key=dataset,
            master_data_version_id=matches[dataset].id,
            pinned_at=moment,
        )
        for dataset in dataset_keys
    ]
    session.add_all(selected)
    session.flush()
    return selected


def add_pins_to_score_run(session: Session, score_run_id: int, contest_id: int) -> None:
    """Copy the contest's immutable dataset selection into the score-run audit record."""
    pins = session.scalars(
        select(ContestMasterDataVersion).where(ContestMasterDataVersion.contest_id == contest_id)
    ).all()
    if not pins:
        raise MissingContestMasterData(["contest pins"])
    from backend.app.models.master_data import ScoreRunMasterDataVersion

    session.add_all(
        [
            ScoreRunMasterDataVersion(
                score_run_id=score_run_id,
                dataset_key=pin.dataset_key,
                master_data_version_id=pin.master_data_version_id,
            )
            for pin in pins
        ]
    )
    session.flush()
