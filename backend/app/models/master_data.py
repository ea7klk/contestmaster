from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db import Base
from backend.app.models.domain import enum_column
from backend.app.models.enums import (
    EntityType,
    MasterDataAuthorityRole,
    MasterDataRunStatus,
    MasterDataVersionStatus,
)
from backend.app.models.types import UTCDateTime, utc_now


class MasterDataSource(Base):
    __tablename__ = "master_data_sources"
    __table_args__ = (
        CheckConstraint("source_priority >= 0", name="source_priority_nonnegative"),
        CheckConstraint("length(trim(source_key)) > 0", name="source_key_not_blank"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    canonical_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    source_priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    authority_role: Mapped[MasterDataAuthorityRole] = mapped_column(
        enum_column(MasterDataAuthorityRole, "master_data_authority_role"), nullable=False
    )
    use_terms_url: Mapped[str | None] = mapped_column(String(2048))
    license_notice: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utc_now, onupdate=utc_now
    )


class MasterDataSyncRun(Base):
    __tablename__ = "master_data_sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("master_data_sources.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    dataset_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    retrieved_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    source_release: Mapped[str | None] = mapped_column(String(160))
    checksum: Mapped[str | None] = mapped_column(String(128))
    parser_version: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[MasterDataRunStatus] = mapped_column(
        enum_column(MasterDataRunStatus, "master_data_run_status"),
        nullable=False,
        default=MasterDataRunStatus.RUNNING,
    )
    record_counts: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False, default=dict)
    error_summary: Mapped[str | None] = mapped_column(Text)


class MasterDataVersion(Base):
    __tablename__ = "master_data_versions"
    __table_args__ = (
        UniqueConstraint("dataset_key", "checksum", name="master_data_dataset_checksum_unique"),
        CheckConstraint("length(trim(dataset_key)) > 0", name="dataset_key_not_blank"),
        CheckConstraint("length(checksum) >= 32", name="checksum_minimum_length"),
        Index(
            "uq_master_data_active_dataset",
            "dataset_key",
            unique=True,
            sqlite_where=text("status = 'active'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sync_run_id: Mapped[int] = mapped_column(
        ForeignKey("master_data_sync_runs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    dataset_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_release: Mapped[str | None] = mapped_column(String(160))
    retrieved_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    activated_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    status: Mapped[MasterDataVersionStatus] = mapped_column(
        enum_column(MasterDataVersionStatus, "master_data_version_status"),
        nullable=False,
        default=MasterDataVersionStatus.CANDIDATE,
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)


class CQZone(Base):
    __tablename__ = "cq_zones"
    __table_args__ = (
        UniqueConstraint("version_id", "code", name="cq_zone_version_code_unique"),
        UniqueConstraint("id", "version_id", name="cq_zone_id_version_unique"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("master_data_versions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    definition: Mapped[str | None] = mapped_column(Text)


class ITUZone(Base):
    __tablename__ = "itu_zones"
    __table_args__ = (
        UniqueConstraint("version_id", "code", name="itu_zone_version_code_unique"),
        UniqueConstraint("id", "version_id", name="itu_zone_id_version_unique"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("master_data_versions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    definition: Mapped[str | None] = mapped_column(Text)


class IARURegion(Base):
    __tablename__ = "iaru_regions"
    __table_args__ = (
        UniqueConstraint("version_id", "code", name="iaru_region_version_code_unique"),
        UniqueConstraint("id", "version_id", name="iaru_region_id_version_unique"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("master_data_versions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)


class ITURadioRegion(Base):
    __tablename__ = "itu_radio_regions"
    __table_args__ = (
        UniqueConstraint("version_id", "code", name="itu_radio_region_version_code_unique"),
        UniqueConstraint("id", "version_id", name="itu_radio_region_id_version_unique"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("master_data_versions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)


class ContestEntity(Base):
    __tablename__ = "contest_entities"
    __table_args__ = (
        UniqueConstraint(
            "version_id", "namespace", "authority_code", name="entity_version_namespace_code_unique"
        ),
        UniqueConstraint("id", "version_id", name="entity_id_version_unique"),
        CheckConstraint("length(trim(namespace)) > 0", name="namespace_not_blank"),
        CheckConstraint("length(trim(authority_code)) > 0", name="authority_code_not_blank"),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="validity_range",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("master_data_versions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    namespace: Mapped[str] = mapped_column(String(40), nullable=False)
    authority_code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    entity_type: Mapped[EntityType] = mapped_column(
        enum_column(EntityType, "entity_type"), nullable=False
    )
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)


class CallsignPrefix(Base):
    __tablename__ = "callsign_prefixes"
    __table_args__ = (
        UniqueConstraint("version_id", "prefix_pattern", name="prefix_version_pattern_unique"),
        UniqueConstraint("id", "version_id", name="prefix_id_version_unique"),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="validity_range",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("master_data_versions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    prefix_pattern: Mapped[str] = mapped_column(String(80), nullable=False)
    allocation_type: Mapped[str] = mapped_column(String(80), nullable=False)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)


class PrefixEntityAssignment(Base):
    __tablename__ = "prefix_entity_assignments"
    __table_args__ = (
        UniqueConstraint(
            "version_id",
            "prefix_id",
            "entity_id",
            "valid_from",
            name="prefix_entity_version_effective_unique",
        ),
        ForeignKeyConstraint(
            ["prefix_id", "version_id"],
            ["callsign_prefixes.id", "callsign_prefixes.version_id"],
            name="prefix_entity_prefix_version_fk",
        ),
        ForeignKeyConstraint(
            ["entity_id", "version_id"],
            ["contest_entities.id", "contest_entities.version_id"],
            name="prefix_entity_entity_version_fk",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="validity_range",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("master_data_versions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    prefix_id: Mapped[int] = mapped_column(
        ForeignKey("callsign_prefixes.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    entity_id: Mapped[int] = mapped_column(
        ForeignKey("contest_entities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    source_note: Mapped[str | None] = mapped_column(Text)


class PrefixCQZoneAssignment(Base):
    __tablename__ = "prefix_cq_zone_assignments"
    __table_args__ = (
        UniqueConstraint(
            "version_id",
            "prefix_id",
            "cq_zone_id",
            "valid_from",
            name="prefix_cq_zone_version_effective_unique",
        ),
        ForeignKeyConstraint(
            ["prefix_id", "version_id"],
            ["callsign_prefixes.id", "callsign_prefixes.version_id"],
            name="prefix_cq_zone_prefix_version_fk",
        ),
        ForeignKeyConstraint(
            ["cq_zone_id", "version_id"],
            ["cq_zones.id", "cq_zones.version_id"],
            name="prefix_cq_zone_zone_version_fk",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="validity_range",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("master_data_versions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    prefix_id: Mapped[int] = mapped_column(
        ForeignKey("callsign_prefixes.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    cq_zone_id: Mapped[int] = mapped_column(
        ForeignKey("cq_zones.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    override_note: Mapped[str | None] = mapped_column(Text)


class PrefixITUZoneAssignment(Base):
    __tablename__ = "prefix_itu_zone_assignments"
    __table_args__ = (
        UniqueConstraint(
            "version_id",
            "prefix_id",
            "itu_zone_id",
            "valid_from",
            name="prefix_itu_zone_version_effective_unique",
        ),
        ForeignKeyConstraint(
            ["prefix_id", "version_id"],
            ["callsign_prefixes.id", "callsign_prefixes.version_id"],
            name="prefix_itu_zone_prefix_version_fk",
        ),
        ForeignKeyConstraint(
            ["itu_zone_id", "version_id"],
            ["itu_zones.id", "itu_zones.version_id"],
            name="prefix_itu_zone_zone_version_fk",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="validity_range",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("master_data_versions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    prefix_id: Mapped[int] = mapped_column(
        ForeignKey("callsign_prefixes.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    itu_zone_id: Mapped[int] = mapped_column(
        ForeignKey("itu_zones.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    override_note: Mapped[str | None] = mapped_column(Text)


class CallDistrict(Base):
    __tablename__ = "call_districts"
    __table_args__ = (
        UniqueConstraint(
            "version_id",
            "entity_id",
            "district_code",
            name="call_district_version_entity_code_unique",
        ),
        ForeignKeyConstraint(
            ["entity_id", "version_id"],
            ["contest_entities.id", "contest_entities.version_id"],
            name="call_district_entity_version_fk",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="validity_range",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("master_data_versions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    entity_id: Mapped[int] = mapped_column(
        ForeignKey("contest_entities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    district_code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    callsign_pattern: Mapped[str | None] = mapped_column(String(200))
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("master_data_sources.id", ondelete="RESTRICT")
    )


class EntityCQZoneAssignment(Base):
    __tablename__ = "entity_cq_zone_assignments"
    __table_args__ = (
        UniqueConstraint(
            "version_id",
            "entity_id",
            "cq_zone_id",
            "valid_from",
            name="entity_cq_zone_version_effective_unique",
        ),
        ForeignKeyConstraint(
            ["entity_id", "version_id"],
            ["contest_entities.id", "contest_entities.version_id"],
            name="entity_cq_zone_entity_version_fk",
        ),
        ForeignKeyConstraint(
            ["cq_zone_id", "version_id"],
            ["cq_zones.id", "cq_zones.version_id"],
            name="entity_cq_zone_zone_version_fk",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="validity_range",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("master_data_versions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    entity_id: Mapped[int] = mapped_column(
        ForeignKey("contest_entities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    cq_zone_id: Mapped[int] = mapped_column(
        ForeignKey("cq_zones.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    boundary_note: Mapped[str | None] = mapped_column(Text)


class EntityITUZoneAssignment(Base):
    __tablename__ = "entity_itu_zone_assignments"
    __table_args__ = (
        UniqueConstraint(
            "version_id",
            "entity_id",
            "itu_zone_id",
            "valid_from",
            name="entity_itu_zone_version_effective_unique",
        ),
        ForeignKeyConstraint(
            ["entity_id", "version_id"],
            ["contest_entities.id", "contest_entities.version_id"],
            name="entity_itu_zone_entity_version_fk",
        ),
        ForeignKeyConstraint(
            ["itu_zone_id", "version_id"],
            ["itu_zones.id", "itu_zones.version_id"],
            name="entity_itu_zone_zone_version_fk",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="validity_range",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("master_data_versions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    entity_id: Mapped[int] = mapped_column(
        ForeignKey("contest_entities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    itu_zone_id: Mapped[int] = mapped_column(
        ForeignKey("itu_zones.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    boundary_note: Mapped[str | None] = mapped_column(Text)


class EntityIARURegionAssignment(Base):
    __tablename__ = "entity_iaru_region_assignments"
    __table_args__ = (
        UniqueConstraint(
            "version_id",
            "entity_id",
            "iaru_region_id",
            "valid_from",
            name="entity_iaru_region_version_effective_unique",
        ),
        ForeignKeyConstraint(
            ["entity_id", "version_id"],
            ["contest_entities.id", "contest_entities.version_id"],
            name="entity_iaru_region_entity_version_fk",
        ),
        ForeignKeyConstraint(
            ["iaru_region_id", "version_id"],
            ["iaru_regions.id", "iaru_regions.version_id"],
            name="entity_iaru_region_region_version_fk",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="validity_range",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("master_data_versions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    entity_id: Mapped[int] = mapped_column(
        ForeignKey("contest_entities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    iaru_region_id: Mapped[int] = mapped_column(
        ForeignKey("iaru_regions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)


class EntityITURadioRegionAssignment(Base):
    __tablename__ = "entity_itu_radio_region_assignments"
    __table_args__ = (
        UniqueConstraint(
            "version_id",
            "entity_id",
            "itu_radio_region_id",
            "valid_from",
            name="entity_itu_radio_region_version_effective_unique",
        ),
        ForeignKeyConstraint(
            ["entity_id", "version_id"],
            ["contest_entities.id", "contest_entities.version_id"],
            name="entity_itu_radio_region_entity_version_fk",
        ),
        ForeignKeyConstraint(
            ["itu_radio_region_id", "version_id"],
            ["itu_radio_regions.id", "itu_radio_regions.version_id"],
            name="entity_itu_radio_region_region_version_fk",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="validity_range",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("master_data_versions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    entity_id: Mapped[int] = mapped_column(
        ForeignKey("contest_entities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    itu_radio_region_id: Mapped[int] = mapped_column(
        ForeignKey("itu_radio_regions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)


class IARUITURadioRegionMapping(Base):
    __tablename__ = "iaru_itu_radio_region_mappings"
    __table_args__ = (
        UniqueConstraint(
            "version_id",
            "iaru_region_id",
            "itu_radio_region_id",
            "valid_from",
            name="iaru_itu_region_version_effective_unique",
        ),
        ForeignKeyConstraint(
            ["iaru_region_id", "version_id"],
            ["iaru_regions.id", "iaru_regions.version_id"],
            name="iaru_itu_region_iaru_version_fk",
        ),
        ForeignKeyConstraint(
            ["itu_radio_region_id", "version_id"],
            ["itu_radio_regions.id", "itu_radio_regions.version_id"],
            name="iaru_itu_region_itu_version_fk",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="validity_range",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("master_data_versions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    iaru_region_id: Mapped[int] = mapped_column(
        ForeignKey("iaru_regions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    itu_radio_region_id: Mapped[int] = mapped_column(
        ForeignKey("itu_radio_regions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    mapping_note: Mapped[str | None] = mapped_column(Text)
