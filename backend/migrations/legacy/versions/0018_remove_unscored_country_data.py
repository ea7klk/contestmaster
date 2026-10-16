"""Remove unused UNGEGN and M49 country reference datasets.

Revision ID: 0018_remove_unscored_country_data
Revises: 0017_contest_free_band_defaults
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_remove_unscored_country_data"
down_revision: str | None = "0017_contest_free_band_defaults"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DATASET_KEYS = ("countries-ungegn-wgn", "countries-unsd-m49")
_SOURCE_KEYS = ("ungegn-wgn-countries", "unsd-m49-country-areas")


def upgrade() -> None:
    connection = op.get_bind()
    dataset_list = "'countries-ungegn-wgn', 'countries-unsd-m49'"
    version_ids = f"SELECT id FROM master_data_versions WHERE dataset_key IN ({dataset_list})"

    # These obsolete pins never drove supported score facts. Remove their provenance
    # entries while preserving score values, ruleset snapshots, and the CTY pin.
    op.execute(f"DELETE FROM contest_master_data_versions WHERE dataset_key IN ({dataset_list})")
    op.execute(f"DELETE FROM score_run_master_data_versions WHERE dataset_key IN ({dataset_list})")
    op.execute("DROP TRIGGER IF EXISTS immutable_qsos_update")
    op.execute(
        f"UPDATE qsos SET worked_entity_id = NULL, worked_cq_zone_id = NULL, "
        f"worked_itu_zone_id = NULL, resolved_master_data_version_id = NULL "
        f"WHERE resolved_master_data_version_id IN ({version_ids})"
    )

    # Completed score runs are append-only during normal operation. This migration
    # removes unused dataset keys from their audit snapshot; scores are untouched.
    op.execute(
        "CREATE TRIGGER immutable_qsos_update BEFORE UPDATE ON qsos "
        "BEGIN SELECT RAISE(ABORT, 'qsos records are append-only'); END"
    )
    op.execute("DROP TRIGGER IF EXISTS immutable_completed_score_run")
    op.execute("DROP TRIGGER IF EXISTS completed_score_runs_update")
    for row in connection.execute(
        sa.text(
            "SELECT id, master_data_snapshot FROM score_runs WHERE master_data_snapshot IS NOT NULL"
        )
    ):
        snapshot = row.master_data_snapshot
        if isinstance(snapshot, str):
            snapshot = json.loads(snapshot)
        if isinstance(snapshot, dict):
            cleaned = {key: value for key, value in snapshot.items() if key not in _DATASET_KEYS}
            if cleaned != snapshot:
                connection.execute(
                    sa.text(
                        "UPDATE score_runs SET master_data_snapshot = :snapshot WHERE id = :id"
                    ),
                    {"snapshot": json.dumps(cleaned, separators=(",", ":")), "id": row.id},
                )
    # The scoring pipeline pins CTY in this dedicated field; clear only accidental
    # references to the obsolete dataset versions before restoring immutability.
    op.execute(
        f"UPDATE score_runs SET master_data_version_id = NULL "
        f"WHERE master_data_version_id IN ({version_ids})"
    )
    op.execute(
        "CREATE TRIGGER completed_score_runs_update BEFORE UPDATE ON score_runs "
        "WHEN OLD.status = 'completed' "
        "BEGIN SELECT RAISE(ABORT, 'completed score runs are immutable'); END"
    )
    op.execute(
        "CREATE TRIGGER immutable_completed_score_run BEFORE UPDATE ON score_runs "
        "WHEN OLD.status = 'completed' "
        "BEGIN SELECT RAISE(ABORT, 'completed score_runs are immutable'); END"
    )
    for table in (
        "prefix_entity_assignments",
        "prefix_cq_zone_assignments",
        "prefix_itu_zone_assignments",
        "entity_cq_zone_assignments",
        "entity_itu_zone_assignments",
        "callsign_prefixes",
        "contest_entities",
        "cq_zones",
        "itu_zones",
    ):
        op.execute(f"DELETE FROM {table} WHERE version_id IN ({version_ids})")

    op.execute("DROP TRIGGER IF EXISTS prevent_active_master_data_version_delete")
    op.execute(f"DELETE FROM master_data_versions WHERE dataset_key IN ({dataset_list})")
    source_list = ", ".join(f"'{key}'" for key in _SOURCE_KEYS)
    op.execute(
        f"DELETE FROM master_data_sync_runs WHERE dataset_key IN ({dataset_list}) "
        f"OR source_id IN (SELECT id FROM master_data_sources WHERE source_key IN ({source_list}))"
    )
    op.execute(f"DELETE FROM master_data_sources WHERE source_key IN ({source_list})")
    op.execute(
        "CREATE TRIGGER prevent_active_master_data_version_delete "
        "BEFORE DELETE ON master_data_versions WHEN OLD.status = 'active' "
        "BEGIN SELECT RAISE(ABORT, 'active master data versions cannot be deleted'); END"
    )


def downgrade() -> None:
    # Source records were intentionally purged and cannot be recreated by rollback.
    pass
