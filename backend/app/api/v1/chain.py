"""Authenticated Project Coin routes. Rewards are created only by a validated block."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_db, get_principal
from app.core.rate_limit import WindowLimiter
from app.services.chain_service import ChainServiceError, account_activity, block_detail, create_wallet, dashboard, export_wallet, import_wallet, list_blocks, list_transactions, mining_statistics, mining_status, network_status, pause_mining, resume_mining, search, send_coins, set_cpu, start_mining, stop_mining, transaction_detail, wallet_transactions, wallet_view
from app.services.conversion_service import ConversionServiceError, convert, export_csv, list_conversions, preview, report, update_settings, wallet_conversion, public_settings
from app.services.mining_plan_service import MiningPlanError, admin_miners, admin_overview, admin_suspicious, hybrid_overview, list_plans, list_reward_rows, list_upgrade_payments, purchase_upgrade, save_plan, settings_payload, update_settings as update_mining_settings

router = APIRouter(prefix="/chain")
_limiter = WindowLimiter()


class WalletImport(BaseModel):
    private_key: str = Field(min_length=64, max_length=64)


class WalletExport(BaseModel):
    confirm: bool = False


class SendBody(BaseModel):
    recipient: str
    amount: str


class MineBody(BaseModel):
    cpu_percent: int | None = None


class ConvertBody(BaseModel):
    amount: str
    reference: str = ""


class ConversionSettingsBody(BaseModel):
    rate: str
    enabled: bool = True
    min_pcoin: str = "1000"
    max_pcoin: str = "0"
    fee_bps: int = 0


class UpgradeBody(BaseModel):
    plan_id: str
    method: str = "wallet"


class MiningSettingsBody(BaseModel):
    paused: bool | None = None
    base_daily_pcoin: str | None = None
    default_duration_days: int | None = None
    max_multiplier: str | None = None


class MiningPlanBody(BaseModel):
    code: str | None = None
    name: str | None = None
    price: str | None = None
    multiplier: str | None = None
    duration_days: int | None = None
    daily_limit: str | None = None
    benefits: str | None = None
    enabled: bool | None = None
    sort_order: int | None = None


def _run(func):
    try:
        return func()
    except (ChainServiceError, ConversionServiceError, MiningPlanError) as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc


def _guard(principal: Principal, action: str) -> None:
    if _limiter.hit(f"{principal.user.id}:{action}", limit=20, window_seconds=60):
        raise HTTPException(status_code=429, detail="Too many chain requests. Wait a minute.")


@router.post("/wallet")
def create(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.mine")
    _guard(principal, "wallet")
    return _run(lambda: create_wallet(db, principal.user.organization_id, principal.user.id))


@router.post("/wallet/import")
def import_key(body: WalletImport, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.mine")
    _guard(principal, "import")
    return _run(lambda: import_wallet(db, principal.user.organization_id, principal.user.id, body.private_key))


@router.post("/wallet/export")
def export_key(body: WalletExport, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.mine")
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Confirm the export before the private key is shown")
    _guard(principal, "export")
    return _run(lambda: export_wallet(db, principal.user.organization_id, principal.user.id))


@router.get("/wallet")
def wallet(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.read")
    return _run(lambda: wallet_view(db, principal.user.organization_id, principal.user.id))


@router.get("/wallet/balance")
def balance(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.read")
    view = _run(lambda: wallet_view(db, principal.user.organization_id, principal.user.id))
    return {"available": view["available"], "pending": view["pending"], "confirmed": view["confirmed"], "symbol": view["symbol"]}


@router.get("/wallet/transactions")
def mine_wallet_transactions(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.read")
    return _run(lambda: wallet_transactions(db, principal.user.organization_id, principal.user.id))


@router.post("/wallet/send")
def send(body: SendBody, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.mine")
    _guard(principal, "send")
    return _run(lambda: send_coins(db, principal.user.organization_id, principal.user.id, body.recipient.strip().lower(), body.amount))


@router.post("/mining/start")
def start(body: MineBody | None = None, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.mine")
    _guard(principal, "start")
    cpu = body.cpu_percent if body else None
    return _run(lambda: start_mining(db, principal.user.organization_id, principal.user.id, cpu))


@router.post("/mining/stop")
def stop(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.mine")
    return _run(lambda: stop_mining(db, principal.user.organization_id, principal.user.id))


@router.post("/mining/pause")
def pause(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.mine")
    return _run(lambda: pause_mining(db, principal.user.organization_id, principal.user.id))


@router.post("/mining/resume")
def resume(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.mine")
    return _run(lambda: resume_mining(db, principal.user.organization_id, principal.user.id))


@router.get("/mining/status")
def status(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.read")
    body = _run(lambda: mining_status(db, principal.user.organization_id, principal.user.id))
    db.commit()
    return body


@router.post("/mining/cpu")
def cpu(body: MineBody, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.mine")
    if body.cpu_percent is None:
        raise HTTPException(status_code=400, detail="Choose a CPU limit")
    return _run(lambda: set_cpu(db, principal.user.organization_id, principal.user.id, body.cpu_percent))


@router.get("/dashboard")
def overview(span: str = Query(default="all"), principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.read")
    body = _run(lambda: dashboard(db, principal.user.organization_id, principal.user.id, span))
    db.commit()
    return body


@router.get("/activity")
def activity(
    span: str = Query(default="all"),
    kind: str = Query(default="all"),
    q: str = Query(default=""),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    principal.require("chain.read")
    return _run(lambda: account_activity(db, principal.user.organization_id, principal.user.id, span, kind, q, limit, offset))


@router.get("/mining/statistics")
def statistics(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.read")
    body = _run(lambda: mining_statistics(db, principal.user.organization_id, principal.user.id))
    db.commit()
    return body


@router.get("/mining/plans")
def mining_plans(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.read")
    body = _run(lambda: list_plans(db, principal.user.organization_id, principal.user.id))
    db.commit()
    return body


@router.get("/mining/hybrid")
def mining_hybrid(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.read")
    body = _run(lambda: hybrid_overview(db, principal.user.organization_id, principal.user.id))
    db.commit()
    return body


@router.post("/mining/upgrades")
def mining_upgrade(body: UpgradeBody, request: Request, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.mine")
    _guard(principal, "upgrade")
    result = _run(lambda: purchase_upgrade(db, principal.user, body.plan_id, body.method, request.client.host if request.client else ""))
    db.commit()
    return result


@router.get("/mining/upgrades")
def mining_upgrades(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.read")
    return _run(lambda: list_upgrade_payments(db, principal.user.organization_id, principal.user.id))


@router.get("/mining/rewards")
def mining_rewards(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.read")
    body = _run(lambda: list_reward_rows(db, principal.user.organization_id, principal.user.id, 50))
    db.commit()
    return body


@router.get("/mining/admin/settings")
def mining_admin_settings(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.admin")
    body = _run(lambda: settings_payload(db, principal.user.organization_id))
    db.commit()
    return body


@router.put("/mining/admin/settings")
def mining_admin_save_settings(body: MiningSettingsBody, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.admin")
    result = _run(lambda: update_mining_settings(db, principal.user.organization_id, principal.user.id, body.model_dump(exclude_none=True)))
    db.commit()
    return result


@router.get("/mining/admin/plans")
def mining_admin_plans(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.admin")
    body = _run(lambda: list_plans(db, principal.user.organization_id, principal.user.id, include_disabled=True))
    db.commit()
    return body


@router.post("/mining/admin/plans")
def mining_admin_create_plan(body: MiningPlanBody, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.admin")
    result = _run(lambda: save_plan(db, principal.user.organization_id, principal.user.id, body.model_dump(exclude_none=True)))
    db.commit()
    return result


@router.put("/mining/admin/plans/{plan_id}")
def mining_admin_update_plan(plan_id: str, body: MiningPlanBody, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.admin")
    result = _run(lambda: save_plan(db, principal.user.organization_id, principal.user.id, body.model_dump(exclude_none=True), plan_id))
    db.commit()
    return result


@router.get("/mining/admin/overview")
def mining_admin_overview(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.admin")
    body = _run(lambda: admin_overview(db, principal.user.organization_id))
    db.commit()
    return body


@router.get("/mining/admin/miners")
def mining_admin_miners(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.admin")
    body = _run(lambda: admin_miners(db, principal.user.organization_id))
    db.commit()
    return body


@router.get("/mining/admin/suspicious")
def mining_admin_suspicious(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.admin")
    return _run(lambda: admin_suspicious(db, principal.user.organization_id))


@router.get("/blocks")
def blocks(limit: int = Query(default=50, ge=1, le=200), principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.read")
    return _run(lambda: list_blocks(db, principal.user.organization_id, limit))


@router.get("/blocks/{height}")
def one_block(height: int, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.read")
    return _run(lambda: block_detail(db, principal.user.organization_id, height))


@router.get("/transactions")
def transactions(limit: int = Query(default=50, ge=1, le=200), principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.read")
    return _run(lambda: list_transactions(db, principal.user.organization_id, limit))


@router.get("/transactions/{tx_hash}")
def one_transaction(tx_hash: str, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.read")
    return _run(lambda: transaction_detail(db, principal.user.organization_id, tx_hash.strip().lower()))


@router.get("/search")
def find(q: str = Query(min_length=1, max_length=80), principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.read")
    return _run(lambda: search(db, principal.user.organization_id, q))


@router.get("/conversion/settings")
def conversion_settings(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.read")
    return public_settings(db, principal.user.organization_id)


@router.get("/conversion/quote")
def conversion_quote(amount: str = Query(min_length=1), principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.mine")
    return _run(lambda: preview(db, principal.user.organization_id, principal.user.id, amount))


@router.post("/conversion")
def conversion(body: ConvertBody, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.mine")
    _guard(principal, "convert")
    return _run(lambda: convert(db, principal.user.organization_id, principal.user.id, body.amount, body.reference))


@router.get("/conversion/wallet")
def conversion_wallet(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.read")
    return _run(lambda: wallet_conversion(db, principal.user.organization_id, principal.user.id))


@router.put("/conversion/settings")
def save_conversion_settings(body: ConversionSettingsBody, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.admin")
    return _run(lambda: update_settings(db, principal.user.organization_id, principal.user.id, rate=body.rate, enabled=body.enabled, min_pcoin=body.min_pcoin, max_pcoin=body.max_pcoin, fee_bps=body.fee_bps))


@router.get("/conversion/report")
def conversion_report(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.admin")
    return report(db, principal.user.organization_id)


@router.get("/conversion/history")
def conversion_history(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.admin")
    return list_conversions(db, principal.user.organization_id)


@router.get("/conversion/export")
def conversion_export(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.admin")
    return PlainTextResponse(export_csv(db, principal.user.organization_id), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=pcoin-conversions.csv"})


@router.get("/network/status")
def network(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.require("chain.read")
    return _run(lambda: network_status(db, principal.user.organization_id))
