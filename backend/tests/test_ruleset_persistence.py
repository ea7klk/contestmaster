from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db import Base, build_engine
from backend.app.models import (
    Contest,
    RulesetActivation,
    SystemRole,
    SystemUser,
)
from backend.app.rulesets.persistence import (
    RulesetConflictError,
    activate_ruleset,
    load_ruleset_version,
    save_ruleset_version,
)
from backend.app.rulesets.schema import RulesetDefinition
from backend.app.rulesets.validation import validate_ruleset
from backend.tests.test_rulesets import valid_payload


@pytest.fixture
def session():
    engine = build_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db_session:
        yield db_session
    engine.dispose()


def create_actor_and_contest(session: Session) -> tuple[SystemUser, Contest]:
    actor = SystemUser(
        username="manager",
        email_normalized="manager@example.test",
        display_name="Contest Manager",
        role=SystemRole.CONTEST_MANAGER,
        password_hash="argon2id-hash",
    )
    session.add(actor)
    session.flush()
    contest = Contest(
        owner_user_id=actor.id,
        name="Ruleset Test",
        slug="ruleset-test",
        starts_at=datetime(2026, 1, 1, tzinfo=UTC),
        ends_at=datetime(2026, 1, 1, 2, tzinfo=UTC),
        log_submission_cutoff_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    session.add(contest)
    session.flush()
    return actor, contest


def test_ruleset_version_is_immutable_and_idempotent_by_key_and_version(session: Session):
    actor, _ = create_actor_and_contest(session)
    definition = validate_ruleset(valid_payload())

    first = save_ruleset_version(session, definition, created_by_user_id=actor.id)
    session.commit()
    second = save_ruleset_version(session, definition, created_by_user_id=actor.id)

    assert first.created is True
    assert second.created is False
    assert first.version.id == second.version.id
    loaded = load_ruleset_version(second.version)
    assert loaded.model_dump(mode="json") == definition.model_dump(mode="json")

    changed = definition.model_copy(update={"source_edition": "different edition"})
    with pytest.raises(RulesetConflictError, match="different content"):
        save_ruleset_version(session, changed, created_by_user_id=actor.id)


def test_activation_history_is_append_only_and_contest_keeps_selected_version(session: Session):
    actor, contest = create_actor_and_contest(session)
    first_definition = validate_ruleset(valid_payload())
    first = save_ruleset_version(session, first_definition, created_by_user_id=actor.id)
    session.flush()

    activation = activate_ruleset(
        session,
        contest_id=contest.id,
        ruleset_version_id=first.version.id,
        activated_by_user_id=actor.id,
    )
    assert activation is not None
    assert activation.configuration_sha256
    assert contest.ruleset_version_id == first.version.id
    assert (
        activate_ruleset(
            session,
            contest_id=contest.id,
            ruleset_version_id=first.version.id,
            activated_by_user_id=actor.id,
        )
        is None
    )

    second_payload = valid_payload()
    second_payload["version"] = "2027"
    second_definition: RulesetDefinition = validate_ruleset(second_payload)
    second = save_ruleset_version(session, second_definition, created_by_user_id=actor.id)
    session.flush()
    activate_ruleset(
        session,
        contest_id=contest.id,
        ruleset_version_id=second.version.id,
        activated_by_user_id=actor.id,
    )
    session.commit()

    history = list(
        session.scalars(
            select(RulesetActivation)
            .where(RulesetActivation.contest_id == contest.id)
            .order_by(RulesetActivation.id)
        )
    )
    assert [item.ruleset_version_id for item in history] == [first.version.id, second.version.id]
    assert contest.ruleset_version_id == second.version.id
    assert history[0].activated_by_user_id == actor.id
