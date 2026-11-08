"""Contract holds and daily yield, 2.00% to 2.98%."""

from alembic import op

revision = "0021_contract_yield"
down_revision = "0020_extra_wallets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS contract_settings (
            organization_id UUID PRIMARY KEY REFERENCES organizations(id),
            daily_rate_bps INTEGER NOT NULL DEFAULT 200,
            min_deposit NUMERIC(20, 8) NOT NULL DEFAULT 2000,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS contract_stakes (
            id UUID PRIMARY KEY,
            organization_id UUID NOT NULL REFERENCES organizations(id),
            user_id UUID NOT NULL REFERENCES users(id),
            account_id UUID NOT NULL REFERENCES accounts(id),
            transfer_id UUID REFERENCES asset_transfers(id),
            principal NUMERIC(28, 8) NOT NULL,
            yield_earned NUMERIC(28, 8) NOT NULL DEFAULT 0,
            status VARCHAR(16) NOT NULL DEFAULT 'hold',
            last_yield_on DATE NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_contract_stakes_user_id ON contract_stakes (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_contract_stakes_account_id ON contract_stakes (account_id)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS contract_yields (
            id UUID PRIMARY KEY,
            stake_id UUID NOT NULL REFERENCES contract_stakes(id),
            day DATE NOT NULL,
            rate_bps INTEGER NOT NULL,
            amount NUMERIC(28, 8) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_contract_yield_day UNIQUE (stake_id, day)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS contract_yields")
    op.execute("DROP TABLE IF EXISTS contract_stakes")
    op.execute("DROP TABLE IF EXISTS contract_settings")
