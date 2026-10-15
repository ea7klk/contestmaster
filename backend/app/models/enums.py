from enum import StrEnum


class SystemRole(StrEnum):
    GLOBAL_ADMINISTRATOR = "global_administrator"
    CONTEST_MANAGER = "contest_manager"


class ContestStatus(StrEnum):
    DRAFT = "draft"
    OPEN = "open"
    CLOSED = "closed"
    PUBLISHED = "published"


class EntryStatus(StrEnum):
    RECEIVED = "received"
    ACCEPTED = "accepted"
    CHECKLOG = "checklog"
    WITHDRAWN = "withdrawn"
    DISQUALIFIED = "disqualified"


class QsoDecisionStatus(StrEnum):
    CREDITED = "credited"
    NOT_CREDITED = "not_credited"
    NEEDS_REVIEW = "needs_review"


class QsoDecisionSource(StrEnum):
    AUTOMATED = "automated"
    CONTEST_MANAGER = "contest_manager"
    GLOBAL_ADMINISTRATOR = "global_administrator"


class ScoreRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class MasterDataAuthorityRole(StrEnum):
    PRIMARY_OPERATIONAL = "primary_operational"
    GOVERNING_AUTHORITY = "governing_authority"
    GAP_FILLING = "gap_filling"


class MasterDataRunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    VALIDATION_FAILED = "validation_failed"


class MasterDataVersionStatus(StrEnum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    RETIRED = "retired"
    REJECTED = "rejected"


class EntityType(StrEnum):
    SOVEREIGN_COUNTRY = "sovereign_country"
    TERRITORY = "territory"
    AWARD_ENTITY = "award_entity"
    CONTEST_ENTITY = "contest_entity"
    OTHER = "other"
