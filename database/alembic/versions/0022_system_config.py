"""Org-level connector keys saved by admin."""

from alembic import op

revision = "0022_system_config"
down_revision = "0021_contract_yield"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS system_configs (
            id UUID PRIMARY KEY,
            organization_id UUID NOT NULL UNIQUE REFERENCES organizations(id),
            secret_nonce BYTEA,
            secret_ciphertext BYTEA,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_system_configs_organization_id ON system_configs (organization_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS system_configs")
