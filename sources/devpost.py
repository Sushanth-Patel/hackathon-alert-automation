"""Devpost source fetcher and parser."""

from __future__ import annotations
import logging
import re
from typing import Any, Optional
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from models import RawHackathon, IST
from sources.base import BaseSource

logger = logging.getLogger(__name__)

DEVPOST_API_URL = "https://devpost.com/api/hackathons?challenge_type[]=online&challenge_type[]=in-person&status[]=upcoming&status[]=open"


class DevpostSource(BaseSource):
    """Fetcher for Devpost hackathons."""

    def __init__(self, **kwargs: Any):
        super().__init__(name="devpost", **kwargs)

    def fetch(self) -> list[RawHackathon]:
        resp = self.get(DEVPOST_API_URL)
        data = resp.json()
        items = data.get("hackathons", [])
        results: list[RawHackathon] = []
        for item in items:
            parsed = self.parse_item(item)
            if parsed:
                results.append(parsed)
        return results

    def parse_item(self, item: dict[str, Any]) -> Optional[RawHackathon]:
        item_id = str(item.get("id", ""))
        title = (item.get("title") or "").strip()
        if not item_id or not title:
            return None

        url = item.get("url") or f"https://devpost.com/software/{item_id}"
        organizer = item.get("organization_name") or "Devpost Community"

        # Location & Mode
        disp_loc = item.get("displayed_location") or {}
        location_str = disp_loc.get("location") if isinstance(disp_loc, dict) else "Online"
        location_str = location_str or "Online"

        if location_str.lower() == "online":
            mode = "online"
            city = "Online"
            venue = "Online"
        else:
            mode = "offline"
            city = location_str.split(",")[0].strip()
            venue = location_str

        # Prize
        prize_raw = item.get("prize_amount") or ""
        prize_clean = "Not specified"
        prize_inr = 0.0
        if prize_raw:
            clean_text = BeautifulSoup(prize_raw, "html.parser").get_text(strip=True)
            if clean_text:
                prize_clean = clean_text
                # Try to parse USD / numbers
                num_match = re.search(r"[\d,]+", clean_text)
                if num_match:
                    num = float(num_match.group(0).replace(",", ""))
                    if "$" in clean_text:
                        prize_inr = num * 85.0  # Approx USD to INR
                    else:
                        prize_inr = num

        # Dates / Deadline
        sub_dates = item.get("submission_period_dates") or ""
        registration_deadline = None
        if sub_dates and "-" in sub_dates:
            end_part = sub_dates.split("-")[-1].strip()
            try:
                registration_deadline = date_parser.parse(end_part)
                if registration_deadline.tzinfo is None:
                    registration_deadline = registration_deadline.replace(tzinfo=IST)
                else:
                    registration_deadline = registration_deadline.astimezone(IST)
            except Exception as e:
                logger.debug("Failed to parse Devpost deadline from '%s': %s", end_part, e)

        # Determine India eligibility
        invite_only = bool(item.get("invite_only", False))
        invite_desc = item.get("eligibility_requirement_invite_only_description") or ""
        text_to_check = f"{title} {location_str} {invite_desc}".lower()

        is_non_india_offline = (mode == "offline" and "india" not in location_str.lower())
        is_restricted_region = bool(
            re.search(
                r"\b(us only|usa only|united states only|north america only|canada only|europe only|residents of the 50 united states)\b",
                text_to_check,
            )
        )
        if is_non_india_offline or invite_only or is_restricted_region:
            raw_eligibility = "Not open to India"
        else:
            raw_eligibility = "Open to global participants (Open to India)"

        return RawHackathon(
            source="devpost",
            source_id=item_id,
            title=title,
            registration_url=url,
            raw_payload=item,
            organizer=organizer,
            venue=venue,
            city=city,
            mode=mode,
            event_start=None,
            event_end=None,
            registration_deadline=registration_deadline,
            entry_fee="Free",
            participation_type="Team or Solo",
            prize_pool=prize_clean,
            prize_pool_inr=prize_inr,
            raw_description=f"{title} hosted by {organizer}. Submission period: {sub_dates}",
            raw_eligibility=raw_eligibility,
        )
