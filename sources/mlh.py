"""MLH (Major League Hacking) source fetcher and parser."""

from __future__ import annotations
import logging
import re
from typing import Any, Optional
from datetime import datetime
from bs4 import BeautifulSoup, Tag
from dateutil import parser as date_parser
from models import RawHackathon, IST
from sources.base import BaseSource

logger = logging.getLogger(__name__)

MLH_SEASONS_URL = "https://mlh.io/seasons/2026/events"


class MLHSource(BaseSource):
    """Fetcher for Major League Hacking events."""

    def __init__(self, **kwargs: Any):
        super().__init__(name="mlh", **kwargs)

    def fetch(self) -> list[RawHackathon]:
        resp = self.get(MLH_SEASONS_URL)
        soup = BeautifulSoup(resp.text, "html.parser")
        event_cards = soup.find_all(lambda el: el.name == "a" and "schema.org/Event" in el.get("itemtype", ""))
        
        results: list[RawHackathon] = []
        for card in event_cards:
            parsed = self.parse_card(card)
            if parsed:
                results.append(parsed)
        return results

    def parse_card(self, card: Tag) -> Optional[RawHackathon]:
        # Title
        h4 = card.find("h4")
        title = h4.get_text(strip=True) if h4 else ""
        if not title:
            return None

        # URL
        url_meta = card.find("meta", attrs={"itemprop": "url"})
        url = url_meta.get("content") if url_meta else card.get("href", "")
        if not url:
            url = card.get("href", "")

        # ID from url or title
        source_id = re.sub(r"[^a-zA-Z0-9_-]", "_", title.lower())
        if url:
            m = re.search(r"https?://(?:www\.)?([^/]+)", url)
            if m:
                source_id = re.sub(r"[^a-zA-Z0-9_-]", "_", m.group(1).lower())

        # Dates
        start_meta = card.find("meta", attrs={"itemprop": "startDate"})
        end_meta = card.find("meta", attrs={"itemprop": "endDate"})
        
        event_start = None
        event_end = None
        if start_meta and start_meta.get("content"):
            try:
                event_start = date_parser.parse(start_meta["content"]).astimezone(IST)
            except Exception:
                pass

        if end_meta and end_meta.get("content"):
            try:
                event_end = date_parser.parse(end_meta["content"]).astimezone(IST)
            except Exception:
                pass

        # For MLH hackathons, registration usually closes at or right before event_start
        registration_deadline = event_start or event_end

        # Mode
        mode_meta = card.find("meta", attrs={"itemprop": "eventAttendanceMode"})
        mode = "offline"
        if mode_meta and mode_meta.get("content"):
            att_mode = mode_meta["content"].lower()
            if "online" in att_mode:
                mode = "online"
            elif "mixed" in att_mode or "hybrid" in att_mode:
                mode = "hybrid"

        # Location
        city_meta = card.find("meta", attrs={"itemprop": "addressLocality"})
        region_meta = card.find("meta", attrs={"itemprop": "addressRegion"})
        country_meta = card.find("meta", attrs={"itemprop": "addressCountry"})

        city = city_meta.get("content", "").strip() if city_meta else ""
        region = region_meta.get("content", "").strip() if region_meta else ""
        country = country_meta.get("content", "").strip() if country_meta else ""

        loc_parts = [p for p in [city, region, country] if p]
        venue = ", ".join(loc_parts) if loc_parts else ("Online" if mode == "online" else "Not specified")
        if not city:
            city = "Online" if mode == "online" else "Not specified"

        return RawHackathon(
            source="mlh",
            source_id=source_id,
            title=title,
            registration_url=url,
            raw_payload={"title": title, "url": url},
            organizer="Major League Hacking (MLH)",
            venue=venue,
            city=city,
            mode=mode,
            event_start=event_start,
            event_end=event_end,
            registration_deadline=registration_deadline,
            entry_fee="Free",
            participation_type="Team or Solo",
            prize_pool="Swag & Sponsor Prizes",
            prize_pool_inr=0.0,
            raw_description=f"MLH Member Hackathon: {title} taking place at {venue}.",
            raw_eligibility="Open to all university students (high schoolers welcome at select events)",
        )
