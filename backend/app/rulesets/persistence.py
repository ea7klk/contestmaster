"""Immutable ruleset version persistence and per-contest activation history."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import Contest, RulesetActivation, RulesetVersion
from backend.app.models.types import utc_now
from backend.app.rulesets.schema import RulesetDefinition, rule_types_in
from backend.app.rulesets.validation import RulesetValidationError, validate_ruleset


class RulesetConflictError(ValueError):
    """A key/version pair already exists with different immutable configuration."""


class RulesetPersistenceError(ValueError):
    """A ruleset or contest reference needed for the operation is missing or invalid."""


@dataclass(frozen=True)
class PersistedRuleset:
    version: RulesetVersion
    created: bool


def _canonical_digest(configuration: dict[str, object]) -> str:
    encoded = json.dumps(configuration, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def save_ruleset_version(
    session: Session,
    definition: RulesetDefinition,
    *,
    created_by_user_id: int | None,
) -> PersistedRuleset:
    """Append a validated version; callers manage the short ORM transaction."""
    validated = validate_ruleset(definition.model_dump(mode="json"))
    configuration = validated.model_dump(mode="json")
    existing = session.scalar(
        select(RulesetVersion).where(
            RulesetVersion.ruleset_key == validated.ruleset_key,
            RulesetVersion.version == validated.version,
        )
    )
    if existing is not None:
        if (
            existing.configuration != configuration
            or existing.rule_type_keys != rule_types_in(validated)
            or existing.source_url != (str(validated.source_url) if validated.source_url else None)
            or existing.source_edition != validated.source_edition
        ):
            raise RulesetConflictError(
                f"Ruleset {validated.ruleset_key} version {validated.version} already exists "
                "with different content."
            )
        return PersistedRuleset(existing, created=False)

    version = RulesetVersion(
        ruleset_key=validated.ruleset_key,
        version=validated.version,
        source_url=str(validated.source_url) if validated.source_url else None,
        source_edition=validated.source_edition,
        rule_type_keys=rule_types_in(validated),
        configuration=configuration,
        created_by_user_id=created_by_user_id,
    )
    session.add(version)
    session.flush()
    return PersistedRuleset(version, created=True)


def load_ruleset_version(version: RulesetVersion) -> RulesetDefinition:
    """Revalidate stored JSON before execution; persisted configuration is untrusted input."""
    try:
        definition = validate_ruleset(version.configuration)
    except RulesetValidationError as exc:
        raise RulesetPersistenceError("Stored ruleset configuration is invalid.") from exc
    if definition.ruleset_key != version.ruleset_key or definition.version != version.version:
        raise RulesetPersistenceError("Stored ruleset metadata does not match its version row.")
    if definition.source_edition != version.source_edition:
        raise RulesetPersistenceError("Stored ruleset edition does not match its version row.")
    stored_source_url = str(definition.source_url) if definition.source_url else None
    if stored_source_url != version.source_url:
        raise RulesetPersistenceError("Stored ruleset source URL does not match its version row.")
    if rule_types_in(definition) != version.rule_type_keys:
        raise RulesetPersistenceError("Stored ruleset types do not match its version row.")
    return definition


def activate_ruleset(
    session: Session,
    *,
    contest_id: int,
    ruleset_version_id: int,
    activated_by_user_id: int | None,
) -> RulesetActivation | None:
    """Select an immutable version for a contest and append its activation event."""
    contest = session.get(Contest, contest_id)
    if contest is None:
        raise RulesetPersistenceError("Contest does not exist.")
    version = session.get(RulesetVersion, ruleset_version_id)
    if version is None:
        raise RulesetPersistenceError("Ruleset version does not exist.")
    load_ruleset_version(version)
    if contest.ruleset_version_id == version.id:
        return None

    contest.ruleset_version_id = version.id
    activation = RulesetActivation(
        contest_id=contest.id,
        ruleset_version_id=version.id,
        activated_by_user_id=activated_by_user_id,
        configuration_sha256=_canonical_digest(version.configuration),
        activated_at=utc_now(),
    )
    session.add(activation)
    session.flush()
    return activation
