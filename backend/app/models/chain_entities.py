"""Database rows for one Project Coin chain per organization."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint, Uuid
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
