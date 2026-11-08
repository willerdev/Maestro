"""Encrypted extra wallet configuration for Binance, Bybit, and OKX."""

from alembic import op

revision = "0020_extra_wallets"
down_revision = "0019_pcoin_conversion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS extra_wallets (
            id UUID PRIMARY KEY,
            organization_id UUID NOT NULL REFERENCES organizations(id),
            user_id UUID NOT NULL REFERENCES users(id),
            provider VARCHAR(16) NOT NULL,
            address VARCHAR(42) NOT NULL,
            source VARCHAR(16) NOT NULL,
            key_nonce BYTEA NOT NULL,
            key_ciphertext BYTEA NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_extra_wallet_user_provider UNIQUE (organization_id, user_id, provider)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS extra_wallets")
