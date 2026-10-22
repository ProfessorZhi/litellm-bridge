from datetime import datetime

import pytest

import litellm
from litellm.proxy.db.db_spend_update_writer import DBSpendUpdateWriter


@pytest.fixture(autouse=True)
def _restore_timezone():
    """`litellm.timezone` is a module-level global set from litellm_settings."""
    previous = getattr(litellm, "timezone", None)
    yield
    litellm.timezone = previous


@pytest.mark.parametrize(
    "timezone_name,start_time,expected",
    [
        # Default (unset) and explicit UTC keep the historical UTC-day behaviour.
        (None, datetime(2026, 9, 14, 18, 0), "2026-09-14"),
        ("UTC", datetime(2026, 9, 14, 18, 0), "2026-09-14"),
        # Naive timestamps are UTC: 16:00 UTC is exactly midnight in Asia/Shanghai.
        ("Asia/Shanghai", datetime(2026, 9, 14, 15, 0), "2026-09-14"),
        ("Asia/Shanghai", datetime(2026, 9, 14, 16, 0), "2026-09-15"),
        ("Asia/Shanghai", datetime(2026, 9, 14, 18, 0), "2026-09-15"),
        # The payload may carry either a naive or a tz-aware ISO string.
        ("Asia/Shanghai", "2026-09-14T18:00:00", "2026-09-15"),
        ("Asia/Shanghai", "2026-09-14T18:00:00+00:00", "2026-09-15"),
        ("Asia/Shanghai", "2026-09-14T02:00:00Z", "2026-09-14"),
        # An unusable timezone falls back to UTC rather than raising.
        ("Bogus/Zone", datetime(2026, 9, 14, 18, 0), "2026-09-14"),
        # An unparseable timestamp keeps the legacy string-splitting behaviour.
        ("Asia/Shanghai", "not-a-timestamp", "not-a-timestamp"),
    ],
)
def test_get_daily_spend_date(timezone_name, start_time, expected):
    litellm.timezone = timezone_name
    assert DBSpendUpdateWriter._get_daily_spend_date(start_time) == expected
