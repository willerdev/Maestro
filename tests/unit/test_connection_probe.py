import httpx

from app.connectors.metaapi import MetaApiConnector

_ACCOUNT = "1eda642a-a9a3-457c-99af-3bc5e8d5c4c9"


def _provision(**overrides):
    body = {
        "_id": _ACCOUNT,
        "login": "50194988",
        "name": "mt5a",
        "server": "ICMarketsSC-Demo",
        "state": "DEPLOYED",
        "connectionStatus": "CONNECTED",
        "region": "london",
        "baseCurrency": "USD",
    }
    body.update(overrides)
    return body


def test_metaapi_region_and_identity_come_from_the_token_lookup():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["auth-token"] == "secret-token"
        if "provisioning" in str(request.url):
            return httpx.Response(200, json=_provision())
        assert "mt-client-api-v1.london.agiliumtrade.ai" in str(request.url)
        return httpx.Response(
            200,
            json={
                "login": 50194988,
                "name": "mt5a",
                "server": "ICMarketsSC-Demo",
                "broker": "Raw Trading Ltd",
                "currency": "USD",
                "leverage": 500,
                "balance": 1000,
                "equity": 990,
                "margin": 0,
                "freeMargin": 990,
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = MetaApiConnector().inspect(
            {"token": "secret-token", "metaapi_account_id": _ACCOUNT},
            client,
        )
    assert result["ok"] is True
    assert result["region"] == "london"
    assert result["account"]["account_number"] == "50194988"
    assert result["account"]["broker"] == "Raw Trading Ltd"
    assert result["account"]["leverage"] == "500"
    assert "secret-token" not in str(result)


def test_nowpayments_payment_returns_a_deposit_address():
    import json
    from decimal import Decimal

    from app.connectors.payments import NowPaymentsConnector

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if request.method == "POST" and url.endswith("/payment"):
            body = json.loads(request.content)
            assert body["pay_currency"] == "usdttrc20"
            assert body["price_currency"] == "usdttrc20"
            return httpx.Response(
                201,
                json={"payment_id": "pay_1", "pay_address": "TXYZDEPOSITADDRESS000000000000000", "pay_amount": "10", "pay_currency": "usdttrc20", "payment_status": "waiting"},
            )
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = NowPaymentsConnector().create_payment(
            {"api_key": "now-key-123456", "api_url": "https://api.nowpayments.io/v1"},
            sandbox=False,
            price_amount=Decimal("10"),
            price_currency="usdttrc20",
            pay_currency="usdttrc20",
            order_id="order1",
            description="deposit",
            callback_url="https://desk.example/ipn",
            client=client,
        )
    assert result["pay_address"].startswith("T")
    assert result["provider_payment_id"] == "pay_1"


def test_metaapi_creates_cloud_account_from_broker_login():
    created = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if request.method == "GET" and url.rstrip("/").endswith("/accounts"):
            return httpx.Response(200, json=[])
        if request.method == "POST" and url.rstrip("/").endswith("/accounts"):
            created.append(request.content)
            return httpx.Response(201, json={"id": _ACCOUNT})
        if request.method == "POST" and url.endswith("/deploy"):
            return httpx.Response(204)
        if "account-information" in url:
            return httpx.Response(
                200,
                json={
                    "login": 50194988,
                    "name": "mt5a",
                    "server": "ICMarketsSC-Demo",
                    "company": "Raw Trading Ltd",
                    "currency": "USD",
                    "leverage": 500,
                    "balance": 1000,
                    "equity": 990,
                },
            )
        return httpx.Response(200, json=_provision())

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = MetaApiConnector().inspect(
            {
                "token": "secret-token",
                "broker": "IC Markets",
                "server": "ICMarketsSC-Demo",
                "login": "50194988",
                "password": "broker-password",
            },
            client,
        )
    assert result["ok"] is True
    assert result["metaapi_account_id"] == _ACCOUNT
    assert result["account"]["broker"] == "IC Markets"
    assert result["account"]["account_number"] == "50194988"
    assert b"broker-password" in created[0]
    assert "broker-password" not in str(result)
    assert "secret-token" not in str(result)


def test_metaapi_reuses_existing_cloud_account():
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if request.method == "POST":
            return httpx.Response(500, json={"message": "should reuse"})
        if url.rstrip("/").endswith("/accounts"):
            return httpx.Response(200, json=[_provision()])
        if "account-information" in url:
            return httpx.Response(
                200,
                json={"login": 50194988, "name": "mt5a", "server": "ICMarketsSC-Demo", "broker": "Raw Trading Ltd", "currency": "USD", "leverage": 500},
            )
        return httpx.Response(200, json=_provision())

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = MetaApiConnector().inspect(
            {"token": "secret-token", "broker": "IC Markets", "server": "ICMarketsSC-Demo", "login": "50194988", "password": "pw"},
            client,
        )
    assert result["ok"] is True
    assert result["metaapi_account_id"] == _ACCOUNT


def test_metaapi_disconnected_account_cannot_continue():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "provisioning" in str(request.url)
        return httpx.Response(200, json=_provision(connectionStatus="DISCONNECTED"))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = MetaApiConnector().inspect({"token": "secret-token", "metaapi_account_id": _ACCOUNT}, client)
    assert result["ok"] is False
    assert result["error_code"] == "metaapi_not_connected"
    assert result["region"] == ""
