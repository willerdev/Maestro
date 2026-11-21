from __future__ import annotations

PLATFORMS: dict[str, dict[str, object]] = {
    "pocketoption": {
        "code": "pocketoption",
        "label": "Pocket Option",
        "login_url": "https://pocketoption.com/en/login",
        "demo_url": "https://pocketoption.com/en/cabinet/demo-quick-high-low/",
        "real_url": "https://pocketoption.com/en/cabinet/quick-high-low/",
        "hosts": ("pocketoption.com", "po.market"),
    },
    "iqoption": {
        "code": "iqoption",
        "label": "IQ Option",
        "login_url": "https://login.iqoption.com/en/login",
        "demo_url": "https://iqoption.com/en/traderoom",
        "real_url": "https://iqoption.com/en/traderoom",
        "hosts": ("iqoption.com",),
    },
    "quotex": {
        "code": "quotex",
        "label": "Quotex",
        "login_url": "https://qxbroker.com/en/sign-in",
        "demo_url": "https://qxbroker.com/en/demo-trade",
        "real_url": "https://qxbroker.com/en/trade",
        "hosts": ("qxbroker.com", "quotex.com"),
    },
    "deriv": {
        "code": "deriv",
        "label": "Deriv",
        "login_url": "https://oauth.deriv.com/oauth2/pages/login/index.html",
        "demo_url": "https://app.deriv.com",
        "real_url": "https://app.deriv.com",
        "hosts": ("deriv.com", "binary.com"),
    },
    "olymptrade": {
        "code": "olymptrade",
        "label": "Olymp Trade",
        "login_url": "https://olymptrade.com/login",
        "demo_url": "https://olymptrade.com/platform",
        "real_url": "https://olymptrade.com/platform",
        "hosts": ("olymptrade.com",),
    },
}

CODES = tuple(PLATFORMS)
BROWSER_SESSION = "browser-session"
METHOD = "pocketoption"
METHOD_LABEL = "Options Trading"
CHOOSE_METHODS = "Choose MetaAPI, MetaTrader 5, Pass Props, Options Trading, contracts, or mining"


def normalize_platform(value: object) -> str:
    code = str(value or "").strip().lower().replace(" ", "").replace("_", "")
    aliases = {
        "pocket": "pocketoption",
        "pocketoptions": "pocketoption",
        "iq": "iqoption",
        "iqoptions": "iqoption",
        "qx": "quotex",
        "olymp": "olymptrade",
        "olymptrade": "olymptrade",
    }
    code = aliases.get(code, code)
    if code not in PLATFORMS:
        raise ValueError("Choose Pocket Option, IQ Option, Quotex, Deriv, or Olymp Trade")
    return code


def platform_of(credentials: dict | None) -> str:
    creds = credentials or {}
    raw = creds.get("options_platform") or creds.get("platform") or ""
    try:
        if raw:
            return normalize_platform(raw)
    except ValueError:
        pass
    broker = str(creds.get("broker") or "").strip().lower()
    for code, row in PLATFORMS.items():
        if broker == str(row["label"]).lower():
            return code
    return "pocketoption"


def platform_row(code: str) -> dict[str, object]:
    return PLATFORMS.get(code) or PLATFORMS["pocketoption"]


def platform_label(code: str) -> str:
    return str(platform_row(code)["label"])


def platform_from_broker(broker: str) -> str | None:
    name = str(broker or "").strip().lower()
    for code, row in PLATFORMS.items():
        if name == str(row["label"]).lower():
            return code
    return None


def is_pocket_live(credentials: dict | None) -> bool:
    creds = credentials or {}
    if platform_of(creds) != "pocketoption":
        return False
    wire = str(creds.get("real_ssid") or creds.get("demo_ssid") or "")
    return "auth" in wire or wire.startswith("42")


def public_platforms() -> list[dict[str, str]]:
    return [{"code": str(row["code"]), "label": str(row["label"])} for row in PLATFORMS.values()]
