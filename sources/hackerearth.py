"""HackerEarth source fetcher and parser."""

from __future__ import annotations
import logging
import re
from typing import Any, Optional
from dateutil import parser as date_parser
from models import RawHackathon, IST
from sources.base import BaseSource

logger = logging.getLogger(__name__)

HACKEREARTH_API_URL = "https://www.hackerearth.com/chrome-extension/events/"


class HackerEarthSource(BaseSource):
    """Fetcher for HackerEarth hackathons and coding challenges."""

    def __init__(self, **kwargs: Any):
        super().__init__(name="hackerearth", **kwargs)

    def fetch(self) -> list[RawHackathon]:
        resp = self.get(HACKEREARTH_API_URL)
        data = resp.json()
        items = data.get("response", [])
        results: list[RawHackathon] = []
        for item in items:
            parsed = self.parse_item(item)
            if parsed:
                results.append(parsed)
        return results

    def parse_item(self, item: dict[str, Any]) -> Optional[RawHackathon]:
        title = (item.get("title") or "").strip()
        url = item.get("url") or ""
        if not title or not url:
            return None

        # Extract slug from url
        slug_match = re.search(r"/challenges/([^/]+)/([^/]+)/?", url)
        if slug_match:
            source_id = slug_match.group(2)
        else:
            source_id = re.sub(r"[^a-zA-Z0-9_-]", "_", title.lower())

        # Dates & Deadline
        end_tz = item.get("end_tz")
        registration_deadline = None
        if end_tz:
            try:
                registration_deadline = date_parser.parse(end_tz)
                if registration_deadline.tzinfo is None:
                    registration_deadline = registration_deadline.replace(tzinfo=IST)
                else:
                    registration_deadline = registration_deadline.astimezone(IST)
            except Exception as e:
                logger.debug("Failed parsing HackerEarth deadline: %s", e)

        event_start = None
        start_tz = item.get("start_tz")
        if start_tz:
            try:
                event_start = date_parser.parse(start_tz).astimezone(IST)
            except Exception:
                pass

        description = item.get("description") or ""

        return RawHackathon(
            source="hackerearth",
            source_id=source_id,
            title=title,
            registration_url=url,
            raw_payload=item,
            organizer="HackerEarth Community",
            venue="Online",
            city="Online",
            mode="online",
            event_start=event_start,
            event_end=registration_deadline,
            registration_deadline=registration_deadline,
            entry_fee="Free",
            participation_type="Solo or Team",
            prize_pool="Not specified",
            prize_pool_inr=0.0,
            raw_description=description,
            raw_eligibility="Open to students and developers",
        )
