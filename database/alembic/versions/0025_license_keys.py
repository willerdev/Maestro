"""License keys bound to one computer, and $500 operating minimum."""

from alembic import op

revision = "0025_license_keys"
down_revision = "0024_hybrid_mining"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS license_keys (
            id UUID PRIMARY KEY,
            code VARCHAR(32) NOT NULL UNIQUE,
            status VARCHAR(16) NOT NULL DEFAULT 'available',
            organization_id UUID REFERENCES organizations(id),
            user_id UUID REFERENCES users(id),
            device_hash VARCHAR(64) NOT NULL DEFAULT '',
            bound_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_license_keys_status ON license_keys (status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_license_keys_user_id ON license_keys (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_license_keys_device_hash ON license_keys (device_hash)")
    op.execute("ALTER TABLE operating_cycles ALTER COLUMN target SET DEFAULT 500")


def downgrade() -> None:
    op.execute("ALTER TABLE operating_cycles ALTER COLUMN target SET DEFAULT 700")
    op.execute("DROP TABLE IF EXISTS license_keys")
