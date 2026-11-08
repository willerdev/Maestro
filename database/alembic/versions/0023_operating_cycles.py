"""Five-day operating expense cycles billed from user wallets."""

from alembic import op

revision = "0023_operating_cycles"
down_revision = "0022_system_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS operating_cycles (
            id UUID PRIMARY KEY,
            organization_id UUID NOT NULL REFERENCES organizations(id),
            user_id UUID NOT NULL REFERENCES users(id),
            started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            ends_at TIMESTAMPTZ NOT NULL,
            target NUMERIC(28, 8) NOT NULL DEFAULT 700,
            collected NUMERIC(28, 8) NOT NULL DEFAULT 0,
            last_charged_at TIMESTAMPTZ,
            status VARCHAR(16) NOT NULL DEFAULT 'active',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_operating_cycles_organization_id ON operating_cycles (organization_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_operating_cycles_user_id ON operating_cycles (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_operating_cycles_status ON operating_cycles (status)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS operating_cycles")
