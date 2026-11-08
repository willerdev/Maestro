"""Optional premium mining plans on top of existing Project Coin proof-of-work."""

from alembic import op

revision = "0024_hybrid_mining"
down_revision = "0023_operating_cycles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mining_settings (
            organization_id UUID PRIMARY KEY REFERENCES organizations(id),
            paused BOOLEAN NOT NULL DEFAULT FALSE,
            base_daily_pcoin VARCHAR(40) NOT NULL DEFAULT '10',
            default_duration_days INTEGER NOT NULL DEFAULT 30,
            max_multiplier VARCHAR(16) NOT NULL DEFAULT '3',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mining_plans (
            id UUID PRIMARY KEY,
            organization_id UUID NOT NULL REFERENCES organizations(id),
            code VARCHAR(32) NOT NULL,
            name VARCHAR(80) NOT NULL,
            price NUMERIC(20, 8) NOT NULL DEFAULT 0,
            multiplier VARCHAR(16) NOT NULL DEFAULT '1',
            duration_days INTEGER NOT NULL DEFAULT 0,
            daily_limit VARCHAR(40) NOT NULL DEFAULT '0',
            sort_order INTEGER NOT NULL DEFAULT 0,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            benefits TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_mining_plan_code UNIQUE (organization_id, code)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_mining_plans_organization_id ON mining_plans (organization_id)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_mining_upgrades (
            id UUID PRIMARY KEY,
            organization_id UUID NOT NULL REFERENCES organizations(id),
            user_id UUID NOT NULL REFERENCES users(id),
            plan_id UUID NOT NULL REFERENCES mining_plans(id),
            status VARCHAR(16) NOT NULL DEFAULT 'active',
            multiplier VARCHAR(16) NOT NULL DEFAULT '1',
            started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            ends_at TIMESTAMPTZ,
            last_accrued_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_mining_upgrades_organization_id ON user_mining_upgrades (organization_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_mining_upgrades_user_id ON user_mining_upgrades (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_mining_upgrades_plan_id ON user_mining_upgrades (plan_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_mining_upgrades_status ON user_mining_upgrades (status)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mining_upgrade_payments (
            id UUID PRIMARY KEY,
            organization_id UUID NOT NULL REFERENCES organizations(id),
            user_id UUID NOT NULL REFERENCES users(id),
            plan_id UUID NOT NULL REFERENCES mining_plans(id),
            upgrade_id UUID REFERENCES user_mining_upgrades(id),
            reference VARCHAR(80) NOT NULL,
            amount NUMERIC(20, 8) NOT NULL,
            currency VARCHAR(20) NOT NULL DEFAULT 'usdttrc20',
            method VARCHAR(16) NOT NULL DEFAULT 'wallet',
            status VARCHAR(16) NOT NULL DEFAULT 'pending',
            invoice_url VARCHAR(500) NOT NULL DEFAULT '',
            note VARCHAR(240) NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            paid_at TIMESTAMPTZ,
            CONSTRAINT uq_mining_upgrade_payment_ref UNIQUE (organization_id, reference)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_mining_upgrade_payments_organization_id ON mining_upgrade_payments (organization_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_mining_upgrade_payments_user_id ON mining_upgrade_payments (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_mining_upgrade_payments_status ON mining_upgrade_payments (status)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mining_reward_ledger (
            id UUID PRIMARY KEY,
            organization_id UUID NOT NULL REFERENCES organizations(id),
            user_id UUID NOT NULL REFERENCES users(id),
            upgrade_id UUID REFERENCES user_mining_upgrades(id),
            plan_id UUID REFERENCES mining_plans(id),
            kind VARCHAR(24) NOT NULL DEFAULT 'premium_accrual',
            amount_atomic BIGINT NOT NULL,
            multiplier VARCHAR(16) NOT NULL DEFAULT '1',
            reference VARCHAR(80) NOT NULL,
            note VARCHAR(240) NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_mining_reward_reference UNIQUE (organization_id, reference)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_mining_reward_ledger_organization_id ON mining_reward_ledger (organization_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_mining_reward_ledger_user_id ON mining_reward_ledger (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_mining_reward_ledger_created_at ON mining_reward_ledger (created_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS mining_reward_ledger")
    op.execute("DROP TABLE IF EXISTS mining_upgrade_payments")
    op.execute("DROP TABLE IF EXISTS user_mining_upgrades")
    op.execute("DROP TABLE IF EXISTS mining_plans")
    op.execute("DROP TABLE IF EXISTS mining_settings")
