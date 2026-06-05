import httpx

from sensortower import client as sensortower_client


def test_sales_estimates_uses_api_key_alias_and_expected_query(monkeypatch):
    def fake_secret(name: str, default: str = "") -> str:
        if name == "SENSORTOWER_API_KEY":
            return "  test-token  "
        return default

    monkeypatch.setattr(sensortower_client, "secret", fake_secret)

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = request.url
        return httpx.Response(200, json=[{"aid": 6749636760, "cc": "MX", "iu": 4159}])

    client = sensortower_client.SensorTowerClient()
    client._client = httpx.Client(transport=httpx.MockTransport(handler))

    result = client.get_sales_estimates(
        app_ids=["6749636760"],
        platform="ios",
        start_date="2025-12-01",
        end_date="2026-05-31",
        countries=["MX"],
        date_granularity="monthly",
    )

    assert result == [{"aid": 6749636760, "cc": "MX", "iu": 4159}]
    assert seen["url"].path == "/v1/ios/sales_report_estimates"
    assert dict(seen["url"].params) == {
        "date_granularity": "monthly",
        "start_date": "2025-12-01",
        "end_date": "2026-05-31",
        "app_ids": "6749636760",
        "countries": "MX",
        "auth_token": "test-token",
    }
