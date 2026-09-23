from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.api.metrics.routes import resolve_time_period


NOW = datetime(2026, 9, 23, 12, 0, 0)


def test_preset_range_used_when_no_custom_bounds():
    start, end, label = resolve_time_period("7d", None, None, now=NOW)
    assert (start, end, label) == (NOW - timedelta(days=7), NOW, "7d")


def test_custom_bounds_override_preset_and_normalize_to_utc():
    time_from = datetime(2026, 9, 23, 9, 0, tzinfo=timezone(timedelta(hours=9)))
    time_to = datetime(2026, 9, 23, 11, 0, tzinfo=timezone.utc)
    start, end, label = resolve_time_period("30d", time_from, time_to, now=NOW)
    assert start == datetime(2026, 9, 23, 0, 0)
    assert end == datetime(2026, 9, 23, 11, 0)
    assert label == "custom"


def test_missing_from_defaults_to_one_hour_before_to():
    start, end, _ = resolve_time_period("custom", None, NOW - timedelta(hours=2), now=NOW)
    assert end == NOW - timedelta(hours=2)
    assert start == end - timedelta(hours=1)


def test_missing_to_defaults_to_now():
    start, end, _ = resolve_time_period("custom", NOW - timedelta(days=1), None, now=NOW)
    assert (start, end) == (NOW - timedelta(days=1), NOW)


def test_from_after_to_is_rejected():
    with pytest.raises(HTTPException) as exc:
        resolve_time_period("custom", NOW, NOW - timedelta(minutes=1), now=NOW)
    assert exc.value.status_code == 422
