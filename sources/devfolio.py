"""Devfolio source fetcher and parser."""

from __future__ import annotations
import logging
from typing import Any, Optional
from dateutil import parser as date_parser
from models import RawHackathon, IST
from sources.base import BaseSource

logger = logging.getLogger(__name__)

DEVFOLIO_API_URL = "https://api.devfolio.co/api/hackathons?filter=application_open&page=1&per_page=30"


class DevfolioSource(BaseSource):
    """Fetcher for Devfolio hackathons."""

    def __init__(self, **kwargs: Any):
        super().__init__(name="devfolio", **kwargs)

    def fetch(self) -> list[RawHackathon]:
        resp = self.get(DEVFOLIO_API_URL)
        data = resp.json()
        items = data.get("result", [])
        results: list[RawHackathon] = []
        for item in items:
            parsed = self.parse_item(item)
            if parsed:
                results.append(parsed)
        return results

    def parse_item(self, item: dict[str, Any]) -> Optional[RawHackathon]:
        uuid = item.get("uuid")
        name = (item.get("name") or "").strip()
        if not uuid or not name:
            return None

        slug = item.get("slug") or ""
        hack_setting = item.get("hackathon_setting") or {}
        site_url = hack_setting.get("site") if isinstance(hack_setting, dict) else None
        reg_url = site_url or f"https://{slug}.devfolio.co" if slug else f"https://devfolio.co/hackathons/{uuid}"

        # Location & Mode
        is_online = item.get("is_online", False)
        city = item.get("city") or ("Online" if is_online else "Not specified")
        venue = item.get("location") or city
        mode = "online" if is_online else "offline"

        # Deadlines & Dates
        reg_ends_at = hack_setting.get("reg_ends_at") if isinstance(hack_setting, dict) else None
        starts_at = item.get("starts_at")
        ends_at = item.get("ends_at")

        registration_deadline = None
        if reg_ends_at:
            try:
                registration_deadline = date_parser.parse(reg_ends_at)
                if registration_deadline.tzinfo is None:
                    registration_deadline = registration_deadline.replace(tzinfo=IST)
                else:
                    registration_deadline = registration_deadline.astimezone(IST)
            except Exception as e:
                logger.debug("Failed parsing Devfolio deadline: %s", e)

        # Fallback deadline to starts_at if reg_ends_at is missing
        if not registration_deadline and starts_at:
            try:
                registration_deadline = date_parser.parse(starts_at)
                if registration_deadline.tzinfo is None:
                    registration_deadline = registration_deadline.replace(tzinfo=IST)
                else:
                    registration_deadline = registration_deadline.astimezone(IST)
            except Exception:
                pass

        event_start = None
        if starts_at:
            try:
                event_start = date_parser.parse(starts_at).astimezone(IST)
            except Exception:
                pass

        event_end = None
        if ends_at:
            try:
                event_end = date_parser.parse(ends_at).astimezone(IST)
            except Exception:
                pass

        return RawHackathon(
            source="devfolio",
            source_id=str(uuid),
            title=name,
            registration_url=reg_url,
            raw_payload=item,
            organizer="Devfolio Community",
            venue=venue,
            city=city,
            mode=mode,
            event_start=event_start,
            event_end=event_end,
            registration_deadline=registration_deadline,
            entry_fee="Free",
            participation_type="Team or Solo",
            prize_pool="Not specified",
            prize_pool_inr=0.0,
            raw_description=f"Devfolio hackathon: {name} in {venue}",
            raw_eligibility="Open to students & developers",
        )
