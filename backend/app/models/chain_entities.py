"""Database rows for one Project Coin chain per organization."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, LargeBinary, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class ChainWallet(Base):
    __tablename__ = "chain_wallets"
    __table_args__ = (UniqueConstraint("organization_id", "user_id", name="uq_chain_wallet_user"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    address: Mapped[str] = mapped_column(String(80), unique=True)
    public_key: Mapped[str] = mapped_column(Text)
    key_nonce: Mapped[bytes] = mapped_column(LargeBinary)
    key_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChainBlockRow(Base):
    __tablename__ = "chain_blocks"
    __table_args__ = (UniqueConstraint("organization_id", "height", name="uq_chain_block_height"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    height: Mapped[int] = mapped_column(Integer)
    timestamp: Mapped[int] = mapped_column(BigInteger)
    previous_hash: Mapped[str] = mapped_column(String(64))
    block_hash: Mapped[str] = mapped_column(String(64), index=True)
    nonce: Mapped[str] = mapped_column(String(80))
    difficulty: Mapped[int] = mapped_column(Integer)
    miner_address: Mapped[str] = mapped_column(String(80))
    reward: Mapped[int] = mapped_column(BigInteger)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChainTxRow(Base):
    __tablename__ = "chain_transactions"
    __table_args__ = (UniqueConstraint("organization_id", "tx_hash", name="uq_chain_tx_hash"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    tx_hash: Mapped[str] = mapped_column(String(64))
    block_height: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    sender: Mapped[str] = mapped_column(String(80), default="")
    recipient: Mapped[str] = mapped_column(String(80), index=True)
    amount: Mapped[int] = mapped_column(BigInteger)
    fee: Mapped[int] = mapped_column(BigInteger, default=0)
    nonce: Mapped[int] = mapped_column(Integer, default=0)
    kind: Mapped[str] = mapped_column(String(16))
    public_key: Mapped[str] = mapped_column(Text, default="")
    signature: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChainSessionRow(Base):
    __tablename__ = "chain_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(16))
    hashes: Mapped[int] = mapped_column(BigInteger, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    difficulty: Mapped[int] = mapped_column(Integer)
    cpu_percent: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ChainHit(Base):
    __tablename__ = "chain_hits"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    height: Mapped[int] = mapped_column(Integer)
    block_hash: Mapped[str] = mapped_column(String(64))
    reward: Mapped[int] = mapped_column(BigInteger)
    hashes: Mapped[int] = mapped_column(BigInteger, default=0)
    found_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChainNode(Base):
    __tablename__ = "chain_nodes"
    __table_args__ = (UniqueConstraint("organization_id", "node_key", name="uq_chain_node"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    node_key: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(120), default="local")
    status: Mapped[str] = mapped_column(String(16), default="online")
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChainConversionSettings(Base):
    __tablename__ = "chain_conversion_settings"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    rate: Mapped[str] = mapped_column(String(40), default="1000")
    min_pcoin: Mapped[str] = mapped_column(String(40), default="1000")
    max_pcoin: Mapped[str] = mapped_column(String(40), default="0")
    fee_bps: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ChainConversion(Base):
    __tablename__ = "chain_conversions"
    __table_args__ = (UniqueConstraint("organization_id", "reference", name="uq_chain_conversion_reference"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    reference: Mapped[str] = mapped_column(String(40))
    pcoin_atomic: Mapped[int] = mapped_column(BigInteger)
    fee_atomic: Mapped[int] = mapped_column(BigInteger, default=0)
    usdt_atomic: Mapped[int] = mapped_column(BigInteger)
    rate: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(16), default="completed")
    network: Mapped[str] = mapped_column(String(16), default="internal")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExtraWalletRow(Base):
    __tablename__ = "extra_wallets"
    __table_args__ = (UniqueConstraint("organization_id", "user_id", "provider", name="uq_extra_wallet_user_provider"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(String(16))
    address: Mapped[str] = mapped_column(String(42))
    source: Mapped[str] = mapped_column(String(16))
    key_nonce: Mapped[bytes] = mapped_column(LargeBinary)
    key_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ContractSettings(Base):
    __tablename__ = "contract_settings"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    daily_rate_bps: Mapped[int] = mapped_column(Integer, default=200)
    min_deposit: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("2000"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ContractStake(Base):
    __tablename__ = "contract_stakes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"), index=True)
    transfer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("asset_transfers.id"), nullable=True)
    principal: Mapped[Decimal] = mapped_column(Numeric(28, 8))
    yield_earned: Mapped[Decimal] = mapped_column(Numeric(28, 8), default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(16), default="hold")
    last_yield_on: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ContractYield(Base):
    __tablename__ = "contract_yields"
    __table_args__ = (UniqueConstraint("stake_id", "day", name="uq_contract_yield_day"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stake_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("contract_stakes.id"), index=True)
    day: Mapped[date] = mapped_column(Date)
    rate_bps: Mapped[int] = mapped_column(Integer)
    amount: Mapped[Decimal] = mapped_column(Numeric(28, 8))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChainRateChange(Base):
    __tablename__ = "chain_rate_changes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    old_rate: Mapped[str] = mapped_column(String(40), default="")
    new_rate: Mapped[str] = mapped_column(String(40))
    old_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    new_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MiningSettings(Base):
    __tablename__ = "mining_settings"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    base_daily_pcoin: Mapped[str] = mapped_column(String(40), default="10")
    default_duration_days: Mapped[int] = mapped_column(Integer, default=30)
    max_multiplier: Mapped[str] = mapped_column(String(16), default="3")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class MiningPlan(Base):
    __tablename__ = "mining_plans"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_mining_plan_code"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(80))
    price: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    multiplier: Mapped[str] = mapped_column(String(16), default="1")
    duration_days: Mapped[int] = mapped_column(Integer, default=0)
    daily_limit: Mapped[str] = mapped_column(String(40), default="0")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    benefits: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UserMiningUpgrade(Base):
    __tablename__ = "user_mining_upgrades"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("mining_plans.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    multiplier: Mapped[str] = mapped_column(String(16), default="1")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_accrued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MiningUpgradePayment(Base):
    __tablename__ = "mining_upgrade_payments"
    __table_args__ = (UniqueConstraint("organization_id", "reference", name="uq_mining_upgrade_payment_ref"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("mining_plans.id"), index=True)
    upgrade_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user_mining_upgrades.id"), nullable=True, index=True)
    reference: Mapped[str] = mapped_column(String(80))
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    currency: Mapped[str] = mapped_column(String(20), default="usdttrc20")
    method: Mapped[str] = mapped_column(String(16), default="wallet")
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    invoice_url: Mapped[str] = mapped_column(String(500), default="")
    note: Mapped[str] = mapped_column(String(240), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MiningRewardLedger(Base):
    __tablename__ = "mining_reward_ledger"
    __table_args__ = (UniqueConstraint("organization_id", "reference", name="uq_mining_reward_reference"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    upgrade_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user_mining_upgrades.id"), nullable=True, index=True)
    plan_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("mining_plans.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(24), default="premium_accrual")
    amount_atomic: Mapped[int] = mapped_column(BigInteger)
    multiplier: Mapped[str] = mapped_column(String(16), default="1")
    reference: Mapped[str] = mapped_column(String(80))
    note: Mapped[str] = mapped_column(String(240), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
