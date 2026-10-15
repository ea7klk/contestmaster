"""ORM-backed score run orchestration; the actual scoring stays in the pure rule engine."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import UTC
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.adjudication.domain import (
    CtyCallsignMatch,
    QsoFacts,
    match_counterpart,
    normalize_callsign,
    resolve_cty_callsign,
)
from backend.app.master_data.jobs import MissingContestMasterData
from backend.app.metrics import record_score_run
from backend.app.models import (
    Contest,
    ContestMasterDataVersion,
    Entry,
    EntryRevision,
    MasterDataVersion,
    MasterDataVersionStatus,
    Qso,
    QsoDecision,
    QsoDecisionSource,
    QsoDecisionStatus,
    QsoScore,
    RulesetVersion,
    ScoreRun,
    ScoreRunStatus,
    Station,
)
from backend.app.models.master_data import ScoreRunMasterDataVersion
from backend.app.models.types import utc_now
from backend.app.rulesets.engine import ScoringEntry, ScoringQso, score_entry
from backend.app.rulesets.persistence import load_ruleset_version
from backend.app.rulesets.schema import ExchangeRule, FormatMappingRule, RulesetDefinition

logger = logging.getLogger("contestmaster.adjudication")


class ScoreRunError(ValueError):
    """A score run cannot execute against the requested contest snapshot."""


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _claimed_points(revision: EntryRevision) -> int | None:
    headers = revision.import_metadata.get("headers", {})
    if not isinstance(headers, dict):
        return None
    raw = next(
        (
            values[0]
            for key, values in headers.items()
            if key.casefold() == "claimed-score" and isinstance(values, list) and values
        ),
        None,
    )
    if not isinstance(raw, str) or not re.fullmatch(r"[0-9]+", raw.strip()):
        return None
    return int(raw.strip())


def _required_datasets(definition) -> set[str]:
    """Identify CTY dependencies only when configured scoring facts consume geography."""
    geographic = {"entity", "cq_zone", "itu_zone", "continent"}
    for configured in definition.rules:
        rule = configured.rule
        if getattr(rule, "fact", None) in geographic:
            return {"cty"}
        source_fact = getattr(rule, "source_fact", "")
        if set(source_fact.split(".")) & geographic:
            return {"cty"}
        for condition in (configured.when, getattr(rule, "eligible_if", None)):
            if condition is not None and _condition_uses_geography(condition):
                return {"cty"}
    return set()


def _condition_uses_geography(condition) -> bool:
    if getattr(condition, "kind", None) == "compare":
        return bool(set(condition.fact.split(".")) & {"entity", "cq_zone", "itu_zone", "continent"})
    if getattr(condition, "kind", None) == "not":
        return _condition_uses_geography(condition.condition)
    return any(_condition_uses_geography(item) for item in getattr(condition, "conditions", []))


def _contest_snapshot(session: Session, contest: Contest, definition) -> list[tuple[str, int]]:
    pins = list(
        session.scalars(
            select(ContestMasterDataVersion)
            .where(ContestMasterDataVersion.contest_id == contest.id)
            .order_by(ContestMasterDataVersion.dataset_key)
        )
    )
    by_key = {item.dataset_key: item for item in pins}
    required = _required_datasets(definition)
    if required - by_key.keys():
        raise MissingContestMasterData(required - by_key.keys())
    for key in required:
        pin = by_key[key]
        version = session.get(MasterDataVersion, pin.master_data_version_id)
        if (
            version is None
            or version.dataset_key != key
            or version.status
            not in {MasterDataVersionStatus.ACTIVE, MasterDataVersionStatus.RETIRED}
            or version.valid_from > contest.starts_at
            or (version.valid_to is not None and version.valid_to <= contest.starts_at)
        ):
            raise MissingContestMasterData([key])
    return [(item.dataset_key, item.master_data_version_id) for item in pins]


def _scoring_inputs(
    session: Session,
    entry: Entry,
    revision: EntryRevision,
    cty_mappings: list[CtyCallsignMatch],
    cty_version_id: int | None,
    exchange_rule: ExchangeRule | None,
    declarations: dict[str, Any],
) -> tuple[ScoringEntry, list[Qso], list[QsoFacts]]:
    station = session.scalar(select(Station).where(Station.entry_revision_id == revision.id))
    if station is None:
        raise ScoreRunError("Entry revision is missing its station record.")
    qsos = list(
        session.scalars(select(Qso).where(Qso.entry_revision_id == revision.id).order_by(Qso.id))
    )
    source_facts: list[QsoFacts] = []
    scoring_qsos: list[ScoringQso] = []
    for qso in qsos:
        callsign = normalize_callsign(qso.callsign_submitted)
        # Import-time resolutions are trusted only when they use the contest-pinned CTY version.
        entity = cq_zone = itu_zone = continent = None
        if cty_version_id and qso.resolved_master_data_version_id == cty_version_id:
            from backend.app.models.master_data import ContestEntity, CQZone, ITUZone

            entity_row = (
                session.get(ContestEntity, qso.worked_entity_id) if qso.worked_entity_id else None
            )
            cq_row = session.get(CQZone, qso.worked_cq_zone_id) if qso.worked_cq_zone_id else None
            itu_row = (
                session.get(ITUZone, qso.worked_itu_zone_id) if qso.worked_itu_zone_id else None
            )
            entity = entity_row.authority_code if entity_row else None
            continent = entity_row.continent if entity_row else None
            cq_zone = cq_row.code if cq_row else None
            itu_zone = itu_row.code if itu_row else None
        if cty_version_id:
            mapping = resolve_cty_callsign(callsign, cty_mappings)
            if mapping is not None:
                entity = entity or mapping.entity
                cq_zone = cq_zone or mapping.cq_zone
                itu_zone = itu_zone or mapping.itu_zone
                continent = continent or mapping.continent
        sent_exchange = _exchange_values(
            qso.exchange_sent_normalized or qso.exchange_sent_submitted,
            exchange_rule,
            direction="sent",
        )
        received_exchange = _exchange_values(
            qso.exchange_received_normalized or qso.exchange_received_submitted,
            exchange_rule,
            direction="received",
        )
        occurred = qso.occurred_at.astimezone(UTC)
        scoring_qsos.append(
            ScoringQso(
                qso_id=qso.id,
                occurred_at=occurred,
                worked_callsign=callsign,
                band=qso.band,
                mode=qso.mode,
                entity=entity,
                cq_zone=cq_zone,
                itu_zone=itu_zone,
                continent=continent,
                sent_exchange=sent_exchange,
                received_exchange=received_exchange,
            )
        )
        source_facts.append(
            QsoFacts(
                qso_id=qso.id,
                occurred_at=occurred,
                station_callsign=station.callsign_normalized or station.callsign_submitted,
                worked_callsign=callsign,
                band=qso.band,
                mode=qso.mode,
                sent_exchange=sent_exchange,
                received_exchange=received_exchange,
            )
        )
    entry_input = ScoringEntry(
        entry_id=entry.id,
        station_callsign=station.callsign_normalized or station.callsign_submitted,
        categories=entry.category_values,
        declarations=declarations,
        qsos=scoring_qsos,
    )
    return entry_input, qsos, source_facts


def _entry_declarations(definition: RulesetDefinition, revision: EntryRevision) -> dict[str, Any]:
    headers = revision.import_metadata.get("headers", {})
    if not isinstance(headers, dict):
        return {}
    by_name = {str(key).casefold(): value for key, value in headers.items()}
    mapping_rule = next(
        (
            configured.rule
            for configured in definition.rules
            if isinstance(configured.rule, FormatMappingRule)
            and configured.rule.format == "cabrillo"
        ),
        None,
    )
    header_fields = mapping_rule.header_fields if mapping_rule else {}
    declarations: dict[str, Any] = {}
    for configured in definition.rules:
        if not isinstance(configured.rule, ExchangeRule):
            continue
        for field in configured.rule.fields:
            if field.direction != "entry":
                continue
            source_name = header_fields.get(field.key, field.key).casefold()
            values = by_name.get(source_name)
            if isinstance(values, list) and values:
                declarations[field.key] = values[0]
    return declarations


def _exchange_values(
    stored: dict[str, Any], exchange_rule: ExchangeRule | None, *, direction: str
) -> dict[str, Any]:
    """Map Cabrillo's raw exchange tokens onto configured semantic field names."""
    result: dict[str, Any] = {}
    raw = stored.get("raw")
    if exchange_rule is not None and isinstance(raw, str):
        fields = [field for field in exchange_rule.fields if field.direction in {direction, "both"}]
        tokens = raw.split()
        if len(fields) == 1:
            tokens = [raw]
        if len(tokens) == len(fields):
            for field, token in zip(fields, tokens, strict=True):
                if field.value_type in {"integer", "serial"} and token.isdecimal():
                    result[field.key] = int(token)
                else:
                    result[field.key] = token.strip().upper()
        else:
            # Preserve unmapped data so validation can report/review it; never guess
            # which token belongs to which configured field.
            result["raw"] = raw
    elif raw is not None:
        result["raw"] = raw
    if stored.get("rst") is not None:
        result["rst"] = stored["rst"]
    for key, value in stored.items():
        if key not in {"raw", "rst"}:
            result.setdefault(key, value)
    return result


def _load_cty_mappings(session: Session, version_id: int | None) -> list[CtyCallsignMatch]:
    if version_id is None:
        return []
    from backend.app.models.master_data import (
        CallsignPrefix,
        ContestEntity,
        CQZone,
        ITUZone,
        PrefixCQZoneAssignment,
        PrefixEntityAssignment,
        PrefixITUZoneAssignment,
    )

    rows = session.execute(
        select(
            CallsignPrefix.prefix_pattern,
            ContestEntity.authority_code,
            CQZone.code,
            ITUZone.code,
            ContestEntity.continent,
        )
        .join(
            PrefixEntityAssignment,
            (PrefixEntityAssignment.prefix_id == CallsignPrefix.id)
            & (PrefixEntityAssignment.version_id == version_id),
        )
        .join(ContestEntity, ContestEntity.id == PrefixEntityAssignment.entity_id)
        .outerjoin(
            PrefixCQZoneAssignment,
            (PrefixCQZoneAssignment.prefix_id == CallsignPrefix.id)
            & (PrefixCQZoneAssignment.version_id == version_id),
        )
        .outerjoin(CQZone, CQZone.id == PrefixCQZoneAssignment.cq_zone_id)
        .outerjoin(
            PrefixITUZoneAssignment,
            (PrefixITUZoneAssignment.prefix_id == CallsignPrefix.id)
            & (PrefixITUZoneAssignment.version_id == version_id),
        )
        .outerjoin(ITUZone, ITUZone.id == PrefixITUZoneAssignment.itu_zone_id)
        .where(CallsignPrefix.version_id == version_id)
        .order_by(CallsignPrefix.id)
    )
    return [CtyCallsignMatch(*row) for row in rows]


def _latest_decisions(session: Session, qso_ids: list[int]) -> dict[int, QsoDecision]:
    decisions = (
        session.scalars(
            select(QsoDecision).where(QsoDecision.qso_id.in_(qso_ids)).order_by(QsoDecision.id)
        )
        if qso_ids
        else []
    )
    latest: dict[int, QsoDecision] = {}
    latest_manual: dict[int, QsoDecision] = {}
    for decision in decisions:
        latest[decision.qso_id] = decision
        if decision.source is not QsoDecisionSource.AUTOMATED:
            latest_manual[decision.qso_id] = decision
    return {**latest, **latest_manual}


def _cross_log_options(definition) -> tuple[bool, int, dict[str, int]] | None:
    for configured in definition.rules:
        rule = configured.rule
        if rule.kind != "workflow_hook" or rule.stage != "cross_log":
            continue
        parameters = rule.parameters
        tolerance = parameters.get("timestamp_tolerance_seconds", 300)
        numeric = parameters.get("numeric_exchange_tolerances", {})
        if type(tolerance) is not int or tolerance < 0 or not isinstance(numeric, dict):
            raise ScoreRunError("Cross-log tolerance configuration is invalid.")
        if any(type(value) is not int or value < 0 for value in numeric.values()):
            raise ScoreRunError("Cross-log exchange tolerances must be nonnegative integers.")
        return parameters.get("require_counterpart") is True, tolerance, numeric
    return None


def score_entry_revision(
    session: Session,
    *,
    entry_id: int,
    revision_id: int,
    idempotency_key: str,
    created_by_user_id: int | None = None,
    claimed_points: int | None = None,
) -> ScoreRun:
    """Create an immutable score snapshot for exactly one input revision."""
    if claimed_points is not None and (type(claimed_points) is not int or claimed_points < 0):
        raise ScoreRunError("Claimed score must be a nonnegative integer.")
    idempotency_digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
    existing = session.scalar(
        select(ScoreRun).where(ScoreRun.idempotency_key == idempotency_digest)
    )
    if existing is not None and existing.status in {
        ScoreRunStatus.COMPLETED,
        ScoreRunStatus.RUNNING,
    }:
        return existing
    entry = session.get(Entry, entry_id)
    revision = session.get(EntryRevision, revision_id)
    if entry is None or revision is None or revision.entry_id != entry_id:
        raise ScoreRunError("Entry revision was not found.")
    contest = session.get(Contest, entry.contest_id)
    if contest is None or contest.ruleset_version_id is None:
        raise ScoreRunError("Contest has no active ruleset version.")
    ruleset_row = session.get(RulesetVersion, contest.ruleset_version_id)
    if ruleset_row is None:
        raise ScoreRunError("Contest ruleset version is unavailable.")
    definition = load_ruleset_version(ruleset_row)
    exchange_rule = next(
        (
            configured.rule
            for configured in definition.rules
            if isinstance(configured.rule, ExchangeRule)
        ),
        None,
    )
    master_versions = _contest_snapshot(session, contest, definition)
    snapshot_ids = dict(master_versions)
    cty_version_id = snapshot_ids.get("cty")
    cty_mappings = _load_cty_mappings(session, cty_version_id)
    declarations = _entry_declarations(definition, revision)

    input_entry, revision_qsos, qso_facts = _scoring_inputs(
        session, entry, revision, cty_mappings, cty_version_id, exchange_rule, declarations
    )
    qso_ids = [qso.id for qso in revision_qsos]
    latest = _latest_decisions(session, qso_ids)
    overrides = {
        qso_id: {"status": decision.status.value, "reason_code": decision.reason_code}
        for qso_id, decision in latest.items()
        if decision.source is not QsoDecisionSource.AUTOMATED
    }

    cross_log = _cross_log_options(definition)
    cross_log_findings: dict[int, Any] = {}
    counterpart_revisions: list[tuple[int, int, str]] = []
    if cross_log:
        require_counterpart, time_tolerance, numeric_tolerances = cross_log
        other_facts: list[QsoFacts] = []
        for other_entry in session.scalars(
            select(Entry).where(Entry.contest_id == contest.id, Entry.id != entry.id)
        ):
            other_revision = session.scalar(
                select(EntryRevision)
                .where(EntryRevision.entry_id == other_entry.id)
                .order_by(EntryRevision.revision_number.desc())
                .limit(1)
            )
            if other_revision is not None:
                counterpart_revisions.append(
                    (other_entry.id, other_revision.id, other_revision.content_sha256)
                )
                _other_input, _other_qsos, candidate_facts = _scoring_inputs(
                    session,
                    other_entry,
                    other_revision,
                    cty_mappings,
                    cty_version_id,
                    exchange_rule,
                    _entry_declarations(definition, other_revision),
                )
                other_facts.extend(candidate_facts)
        for qso in qso_facts:
            finding = match_counterpart(
                qso,
                [*qso_facts, *other_facts],
                timestamp_tolerance_seconds=time_tolerance,
                numeric_exchange_tolerances=numeric_tolerances,
            )
            cross_log_findings[qso.qso_id] = finding
            if require_counterpart and finding.reason_code != "counterpart_match":
                overrides.setdefault(
                    qso.qso_id,
                    {"status": finding.status, "reason_code": finding.reason_code},
                )

    previous_number = (
        session.scalar(
            select(func.max(ScoreRun.run_number)).where(ScoreRun.entry_revision_id == revision.id)
        )
        or 0
    )
    input_digest = _canonical_digest(
        {
            "revision": revision.content_sha256,
            "ruleset": ruleset_row.configuration,
            "decisions": [
                {"qso_id": key, "decision_id": value.id, "status": value.status.value}
                for key, value in sorted(latest.items())
                if value.source is not QsoDecisionSource.AUTOMATED
            ],
            "master_data": master_versions,
            "counterpart_revisions": sorted(counterpart_revisions),
        }
    )
    run = existing or ScoreRun(
        entry_id=entry.id,
        entry_revision_id=revision.id,
        ruleset_version_id=ruleset_row.id,
        master_data_version_id=cty_version_id,
        run_number=previous_number + 1,
        idempotency_key=idempotency_digest,
        status=ScoreRunStatus.QUEUED,
        input_digest=input_digest,
        ruleset_snapshot=ruleset_row.configuration,
        master_data_snapshot={key: version_id for key, version_id in master_versions} or None,
        claimed_points=claimed_points,
        created_by_user_id=created_by_user_id,
    )
    if existing is None:
        session.add(run)
    else:
        run.status = ScoreRunStatus.QUEUED
        run.started_at = None
        run.completed_at = None
        run.input_digest = input_digest
        run.ruleset_version_id = ruleset_row.id
        run.master_data_version_id = cty_version_id
        run.ruleset_snapshot = ruleset_row.configuration
        run.master_data_snapshot = {key: version_id for key, version_id in master_versions} or None
        run.claimed_points = claimed_points
        run.created_by_user_id = created_by_user_id
        # A failed attempt may have committed no score rows; if it did, do not mutate it.
        if session.scalar(select(QsoScore.id).where(QsoScore.score_run_id == run.id)) is not None:
            raise ScoreRunError("A failed score run with details cannot be retried in place.")
    session.flush()
    run.status = ScoreRunStatus.RUNNING
    run.started_at = utc_now()
    session.flush()
    if master_versions:
        # Persist the exact contest pins on each score run before scoring.
        session.add_all(
            ScoreRunMasterDataVersion(
                score_run_id=run.id,
                dataset_key=key,
                master_data_version_id=version_id,
            )
            for key, version_id in master_versions
        )
        session.flush()
    result = score_entry(
        definition,
        input_entry,
        contest_starts_at=contest.starts_at,
        contest_ends_at=contest.ends_at,
        qso_overrides=overrides,
    )
    run.points = result.points_total
    run.multiplier_count = result.multiplier_count
    run.bonus_points = result.bonus_points
    run.penalty_points = result.penalty_points
    run.final_score = result.final_score
    run.adjudicated_score = None
    if any(decision.source is not QsoDecisionSource.AUTOMATED for decision in latest.values()):
        run.adjudicated_score = result.final_score
    if run.claimed_points is None:
        run.claimed_points = (
            claimed_points if claimed_points is not None else _claimed_points(revision)
        )
    explanation = {
        "outcome": result.outcome,
        "summary": result.explanation,
        "review_reasons": result.review_reasons,
        "workflow_actions": [item.model_dump(mode="json") for item in result.workflow_actions],
        "cross_log": {
            str(key): {
                "status": value.status,
                "reason_code": value.reason_code,
                "reason": value.reason,
                "evidence": value.evidence,
            }
            for key, value in cross_log_findings.items()
        },
    }
    run.explanation = explanation
    session.flush()
    for score in result.qso_scores:
        finding = cross_log_findings.get(score.qso_id)
        reasons = list(score.reasons)
        status = score.status
        if finding:
            reasons.append(finding.reason_code)
            if cross_log is not None and cross_log[0]:
                if finding.reason_code != "counterpart_match":
                    status = finding.status
        session.add(
            QsoScore(
                score_run_id=run.id,
                qso_id=score.qso_id,
                entry_revision_id=revision.id,
                credited=status == "credited",
                points=score.points if status == "credited" else 0,
                bonus_points=score.bonus_points,
                penalty_points=score.penalty_points,
                multiplier_count=len(score.multiplier_keys) if status == "credited" else 0,
                multiplier_keys=score.multiplier_keys if status == "credited" else [],
                status=status,
                reason_codes=reasons,
                explanation="; ".join(reasons)
                if reasons
                else "Credited under the configured ruleset.",
            )
        )
        if finding:
            session.add(
                QsoDecision(
                    qso_id=score.qso_id,
                    status=QsoDecisionStatus(finding.status),
                    source=QsoDecisionSource.AUTOMATED,
                    reason_code=finding.reason_code,
                    reason=finding.reason,
                    evidence=finding.evidence,
                )
            )
        elif score.reasons:
            session.add(
                QsoDecision(
                    qso_id=score.qso_id,
                    status=QsoDecisionStatus(score.status),
                    source=QsoDecisionSource.AUTOMATED,
                    reason_code=score.reasons[0],
                    reason="Automated QSO validation produced the recorded scoring findings.",
                    evidence={"reason_codes": score.reasons},
                )
            )
    session.flush()
    run.status = ScoreRunStatus.COMPLETED
    run.completed_at = utc_now()
    session.flush()
    record_score_run("completed")
    return run


def recalculate_contest(
    session: Session, contest_id: int, *, trigger_key: str, created_by_user_id: int | None = None
) -> list[ScoreRun]:
    """Recalculate each entry's latest accepted revision once for a committed trigger."""
    contest = session.get(Contest, contest_id)
    if contest is None:
        raise ScoreRunError("Contest was not found.")
    entries = list(
        session.scalars(select(Entry).where(Entry.contest_id == contest_id).order_by(Entry.id))
    )
    runs = []
    for entry in entries:
        revision = session.scalar(
            select(EntryRevision)
            .where(EntryRevision.entry_id == entry.id)
            .order_by(EntryRevision.revision_number.desc())
            .limit(1)
        )
        if revision is None:
            continue
        key = f"{trigger_key}:entry:{entry.id}:revision:{revision.id}"
        operation_id = str(uuid4())
        event_fields = {
            "operation_id": operation_id,
            "contest_id": contest_id,
            "entry_id": entry.id,
            "revision_id": revision.id,
        }
        logger.info("score_run_started", extra=event_fields)
        try:
            with session.begin_nested():
                run = score_entry_revision(
                    session,
                    entry_id=entry.id,
                    revision_id=revision.id,
                    idempotency_key=key,
                    created_by_user_id=created_by_user_id,
                )
            runs.append(run)
            logger.info(
                "score_run_finished",
                extra={**event_fields, "score_run_id": run.id, "status": run.status.value},
            )
        except Exception as exc:
            logger.exception("score_run_failed", extra=event_fields)
            failed_run = _record_failed_run(session, entry, revision, key, exc, created_by_user_id)
            runs.append(failed_run)
            logger.info(
                "score_run_finished",
                extra={
                    **event_fields,
                    "score_run_id": failed_run.id,
                    "status": failed_run.status.value,
                },
            )
    return runs


def _record_failed_run(
    session: Session,
    entry: Entry,
    revision: EntryRevision,
    key: str,
    error: Exception,
    created_by_user_id: int | None,
) -> ScoreRun:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    run = session.scalar(select(ScoreRun).where(ScoreRun.idempotency_key == digest))
    if run is not None and run.status is ScoreRunStatus.COMPLETED:
        return run
    contest = session.get(Contest, entry.contest_id)
    if contest is None or contest.ruleset_version_id is None:
        raise ScoreRunError("Cannot record score failure without a contest ruleset.") from error
    version = session.get(RulesetVersion, contest.ruleset_version_id)
    if version is None:
        raise ScoreRunError(
            "Cannot record score failure because its ruleset is unavailable."
        ) from error
    if run is None:
        run_number = (
            session.scalar(
                select(func.max(ScoreRun.run_number)).where(
                    ScoreRun.entry_revision_id == revision.id
                )
            )
            or 0
        ) + 1
        run = ScoreRun(
            entry_id=entry.id,
            entry_revision_id=revision.id,
            ruleset_version_id=version.id,
            run_number=run_number,
            idempotency_key=digest,
            status=ScoreRunStatus.FAILED,
            input_digest=revision.content_sha256,
            ruleset_snapshot=version.configuration,
            master_data_snapshot={"error": str(error)},
            completed_at=utc_now(),
            created_by_user_id=created_by_user_id,
        )
        session.add(run)
    else:
        run.status = ScoreRunStatus.FAILED
        run.completed_at = utc_now()
        run.master_data_snapshot = {"error": str(error)}
    session.flush()
    record_score_run("failed")
    return run
