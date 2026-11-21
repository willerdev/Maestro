"""Track mining computers per login and attribute rewards to each machine."""

from alembic import op

revision = "0026_mining_computers"
down_revision = "0025_license_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mining_computers (
            id UUID PRIMARY KEY,
            organization_id UUID NOT NULL REFERENCES organizations(id),
            user_id UUID NOT NULL REFERENCES users(id),
            device_hash VARCHAR(64) NOT NULL,
            label VARCHAR(160) NOT NULL DEFAULT '',
            user_agent VARCHAR(300) NOT NULL DEFAULT '',
            last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_mining_computer_user_device UNIQUE (user_id, device_hash)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_mining_computers_organization_id ON mining_computers (organization_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_mining_computers_user_id ON mining_computers (user_id)")
    op.execute("ALTER TABLE chain_sessions ADD COLUMN IF NOT EXISTS device_hash VARCHAR(64) NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE chain_hits ADD COLUMN IF NOT EXISTS device_hash VARCHAR(64) NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE mining_reward_ledger ADD COLUMN IF NOT EXISTS device_hash VARCHAR(64) NOT NULL DEFAULT ''")


def downgrade() -> None:
    op.execute("ALTER TABLE mining_reward_ledger DROP COLUMN IF EXISTS device_hash")
    op.execute("ALTER TABLE chain_hits DROP COLUMN IF EXISTS device_hash")
    op.execute("ALTER TABLE chain_sessions DROP COLUMN IF EXISTS device_hash")
    op.execute("DROP TABLE IF EXISTS mining_computers")
