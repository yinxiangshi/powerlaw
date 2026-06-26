"""initial event-sourced deal graph

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-25
"""

from __future__ import annotations

from alembic import op

from powerlaw.models.tables import Base

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    Base.metadata.create_all(bind=op.get_bind())
    op.execute("CREATE RULE no_update AS ON UPDATE TO events DO INSTEAD NOTHING")
    op.execute("CREATE RULE no_delete AS ON DELETE TO events DO INSTEAD NOTHING")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_party_aliases_alias_trgm "
        "ON party_aliases USING gin (alias gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP RULE IF EXISTS no_update ON events")
    op.execute("DROP RULE IF EXISTS no_delete ON events")
    op.execute("DROP INDEX IF EXISTS ix_party_aliases_alias_trgm")
    Base.metadata.drop_all(bind=op.get_bind())
