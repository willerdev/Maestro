"""Internal PCoin to USDT conversion ledger."""

from alembic import op

revision = "0019_pcoin_conversion"
down_revision = "0018_project_chain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS chain_conversion_settings (
            organization_id UUID PRIMARY KEY REFERENCES organizations(id),
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            rate VARCHAR(40) NOT NULL DEFAULT '1000',
            min_pcoin VARCHAR(40) NOT NULL DEFAULT '1000',
            max_pcoin VARCHAR(40) NOT NULL DEFAULT '0',
            fee_bps INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS chain_conversions (
            id UUID PRIMARY KEY,
            organization_id UUID NOT NULL REFERENCES organizations(id),
            user_id UUID NOT NULL REFERENCES users(id),
            reference VARCHAR(40) NOT NULL,
            pcoin_atomic BIGINT NOT NULL,
            fee_atomic BIGINT NOT NULL DEFAULT 0,
            usdt_atomic BIGINT NOT NULL,
            rate VARCHAR(40) NOT NULL,
            status VARCHAR(16) NOT NULL DEFAULT 'completed',
            network VARCHAR(16) NOT NULL DEFAULT 'internal',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_chain_conversion_reference UNIQUE (organization_id, reference)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_chain_conversions_organization_id ON chain_conversions (organization_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_chain_conversions_user_id ON chain_conversions (user_id)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS chain_rate_changes (
            id UUID PRIMARY KEY,
            organization_id UUID NOT NULL REFERENCES organizations(id),
            actor_user_id UUID NOT NULL REFERENCES users(id),
            old_rate VARCHAR(40) NOT NULL DEFAULT '',
            new_rate VARCHAR(40) NOT NULL,
            old_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            new_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_chain_rate_changes_organization_id ON chain_rate_changes (organization_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS chain_rate_changes")
    op.execute("DROP TABLE IF EXISTS chain_conversions")
    op.execute("DROP TABLE IF EXISTS chain_conversion_settings")
