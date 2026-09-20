"""Tests for SQLite storage, deduplication, and last-call alerting."""

from datetime import datetime, timedelta
import tempfile
from pathlib import Path
from storage import Storage
from models import Hackathon, IST


def test_storage_dedup_and_marking():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_hackathons.db"
        storage = Storage(db_path)

        h1 = Hackathon(
            id="test_1",
            title="Test Hack 1",
            source="unstop",
            registration_deadline=datetime.now(IST) + timedelta(days=5),
        )

        assert not storage.is_already_sent(h1.id)
        assert not storage.should_send_last_call(h1.id, h1.registration_deadline)

        # Mark as sent
        storage.mark_sent(h1)
        assert storage.is_already_sent(h1.id)


def test_storage_last_call_alert():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_hackathons.db"
        storage = Storage(db_path)

        # Event with 24 hours left
        dl_closing_soon = datetime.now(IST) + timedelta(hours=24)
        h = Hackathon(
            id="test_closing",
            title="Closing Soon Hack",
            source="devfolio",
            registration_deadline=dl_closing_soon,
        )

        # Before initial send, should_send_last_call is False (it's a new item)
        assert not storage.should_send_last_call(h.id, h.registration_deadline)

        # First alert sent
        storage.mark_sent(h, is_last_call=False)
        assert storage.is_already_sent(h.id)

        # Now within 48h, should trigger last call exactly once
        assert storage.should_send_last_call(h.id, h.registration_deadline)

        # Mark last call sent
        storage.mark_sent(h, is_last_call=True)

        # Now should NOT trigger last call again
        assert not storage.should_send_last_call(h.id, h.registration_deadline)


def test_storage_enrichment_cache():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_hackathons.db"
        storage = Storage(db_path)

        item_id = "test_cache_1"
        assert storage.get_cached_enrichment(item_id) is None

        payload = {"accommodation": "Yes", "summary": "Cool AI hackathon"}
        storage.cache_enrichment(item_id, payload)

        cached = storage.get_cached_enrichment(item_id)
        assert cached is not None
        assert cached["accommodation"] == "Yes"
        assert cached["summary"] == "Cool AI hackathon"
