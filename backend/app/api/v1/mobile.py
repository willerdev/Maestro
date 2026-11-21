"""Phone wallet. Signed-in users see their own balances and move only their own funds."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_db, get_principal
from app.api.v1.router import _client_ip
from app.chain.money import UNIT, format_amount
from app.models.chain_entities import ChainTxRow, ChainWallet
from app.models.entities import Account, AccountState, UserPayoutAddress
from app.services.account_service import AccountError, visible_account_query
from app.services.asset_service import AssetError, _address, _available, asset_home, request_deposit, request_withdrawal
from app.services.contract_service import ContractServiceError, desk, fund_contract, withdraw_contract
from app.services.conversion_service import ConversionServiceError, convert, pcoin_hold, preview, public_settings
from app.services.mining_plan_service import bonus_available

router = APIRouter()


class AmountIn(BaseModel):
    amount: Decimal


class WithdrawIn(BaseModel):
    amount: Decimal
    address: str
    currency: str = "usdttrc20"


class FundIn(BaseModel):
    account_id: UUID
    amount: Decimal


class AddressIn(BaseModel):
    address: str


class StakeIn(BaseModel):
    stake_id: UUID


def _fail(exc: Exception) -> None:
    status = getattr(exc, "status", 400)
    detail = getattr(exc, "detail", None) or str(exc)
    raise HTTPException(status, detail) from exc


def _ensure_payout_table(db: Session) -> None:
    UserPayoutAddress.__table__.create(bind=db.get_bind(), checkfirst=True)


def _saved_address(db: Session, user) -> str:
    _ensure_payout_table(db)
    row = db.get(UserPayoutAddress, user.id)
    return "" if row is None else row.address


def _save_address(db: Session, user, address: str) -> str:
    text = _address(address)
    _ensure_payout_table(db)
    row = db.get(UserPayoutAddress, user.id)
    if row is None:
        db.add(UserPayoutAddress(user_id=user.id, organization_id=user.organization_id, address=text))
    else:
        row.address = text
        row.organization_id = user.organization_id
    return text


def _pcoin_atomic(db: Session, user) -> int:
    wallet = db.scalar(select(ChainWallet).where(ChainWallet.organization_id == user.organization_id, ChainWallet.user_id == user.id))
    if wallet is None:
        return 0
    incoming = db.scalar(
        select(func.coalesce(func.sum(ChainTxRow.amount), 0)).where(
            ChainTxRow.organization_id == user.organization_id,
            ChainTxRow.recipient == wallet.address,
            ChainTxRow.block_height.is_not(None),
        )
    )
    outgoing = db.scalar(
        select(func.coalesce(func.sum(ChainTxRow.amount + ChainTxRow.fee), 0)).where(
            ChainTxRow.organization_id == user.organization_id,
            ChainTxRow.sender == wallet.address,
            ChainTxRow.kind == "transfer",
            ChainTxRow.block_height.is_not(None),
        )
    )
    pending = db.scalar(
        select(func.coalesce(func.sum(ChainTxRow.amount + ChainTxRow.fee), 0)).where(
            ChainTxRow.organization_id == user.organization_id,
            ChainTxRow.sender == wallet.address,
            ChainTxRow.kind == "transfer",
            ChainTxRow.block_height.is_(None),
        )
    )
    chain = int(incoming or 0) - int(outgoing or 0) - int(pending or 0)
    return max(0, chain - pcoin_hold(db, user.organization_id, user.id) + bonus_available(db, user.organization_id, user.id))


def _money(value: Decimal) -> str:
    return format(Decimal(value).quantize(Decimal("0.01")), "f")


@router.get("/mobile/home")
def home(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    user = principal.user
    usdt = _available(db, user, "usdttrc20") + _available(db, user, "usdt")
    rules = public_settings(db, user.organization_id)
    rate = Decimal(str(rules["rate"]))
    atomic = _pcoin_atomic(db, user)
    pcoin = Decimal(atomic) / Decimal(UNIT)
    contracts = desk(db, user, principal.roles)
    accounts = db.scalars(visible_account_query(db, user, principal.roles).order_by(Account.display_name)).all()
    cards = []
    for account in accounts:
        state = db.get(AccountState, account.id)
        if account.connection_method == "mining":
            action = "convert"
            balance = format_amount(atomic)
            currency = "PCoin"
        elif account.connection_method == "blockchain":
            action = "contract"
            held = sum(Decimal(row["held"]) for row in contracts["positions"] if row["account_id"] == str(account.id))
            balance = format(held, "f") if held else "0"
            currency = "USDT"
        else:
            action = "view"
            balance = format(state.balance if state else 0, "f")
            currency = account.currency or "USD"
        cards.append(
            {
                "id": str(account.id),
                "name": account.display_name,
                "method": account.connection_method,
                "number": account.account_number,
                "status": account.status,
                "balance": balance,
                "currency": currency,
                "action": action,
            }
        )
    wallet = asset_home(db, user)
    db.commit()
    return {
        "user": {"email": user.email, "full_name": user.full_name},
        "usdt": _money(usdt),
        "pcoin": format_amount(atomic),
        "pcoin_usdt": _money(pcoin / rate if rate else 0),
        "rate": rules["label"],
        "rate_value": str(rules["rate"]),
        "fee_bps": int(rules["fee_bps"]),
        "min_pcoin": rules["min_pcoin"],
        "payments_ready": wallet["configured"],
        "payout_address": _saved_address(db, user),
        "accounts": cards,
        "contracts": contracts["positions"],
        "transfers": wallet["transfers"],
    }


@router.post("/mobile/deposit")
def deposit(body: AmountIn, request: Request, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    try:
        payload = request_deposit(db, principal.user, "usdttrc20", body.amount, _client_ip(request))
    except AssetError as exc:
        _fail(exc)
    db.commit()
    return payload


@router.post("/mobile/payout-address")
def save_payout_address(body: AddressIn, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    try:
        address = _save_address(db, principal.user, body.address)
    except AssetError as exc:
        _fail(exc)
    db.commit()
    return {"address": address}


@router.post("/mobile/withdraw")
def withdraw(body: WithdrawIn, request: Request, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    address = str(body.address or "").strip() or _saved_address(db, principal.user)
    try:
        if address:
            address = _save_address(db, principal.user, address)
        payload = request_withdrawal(db, principal.user, body.currency or "usdttrc20", body.amount, address, _client_ip(request))
    except AssetError as exc:
        _fail(exc)
    db.commit()
    return payload


@router.post("/mobile/convert/preview")
def convert_preview(body: AmountIn, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    try:
        return preview(db, principal.user.organization_id, principal.user.id, format(body.amount, "f"))
    except ConversionServiceError as exc:
        _fail(exc)


@router.post("/mobile/convert")
def convert_pcoin(body: AmountIn, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    try:
        return convert(db, principal.user.organization_id, principal.user.id, format(body.amount, "f"))
    except ConversionServiceError as exc:
        _fail(exc)


@router.post("/mobile/contracts/fund")
def fund(body: FundIn, request: Request, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    try:
        payload = fund_contract(db, principal.user, principal.roles, body.account_id, body.amount, _client_ip(request))
    except (ContractServiceError, AccountError) as exc:
        _fail(exc)
    db.commit()
    return payload


@router.post("/mobile/contracts/withdraw")
def contract_withdraw(body: StakeIn, request: Request, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    try:
        payload = withdraw_contract(db, principal.user, principal.roles, body.stake_id, _client_ip(request))
    except (ContractServiceError, AccountError) as exc:
        _fail(exc)
    db.commit()
    return payload
