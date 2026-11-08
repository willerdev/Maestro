from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.connectors.registry import connector_for
from app.services.connection_probe import MetaApiTokenError, probe_connection, resolve_metaapi_credentials
from app.services.pocket_browser import PocketLoginError, close_login, login_status
from app.core.encryption import decrypt_json, encrypt_json
from app.core.security import new_token, sha256_hex
from app.domain.audit import write_audit
from app.domain.rbac import allows
from app.domain.ruleset import DEFAULT_RULES
from app.models.chain_entities import ContractStake, ContractYield
from app.models.entities import (
    Account,
    AccountConnection,
    AccountCredential,
    AccountGrant,
    AccountGroupMember,
    AccountSnapshot,
    AccountState,
    AiRequest,
    Alert,
    BrokerCommand,
    ClosedTrade,
    CopyDecision,
    CopyLink,
    DailyStatistic,
    DrawdownSnapshot,
    EmergencyAction,
    EquitySnapshot,
    ExecutionSample,
    FundAllocation,
    FundBookAccount,
    MarketQuote,
    NakedLimit,
    Notification,
    NotificationDelivery,
    OrderRow,
    OvertradingRow,
    Position,
    ReconciliationEvent,
    RiskDecisionRow,
    RiskProfile,
    RiskRule,
    RiskViolation,
    SetupWatch,
    StrategyAccount,
    SymbolSpecRow,
    TradeMilestone,
    TraderAccount,
    User,
    WebhookEndpoint,
    WebhookInbox,
    WebhookNonce,
)

METHODS = {"metaapi", "local_mt5", "passprop", "webhook", "pocketoption", "blockchain", "mining"}


class AccountError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        self.status = status
        self.detail = detail


def _pocket_credentials(credentials: dict, user_id: str) -> dict:
    session_id = str(credentials.get("pocket_session_id") or "").strip()
    if not session_id:
        raise PocketLoginError("Open the Pocket Option window and sign in")
    chosen = str(credentials.get("active_mode") or "").strip().lower()
    body = login_status(session_id, user_id).credentials()
    if chosen in {"demo", "real"}:
        body["active_mode"] = chosen
    return body


def _pocket_active_mode(credentials: dict) -> str:
    chosen = str(credentials.get("active_mode") or "").strip().lower()
    if chosen in {"demo", "real"}:
        return chosen
    return "real" if str(credentials.get("real_ssid") or "").strip() else "demo"


def ensure_default_profile(db: Session, organization_id: UUID) -> RiskProfile:
    profile = db.scalar(
        select(RiskProfile).where(
            RiskProfile.organization_id == organization_id,
            RiskProfile.is_default.is_(True),
            RiskProfile.account_id.is_(None),
        )
    )
    if profile:
        return profile
    profile = RiskProfile(organization_id=organization_id, name="Organization default", is_default=True)
    db.add(profile)
    db.flush()
    _fill_rules(db, profile.id)
    return profile


def ensure_account_profile(db: Session, account: Account) -> RiskProfile:
    profile = db.scalar(select(RiskProfile).where(RiskProfile.account_id == account.id))
    if profile:
        return profile
    profile = RiskProfile(
        organization_id=account.organization_id,
        account_id=account.id,
        name=f"{account.display_name} rules",
        is_default=False,
    )
    db.add(profile)
    db.flush()
    _fill_rules(db, profile.id)
    return profile


def _fill_rules(db: Session, profile_id: UUID) -> None:
    for code, value in DEFAULT_RULES.items():
        if isinstance(value, bool):
            db.add(RiskRule(profile_id=profile_id, code=code, bool_value=value, enabled=False))
        else:
            db.add(RiskRule(profile_id=profile_id, code=code, numeric_value=Decimal(value), enabled=False))


def ensure_rule_row(db: Session, profile_id: UUID, code: str) -> RiskRule:
    row = db.scalar(select(RiskRule).where(RiskRule.profile_id == profile_id, RiskRule.code == code))
    if row is not None:
        return row
    value = DEFAULT_RULES[code]
    if isinstance(value, bool):
        row = RiskRule(profile_id=profile_id, code=code, bool_value=value, enabled=False)
    else:
        row = RiskRule(profile_id=profile_id, code=code, numeric_value=Decimal(value), enabled=False)
    db.add(row)
    db.flush()
    return row


def visible_account_query(db: Session, user: User, roles: list[str]):
    query = select(Account).where(Account.organization_id == user.organization_id)
    if any(role in {"SUPER_ADMIN", "ADMIN", "RISK_MANAGER"} for role in roles) or allows(roles, "users.manage"):
        return query
    grant_ids = select(AccountGrant.account_id).where(AccountGrant.user_id == user.id)
    return query.where(Account.id.in_(grant_ids))


def get_visible_account(db: Session, user: User, roles: list[str], account_id: UUID) -> Account:
    account = db.scalar(visible_account_query(db, user, roles).where(Account.id == account_id))
    if account is None:
        raise AccountError(404, "Account not found")
    return account


def _money(value: object) -> Decimal:
    try:
        return Decimal(str(value if value not in (None, "") else "0"))
    except Exception:  # noqa: BLE001
        return Decimal("0")


def create_account(db: Session, user: User, roles: list[str], payload: dict, ip: str) -> tuple[Account, dict | None]:
    method = payload["connection_method"]
    if method not in METHODS:
        raise AccountError(400, "Unsupported connection method")
    from app.services.system_config_service import method_is_open

    if not method_is_open(db, user.organization_id, method):
        raise AccountError(400, "This account type is not available")
    credentials = dict(payload.get("credentials") or {})
    if method in {"metaapi", "passprop"}:
        try:
            from app.services.system_config_service import metaapi_token

            credentials = resolve_metaapi_credentials(credentials, fallback_token=metaapi_token(db, user.organization_id))
        except MetaApiTokenError as exc:
            raise AccountError(400, exc.detail) from exc
    prop = _passprop_fields(credentials) if method == "passprop" else None
    pocket_session_id = ""
    if method == "pocketoption":
        pocket_session_id = str(credentials.get("pocket_session_id") or "").strip()
        try:
            credentials = _pocket_credentials(credentials, str(user.id))
        except PocketLoginError as exc:
            raise AccountError(400, exc.detail) from exc
    found = None
    connected = False
    desk = (
        method in {"blockchain", "mining"}
        and bool(credentials.get("accepted_terms"))
        and not str(credentials.get("wallet_address") or "").strip()
        and not str(credentials.get("mining_address") or "").strip()
    )
    if desk:
        if method == "mining":
            display_name, account_number, broker, server, currency = (
                "Project Coin",
                "project-coin",
                "Project Coin",
                "maestro",
                "PCOIN",
            )
        else:
            display_name, account_number, broker, server, currency = (
                "Blockchain contracts",
                "contracts",
                "Blockchain",
                "maestro",
                "USD",
            )
        leverage = "1"
        connected = True
        credentials = {}
    elif method in {"metaapi", "local_mt5", "passprop", "pocketoption", "blockchain", "mining"}:
        probed = probe_connection(method, credentials)
        if not probed["ok"] or not probed.get("account"):
            raise AccountError(400, probed.get("detail") or "Connection check failed")
        found = probed["account"]
        if not str(found.get("account_number") or "").strip():
            raise AccountError(400, "The terminal did not return an account number")
        if method in {"metaapi", "passprop"}:
            credentials["region"] = probed["region"]
            account_id = str(probed.get("metaapi_account_id") or "").strip()
            if account_id:
                credentials["metaapi_account_id"] = account_id
            if found.get("broker"):
                credentials["broker"] = str(found["broker"])
        if method == "pocketoption":
            if probed.get("region"):
                credentials["ws_url"] = probed["region"]
            if found.get("account_number"):
                credentials["uid"] = str(found["account_number"])
            for mode in ("demo", "real"):
                side = probed.get(mode)
                if isinstance(side, dict) and side.get("balance") not in (None, "", "—"):
                    credentials[f"{mode}_balance"] = side["balance"]
                    credentials[f"{mode}_currency"] = side.get("currency") or "USD"
            credentials["active_mode"] = _pocket_active_mode(credentials)
        display_name = str(found["display_name"]).strip() or str(found["account_number"])
        account_number = str(found["account_number"]).strip()
        broker = str(found.get("broker") or "").strip()
        if prop:
            credentials["firm_name"] = prop["firm_name"]
            credentials["firm_url"] = prop["firm_url"]
            credentials["rules"] = prop["rules"]
            credentials["account_size"] = prop["account_size"]
            display_name = f"{prop['firm_name']} · {prop['account_size']}"
            broker = prop["firm_name"]
        server = str(found.get("server") or "").strip()
        if method == "pocketoption":
            server = str(credentials.get("active_mode") or server or "real")
        currency = str(found.get("currency") or "USD").upper()
        leverage = str(found.get("leverage") or "100")
        connected = True
    else:
        display_name = str(payload.get("display_name") or "").strip()
        account_number = str(payload.get("account_number") or "").strip()
        if not display_name or not account_number:
            raise AccountError(400, "Webhook accounts need a display name and account number")
        broker = str(payload.get("broker") or "").strip()
        server = str(payload.get("server") or "").strip()
        currency = str(payload.get("currency") or "USD").upper()
        leverage = str(payload.get("leverage") or "100")
    alias = str(payload.get("display_name") or "").strip()[:160]
    if alias:
        display_name = alias
    existing = db.scalar(
        select(Account).where(
            Account.organization_id == user.organization_id,
            Account.broker == broker,
            Account.server == server,
            Account.account_number == account_number,
        )
    )
    if existing is not None:
        if desk:
            return existing, None
        raise AccountError(409, "That account is already on the running list")
    counts = _owned_counts(db, user.id)
    limit = _method_limit(method)
    if counts.get(method, 0) >= limit:
        if method == "local_mt5":
            raise AccountError(409, "You can add up to 10 MetaTrader accounts.")
        if method == "passprop":
            raise AccountError(409, "You can add up to 10 Pass Props accounts.")
        raise AccountError(409, "You already have one account of this type.")
    now = datetime.now(timezone.utc)
    account = Account(
        organization_id=user.organization_id,
        display_name=display_name,
        broker=broker,
        server=server,
        account_number=account_number,
        connection_method=method,
        currency=currency,
        leverage=Decimal(str(leverage)),
        trading_day_timezone=payload.get("trading_day_timezone") or "UTC",
        status="connected" if connected else "pending",
    )
    db.add(account)
    db.flush()
    db.add(AccountGrant(account_id=account.id, user_id=user.id))
    state = AccountState(account_id=account.id)
    if found:
        state.balance = _money(found.get("balance"))
        state.equity = _money(found.get("equity"))
        state.margin = _money(found.get("margin"))
        state.free_margin = _money(found.get("free_margin"))
        level = found.get("margin_level")
        state.margin_level = None if level in (None, "") else _money(level)
        state.peak_equity = state.equity
        state.day_start_equity = state.equity
        state.as_of = now
    db.add(state)
    db.add(
        AccountConnection(
            account_id=account.id,
            method=method,
            status="connected" if connected else "pending",
            last_success_at=now if connected else None,
        )
    )
    ensure_account_profile(db, account)
    secret_bundle = None
    if credentials:
        nonce, ciphertext = encrypt_json(credentials)
        db.add(AccountCredential(account_id=account.id, nonce=nonce, ciphertext=ciphertext))
    if method == "webhook":
        secret_bundle = _issue_webhook(db, account)
    write_audit(
        db,
        organization_id=user.organization_id,
        actor_user_id=user.id,
        action="account_created",
        entity_type="account",
        entity_id=str(account.id),
        after={"display_name": account.display_name, "method": method, "account_number": account.account_number},
        ip_address=ip,
    )
    if pocket_session_id:
        try:
            close_login(pocket_session_id, str(user.id))
        except PocketLoginError:
            pass
    return account, secret_bundle


def update_account(db: Session, user: User, account: Account, payload: dict, ip: str) -> Account:
    before = {"display_name": account.display_name, "broker": account.broker, "server": account.server}
    for field in ("display_name", "broker", "server", "trading_day_timezone"):
        if payload.get(field) is not None:
            setattr(account, field, str(payload[field]).strip())
    if payload.get("leverage") is not None:
        account.leverage = Decimal(str(payload["leverage"]))
    if "ai_trading_enabled" in payload:
        account.ai_trading_enabled = bool(payload["ai_trading_enabled"])
    if "risk_blocks_paused" in payload:
        account.risk_blocks_paused = bool(payload["risk_blocks_paused"])
    if payload.get("credentials"):
        nonce, ciphertext = encrypt_json(payload["credentials"])
        row = db.scalar(select(AccountCredential).where(AccountCredential.account_id == account.id))
        if row is None:
            db.add(AccountCredential(account_id=account.id, nonce=nonce, ciphertext=ciphertext))
        else:
            row.nonce = nonce
            row.ciphertext = ciphertext
            row.rotated_at = datetime.now(timezone.utc)
    account.updated_at = datetime.now(timezone.utc)
    write_audit(
        db,
        organization_id=user.organization_id,
        actor_user_id=user.id,
        action="account_updated",
        entity_type="account",
        entity_id=str(account.id),
        before=before,
        after={
            "display_name": account.display_name,
            "broker": account.broker,
            "server": account.server,
            "ai_trading_enabled": account.ai_trading_enabled,
            "risk_blocks_paused": account.risk_blocks_paused,
        },
        ip_address=ip,
    )
    return account


def load_credentials(db: Session, account_id: UUID) -> dict:
    row = db.scalar(select(AccountCredential).where(AccountCredential.account_id == account_id))
    if row is None:
        return {}
    return decrypt_json(row.nonce, row.ciphertext)


def set_monitoring(db: Session, user: User, account: Account, enabled: bool, ip: str) -> Account:
    account.monitoring_enabled = enabled
    write_audit(
        db,
        organization_id=user.organization_id,
        actor_user_id=user.id,
        action="monitoring_changed",
        entity_type="account",
        entity_id=str(account.id),
        after={"monitoring_enabled": enabled},
        ip_address=ip,
    )
    return account


def connect_account(db: Session, user: User, account: Account, ip: str) -> Account:
    account.status = "pending"
    connection = _connection(db, account)
    connection.status = "pending"
    endpoint = db.scalar(select(WebhookEndpoint).where(WebhookEndpoint.account_id == account.id))
    if endpoint:
        endpoint.enabled = True
    write_audit(
        db,
        organization_id=user.organization_id,
        actor_user_id=user.id,
        action="account_connect",
        entity_type="account",
        entity_id=str(account.id),
        ip_address=ip,
    )
    return account


def disconnect_account(db: Session, user: User, account: Account, ip: str) -> Account:
    account.status = "disconnected"
    connection = _connection(db, account)
    connection.status = "disconnected"
    endpoint = db.scalar(select(WebhookEndpoint).where(WebhookEndpoint.account_id == account.id))
    if endpoint:
        endpoint.enabled = False
    write_audit(
        db,
        organization_id=user.organization_id,
        actor_user_id=user.id,
        action="account_disconnect",
        entity_type="account",
        entity_id=str(account.id),
        ip_address=ip,
    )
    return account


def test_connection(db: Session, user: User, account: Account, ip: str) -> dict:
    connection = _connection(db, account)
    if account.connection_method == "webhook":
        if connection.last_heartbeat_at is None:
            result = {"ok": False, "status": "waiting_for_heartbeat", "error_code": "no_heartbeat"}
        else:
            age = (datetime.now(timezone.utc) - connection.last_heartbeat_at).total_seconds()
            fresh = age <= 90
            result = {"ok": fresh, "status": "connected" if fresh else "stale", "error_code": "" if fresh else "heartbeat_stale", "age_seconds": int(age)}
    else:
        adapter = connector_for(account.connection_method)
        credentials = load_credentials(db, account.id)
        tested = adapter.test_connection(credentials) if adapter else None
        if tested is None:
            result = {"ok": False, "status": "unsupported", "error_code": "unsupported_method"}
        else:
            result = {"ok": tested.ok, "status": tested.status, "error_code": tested.error_code, "detail": tested.detail}
            if tested.ok:
                account.status = "connected"
                connection.status = "connected"
                connection.last_success_at = datetime.now(timezone.utc)
                connection.last_error_code = ""
                fetch_account = getattr(adapter, "fetch_account", None)
                if fetch_account is not None:
                    try:
                        from app.services.live_trades import _apply_live_state

                        _apply_live_state(db, account, fetch_account(credentials))
                    except Exception:
                        pass
            else:
                connection.last_error_code = tested.error_code
                connection.status = "degraded"
    write_audit(
        db,
        organization_id=user.organization_id,
        actor_user_id=user.id,
        action="account_connection_tested",
        entity_type="account",
        entity_id=str(account.id),
        after={"status": result["status"], "ok": result["ok"]},
        ip_address=ip,
    )
    return result


def rotate_webhook(db: Session, user: User, account: Account, ip: str) -> dict:
    if account.connection_method != "webhook":
        raise AccountError(400, "Webhook credentials belong to webhook accounts")
    endpoint = db.scalar(select(WebhookEndpoint).where(WebhookEndpoint.account_id == account.id))
    if endpoint:
        db.delete(endpoint)
        db.flush()
    bundle = _issue_webhook(db, account)
    write_audit(
        db,
        organization_id=user.organization_id,
        actor_user_id=user.id,
        action="webhook_rotated",
        entity_type="account",
        entity_id=str(account.id),
        ip_address=ip,
    )
    return bundle


def _issue_webhook(db: Session, account: Account) -> dict:
    token = new_token(24)
    api_key = f"tg_{new_token(24)}"
    secret = new_token(32)
    nonce, ciphertext = encrypt_json({"secret": secret})
    db.add(
        WebhookEndpoint(
            account_id=account.id,
            token=token,
            api_key_hash=sha256_hex(api_key),
            secret_nonce=nonce,
            secret_ciphertext=ciphertext,
        )
    )
    return {
        "url_path": f"/api/v1/webhooks/mt5/{token}",
        "token": token,
        "api_key": api_key,
        "signing_secret": secret,
    }


def _method_limit(method: str) -> int:
    return 10 if method in {"local_mt5", "passprop"} else 1


def pocket_public(db: Session, account: Account) -> dict | None:
    if account.connection_method != "pocketoption":
        return None
    creds = load_credentials(db, account.id)
    session = bool(str(creds.get("demo_ssid") or "").strip() or str(creds.get("real_ssid") or "").strip())
    has_demo = session
    has_real = session
    mode = str(creds.get("active_mode") or "").strip().lower()
    if mode not in {"demo", "real"}:
        mode = "real" if str(creds.get("real_ssid") or "").strip() else "demo"

    def money(key: str) -> str | None:
        raw = creds.get(key)
        if raw in (None, "", "—", "-"):
            return None
        return str(raw)

    return {
        "mode": mode,
        "has_demo": has_demo,
        "has_real": has_real,
        "demo_balance": money("demo_balance"),
        "real_balance": money("real_balance"),
        "demo_currency": str(creds.get("demo_currency") or "USD"),
        "real_currency": str(creds.get("real_currency") or "USD"),
    }


def _write_credentials(db: Session, account: Account, creds: dict, now: datetime | None = None) -> None:
    nonce, ciphertext = encrypt_json(creds)
    row = db.scalar(select(AccountCredential).where(AccountCredential.account_id == account.id))
    stamp = now or datetime.now(timezone.utc)
    if row is None:
        db.add(AccountCredential(account_id=account.id, nonce=nonce, ciphertext=ciphertext))
        return
    row.nonce = nonce
    row.ciphertext = ciphertext
    row.rotated_at = stamp


def _apply_pocket_book(db: Session, account: Account, creds: dict, mode: str) -> None:
    raw = creds.get(f"{mode}_balance")
    if raw in (None, "", "—", "-"):
        return
    try:
        money = Decimal(str(raw))
    except Exception:
        return
    state = db.get(AccountState, account.id)
    if state is None:
        return
    now = datetime.now(timezone.utc)
    state.balance = money
    state.equity = money
    state.free_margin = money
    state.margin = Decimal("0")
    state.as_of = now
    state.stale = False
    currency = str(creds.get(f"{mode}_currency") or "").strip()
    if currency:
        account.currency = currency


def set_pocket_mode(db: Session, user: User, account: Account, mode: str, ip: str) -> Account:
    if account.connection_method != "pocketoption":
        raise AccountError(400, "This is not a Pocket Option account")
    chosen = str(mode or "").strip().lower()
    if chosen not in {"demo", "real"}:
        raise AccountError(400, "Choose Demo or Real")
    creds = dict(load_credentials(db, account.id))
    source = str(creds.get(f"{chosen}_ssid") or creds.get("real_ssid") or creds.get("demo_ssid") or "").strip()
    if not source:
        raise AccountError(400, "That book is not captured yet. Open the Pocket Option window and sign in on Demo and Real.")
    creds["active_mode"] = chosen
    if not str(creds.get(f"{chosen}_ssid") or "").strip():
        creds[f"{chosen}_ssid"] = source
    now = datetime.now(timezone.utc)
    _write_credentials(db, account, creds, now)
    account.server = chosen
    account.updated_at = now
    _apply_pocket_book(db, account, creds, chosen)
    from app.services.live_trades import clear_pocket_throttle, refresh_terminal

    clear_pocket_throttle(account.id)
    error = refresh_terminal(db, account)
    creds = dict(load_credentials(db, account.id))
    creds["active_mode"] = chosen
    state = db.get(AccountState, account.id)
    if error is None and state is not None:
        creds[f"{chosen}_balance"] = f"{state.balance:.2f}"
        creds[f"{chosen}_currency"] = str(account.currency or creds.get(f"{chosen}_currency") or "USD")
        _write_credentials(db, account, creds, now)
    write_audit(
        db,
        organization_id=user.organization_id,
        actor_user_id=user.id,
        action="pocket_mode_changed",
        entity_type="account",
        entity_id=str(account.id),
        after={"mode": chosen},
        ip_address=ip,
    )
    return account


def passprop_public(db: Session, account: Account) -> dict:
    if account.connection_method != "passprop":
        return {}
    creds = load_credentials(db, account.id)
    return {
        "firm_name": str(creds.get("firm_name") or account.broker or "")[:160],
        "firm_url": str(creds.get("firm_url") or "")[:500],
        "rules": str(creds.get("rules") or "")[:20000],
        "account_size": str(creds.get("account_size") or "")[:40],
    }


def _passprop_fields(credentials: dict) -> dict:
    firm = str(credentials.get("firm_name") or "").strip()[:160]
    url = str(credentials.get("firm_url") or "").strip()[:500]
    rules = str(credentials.get("rules") or "").strip()[:20000]
    size = str(credentials.get("account_size") or "").strip().replace(",", "")[:40]
    if len(firm) < 2:
        raise AccountError(400, "Enter the prop firm name")
    if url and not url.startswith(("http://", "https://")):
        raise AccountError(400, "Enter the firm URL starting with https://")
    if not size:
        raise AccountError(400, "Enter the account size")
    return {"firm_name": firm, "firm_url": url, "rules": rules, "account_size": size}


def _owned_counts(db: Session, user_id: UUID) -> dict[str, int]:
    rows = db.execute(
        select(Account.connection_method, func.count())
        .join(AccountGrant, AccountGrant.account_id == Account.id)
        .where(AccountGrant.user_id == user_id)
        .group_by(Account.connection_method)
    ).all()
    return {str(method): int(count) for method, count in rows}


def system_overview(db: Session, user: User) -> dict:
    from app.services.system_config_service import account_type_flags

    counts = _owned_counts(db, user.id)
    limits = {method: _method_limit(method) for method in sorted(METHODS)}
    owned = {method: counts.get(method, 0) for method in limits}
    enabled = account_type_flags(db, user.organization_id)
    return {
        "counts": owned,
        "limits": limits,
        "enabled": enabled,
        "can_add": any(enabled.get(method, True) and owned[method] < limits[method] for method in limits),
    }


def _clear_account_rows(db: Session, account_id: UUID) -> None:
    stake_ids = select(ContractStake.id).where(ContractStake.account_id == account_id)
    db.execute(delete(ContractYield).where(ContractYield.stake_id.in_(stake_ids)))
    db.execute(delete(ContractStake).where(ContractStake.account_id == account_id))
    link_ids = select(CopyLink.id).where(
        or_(CopyLink.master_account_id == account_id, CopyLink.follower_account_id == account_id)
    )
    db.execute(delete(CopyDecision).where(or_(CopyDecision.follower_account_id == account_id, CopyDecision.link_id.in_(link_ids))))
    db.execute(delete(CopyLink).where(or_(CopyLink.master_account_id == account_id, CopyLink.follower_account_id == account_id)))
    endpoint_ids = select(WebhookEndpoint.id).where(WebhookEndpoint.account_id == account_id)
    db.execute(delete(WebhookInbox).where(WebhookInbox.endpoint_id.in_(endpoint_ids)))
    db.execute(delete(WebhookNonce).where(WebhookNonce.endpoint_id.in_(endpoint_ids)))
    db.execute(delete(WebhookEndpoint).where(WebhookEndpoint.account_id == account_id))
    alert_ids = select(Alert.id).where(Alert.account_id == account_id)
    note_ids = select(Notification.id).where(Notification.alert_id.in_(alert_ids))
    db.execute(delete(NotificationDelivery).where(NotificationDelivery.notification_id.in_(note_ids)))
    db.execute(delete(Notification).where(Notification.alert_id.in_(alert_ids)))
    db.execute(delete(Alert).where(Alert.account_id == account_id))
    profile_ids = select(RiskProfile.id).where(RiskProfile.account_id == account_id)
    db.execute(delete(RiskRule).where(RiskRule.profile_id.in_(profile_ids)))
    decision_ids = select(RiskDecisionRow.id).where(RiskDecisionRow.account_id == account_id)
    db.execute(delete(RiskViolation).where(or_(RiskViolation.account_id == account_id, RiskViolation.decision_id.in_(decision_ids))))
    db.execute(delete(RiskDecisionRow).where(RiskDecisionRow.account_id == account_id))
    db.execute(delete(RiskProfile).where(RiskProfile.account_id == account_id))
    for model in (
        AccountSnapshot,
        SymbolSpecRow,
        TradeMilestone,
        ClosedTrade,
        Position,
        OrderRow,
        MarketQuote,
        OvertradingRow,
        EmergencyAction,
        BrokerCommand,
        SetupWatch,
        NakedLimit,
        AiRequest,
        EquitySnapshot,
        DrawdownSnapshot,
        DailyStatistic,
        AccountGroupMember,
        StrategyAccount,
        TraderAccount,
        FundBookAccount,
        ExecutionSample,
        ReconciliationEvent,
        FundAllocation,
        AccountGrant,
        AccountCredential,
        AccountConnection,
        AccountState,
    ):
        db.execute(delete(model).where(model.account_id == account_id))


def delete_account(db: Session, user: User, roles: list[str], account_id: UUID, ip: str) -> None:
    import time

    from app.services.live_trades import pause_pocket_refresh

    account = get_visible_account(db, user, roles, account_id)
    before = {"display_name": account.display_name, "method": account.connection_method, "account_number": account.account_number}
    pause_pocket_refresh(account.id)
    account.status = "disconnected"
    account.monitoring_enabled = False
    connection = db.scalar(select(AccountConnection).where(AccountConnection.account_id == account.id))
    if connection is not None:
        connection.status = "disconnected"
        connection.last_success_at = None
    write_audit(
        db,
        organization_id=user.organization_id,
        actor_user_id=user.id,
        action="account_deleted",
        entity_type="account",
        entity_id=str(account.id),
        before=before,
        ip_address=ip,
    )
    db.commit()
    for _ in range(5):
        _clear_account_rows(db, account_id)
        db.expire_all()
        row = db.get(Account, account_id)
        if row is None:
            return
        nested = db.begin_nested()
        try:
            db.delete(row)
            db.flush()
        except IntegrityError:
            nested.rollback()
            time.sleep(0.2)
            continue
        nested.commit()
        try:
            db.commit()
            return
        except IntegrityError:
            db.rollback()
            time.sleep(0.2)
    raise AccountError(409, "This account still has linked records and could not be removed")


def _connection(db: Session, account: Account) -> AccountConnection:
    connection = db.scalar(select(AccountConnection).where(AccountConnection.account_id == account.id))
    if connection is None:
        connection = AccountConnection(account_id=account.id, method=account.connection_method)
        db.add(connection)
        db.flush()
    return connection
