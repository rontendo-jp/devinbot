from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.api.metrics import routes


SAMPLE = {
    "total_acus": 3.5,
    "consumption_by_date": [
        {"date": 1758528000, "acus": 1.25, "acus_by_product": {"devin": 1.0, "cascade": 0.25, "terminal": 0}},
        {"date": 1758614400, "acus": 2.25, "acus_by_product": {"devin": 2.0, "cascade": 0.0, "terminal": 0.25}},
    ],
}


def test_summarize_consumption_totals_and_breakdown():
    result = routes.summarize_consumption(SAMPLE)
    assert result["total_acus"] == 3.5
    assert result["acus_by_product"] == {"devin": 3.0, "cascade": 0.25, "terminal": 0.25}
    assert result["data_points"] == 2
    assert result["granularity"] == "daily"
    assert [d["acus"] for d in result["daily"]] == [1.25, 2.25]


def test_summarize_consumption_falls_back_to_summing_days():
    data = {"consumption_by_date": [{"date": 1, "acus": 0.5}, {"date": 2, "acus": 0.75}]}
    assert routes.summarize_consumption(data)["total_acus"] == 1.25


@pytest.mark.asyncio
async def test_get_cost_consumption_passes_time_range(monkeypatch):
    client = MagicMock()
    client.get_daily_consumption = AsyncMock(return_value=SAMPLE)
    monkeypatch.setattr(routes, "devin_client", client)

    start = datetime(2026, 9, 15, 3, 0, 0)
    end = datetime(2026, 9, 22, 3, 0, 0)
    result = await routes.get_cost_consumption(start, end)

    client.get_daily_consumption.assert_awaited_once_with(
        time_after=int(start.replace(tzinfo=timezone.utc).timestamp()),
        time_before=int(end.replace(tzinfo=timezone.utc).timestamp()),
    )
    assert result["total_acus"] == 3.5
    assert "error" not in result


@pytest.mark.asyncio
async def test_get_cost_consumption_reports_forbidden(monkeypatch):
    request = httpx.Request("GET", "https://api.devin.ai/v3/organizations/org/consumption/daily")
    response = httpx.Response(403, request=request, text='{"detail":"forbidden"}')
    client = MagicMock()
    client.get_daily_consumption = AsyncMock(side_effect=httpx.HTTPStatusError("403", request=request, response=response))
    monkeypatch.setattr(routes, "devin_client", client)

    result = await routes.get_cost_consumption(datetime(2026, 9, 21), datetime(2026, 9, 22))

    assert result["total_acus"] is None
    assert "ViewOrgConsumption" in result["error"]


def test_resolve_time_period_preset_ends_at_now():
    now = datetime(2026, 9, 23, 6, 0, 0)
    start, end = routes.resolve_time_period("7d", None, None, now=now)
    assert end == now
    assert (end - start).days == 7


def test_resolve_time_period_custom_defaults_to_last_hour():
    now = datetime(2026, 9, 23, 6, 0, 0)
    start, end = routes.resolve_time_period("custom", None, None, now=now)
    assert end == now
    assert start == datetime(2026, 9, 23, 5, 0, 0)


def test_resolve_time_period_custom_normalizes_to_utc():
    from datetime import timedelta
    tz = timezone(timedelta(hours=9))
    start, end = routes.resolve_time_period(
        "custom",
        datetime(2026, 9, 23, 9, 0, tzinfo=tz),
        datetime(2026, 9, 23, 12, 0, tzinfo=tz),
    )
    assert start == datetime(2026, 9, 23, 0, 0)
    assert end == datetime(2026, 9, 23, 3, 0)


def test_resolve_time_period_custom_rejects_inverted_range():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        routes.resolve_time_period("custom", datetime(2026, 9, 23, 5), datetime(2026, 9, 23, 4))
    assert exc.value.status_code == 422
