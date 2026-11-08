"""Project Coin blocks, wallets, and mining sessions."""

from alembic import op

revision = "0018_project_chain"
down_revision = "0017_naked_limits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS chain_wallets (
            id UUID PRIMARY KEY,
            organization_id UUID NOT NULL REFERENCES organizations(id),
            user_id UUID NOT NULL REFERENCES users(id),
            address VARCHAR(80) NOT NULL UNIQUE,
            public_key TEXT NOT NULL,
            key_nonce BYTEA NOT NULL,
            key_ciphertext BYTEA NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_chain_wallet_user UNIQUE (organization_id, user_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_chain_wallets_organization_id ON chain_wallets (organization_id)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS chain_blocks (
            id UUID PRIMARY KEY,
            organization_id UUID NOT NULL REFERENCES organizations(id),
            height INTEGER NOT NULL,
            timestamp BIGINT NOT NULL,
            previous_hash VARCHAR(64) NOT NULL,
            block_hash VARCHAR(64) NOT NULL,
            nonce VARCHAR(80) NOT NULL,
            difficulty INTEGER NOT NULL,
            miner_address VARCHAR(80) NOT NULL,
            reward BIGINT NOT NULL,
            body TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_chain_block_height UNIQUE (organization_id, height)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_chain_blocks_organization_id ON chain_blocks (organization_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_chain_blocks_block_hash ON chain_blocks (block_hash)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS chain_transactions (
            id UUID PRIMARY KEY,
            organization_id UUID NOT NULL REFERENCES organizations(id),
            tx_hash VARCHAR(64) NOT NULL,
            block_height INTEGER,
            sender VARCHAR(80) NOT NULL DEFAULT '',
            recipient VARCHAR(80) NOT NULL,
            amount BIGINT NOT NULL,
            fee BIGINT NOT NULL DEFAULT 0,
            nonce INTEGER NOT NULL DEFAULT 0,
            kind VARCHAR(16) NOT NULL,
            public_key TEXT NOT NULL DEFAULT '',
            signature TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_chain_tx_hash UNIQUE (organization_id, tx_hash)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_chain_transactions_organization_id ON chain_transactions (organization_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_chain_transactions_block_height ON chain_transactions (block_height)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_chain_transactions_recipient ON chain_transactions (recipient)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS chain_sessions (
            id UUID PRIMARY KEY,
            organization_id UUID NOT NULL REFERENCES organizations(id),
            user_id UUID NOT NULL REFERENCES users(id),
            status VARCHAR(16) NOT NULL,
            hashes BIGINT NOT NULL DEFAULT 0,
            success_count INTEGER NOT NULL DEFAULT 0,
            failure_count INTEGER NOT NULL DEFAULT 0,
            difficulty INTEGER NOT NULL,
            cpu_percent INTEGER NOT NULL,
            started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            stopped_at TIMESTAMPTZ
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_chain_sessions_organization_id ON chain_sessions (organization_id)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS chain_hits (
            id UUID PRIMARY KEY,
            organization_id UUID NOT NULL REFERENCES organizations(id),
            user_id UUID NOT NULL REFERENCES users(id),
            height INTEGER NOT NULL,
            block_hash VARCHAR(64) NOT NULL,
            reward BIGINT NOT NULL,
            hashes BIGINT NOT NULL DEFAULT 0,
            found_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_chain_hits_organization_id ON chain_hits (organization_id)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS chain_nodes (
            id UUID PRIMARY KEY,
            organization_id UUID NOT NULL REFERENCES organizations(id),
            node_key VARCHAR(64) NOT NULL,
            label VARCHAR(120) NOT NULL DEFAULT 'local',
            status VARCHAR(16) NOT NULL DEFAULT 'online',
            last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_chain_node UNIQUE (organization_id, node_key)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_chain_nodes_organization_id ON chain_nodes (organization_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS chain_nodes")
    op.execute("DROP TABLE IF EXISTS chain_hits")
    op.execute("DROP TABLE IF EXISTS chain_sessions")
    op.execute("DROP TABLE IF EXISTS chain_transactions")
    op.execute("DROP TABLE IF EXISTS chain_blocks")
    op.execute("DROP TABLE IF EXISTS chain_wallets")
