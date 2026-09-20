"""Unit tests for UTC to Asia/Kolkata timezone conversion and deadline calculations."""

from datetime import datetime, timezone, timedelta
from dateutil import parser as date_parser
from zoneinfo import ZoneInfo
from models import Hackathon, IST


def test_utc_timestamp_near_midnight_ist():
    """Verify that a UTC timestamp near midnight converts to the exact IST hour and date."""
    # 18:29:00 UTC = 23:59:00 IST (same date)
    utc_dt = datetime(2026, 9, 20, 18, 29, 0, tzinfo=timezone.utc)
    h = Hackathon(
        id="tz_test_1",
        title="Midnight UTC Test",
        source="devfolio",
        registration_deadline=utc_dt,
    )

    # Must be converted to IST in Hackathon post-init
    assert h.registration_deadline.tzinfo == IST
    assert h.registration_deadline.year == 2026
    assert h.registration_deadline.month == 9
    assert h.registration_deadline.day == 20
    assert h.registration_deadline.hour == 23
    assert h.registration_deadline.minute == 59

    # Now test an event 1 hour later: 19:30:00 UTC = 01:00:00 IST next day (Sep 21)
    utc_dt_next_day = datetime(2026, 9, 20, 19, 30, 0, tzinfo=timezone.utc)
    h_next = Hackathon(
        id="tz_test_2",
        title="Next Day UTC Test",
        source="devfolio",
        registration_deadline=utc_dt_next_day,
    )
    assert h_next.registration_deadline.tzinfo == IST
    assert h_next.registration_deadline.day == 21
    assert h_next.registration_deadline.hour == 1
    assert h_next.registration_deadline.minute == 0


def test_event_with_no_deadline():
    """Verify that events without a deadline are handled safely without errors."""
    h_no_dl = Hackathon(
        id="no_dl_test",
        title="Rolling Admissions Hackathon",
        source="devpost",
        registration_deadline=None,
    )

    assert not h_no_dl.has_deadline
    assert h_no_dl.days_left is None
    assert h_no_dl.hours_left() is None
    assert not h_no_dl.is_expired()
    assert not h_no_dl.is_closing_soon
