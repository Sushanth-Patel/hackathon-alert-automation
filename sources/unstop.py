"""Unstop hackathon source fetcher and parser."""

from __future__ import annotations
import logging
import re
from typing import Any, Optional
from datetime import datetime
from dateutil import parser as date_parser
from models import RawHackathon, IST
from enrich import format_inr_amount
from sources.base import BaseSource

logger = logging.getLogger(__name__)

UNSTOP_API_URL = "https://unstop.com/api/public/opportunity/search-result?opportunity=hackathons&per_page=100&oppstatus=open"


class UnstopSource(BaseSource):
    """Fetcher for Unstop hackathons."""

    def __init__(self, **kwargs: Any):
        super().__init__(name="unstop", **kwargs)

    def fetch(self) -> list[RawHackathon]:
        resp = self.get(UNSTOP_API_URL)
        data = resp.json()
        items = []
        if isinstance(data, dict) and "data" in data:
            nested = data["data"]
            if isinstance(nested, dict) and "data" in nested:
                items = nested["data"]
            elif isinstance(nested, list):
                items = nested

        results: list[RawHackathon] = []
        for item in items:
            parsed = self.parse_item(item)
            if parsed:
                results.append(parsed)
        return results

    def parse_item(self, item: dict[str, Any]) -> Optional[RawHackathon]:
        """Parse raw Unstop item dictionary into RawHackathon."""
        item_id = str(item.get("id", ""))
        title = item.get("title", "").strip()
        if not item_id or not title:
            return None

        # URL
        url = item.get("seo_url") or ""
        if not url and item.get("public_url"):
            url = f"https://unstop.com/{item.get('public_url')}"
        if not url:
            url = f"https://unstop.com/hackathons/{item_id}"

        # Organizer
        org = item.get("organisation") or {}
        organizer = org.get("name", "Not specified") if isinstance(org, dict) else "Not specified"

        # Venue & City
        addr = item.get("address_with_country_logo") or {}
        city = "Not specified"
        venue = "Not specified"
        if isinstance(addr, dict):
            city = addr.get("city") or "Not specified"
            venue = addr.get("address") or city

        # Mode
        raw_mode = (item.get("region") or "").lower()
        if "online" in raw_mode:
            mode = "online"
        elif "hybrid" in raw_mode:
            mode = "hybrid"
        else:
            mode = "offline"

        # Deadlines
        reg_req = item.get("regnRequirements") or {}
        deadline_str = None
        if isinstance(reg_req, dict):
            deadline_str = reg_req.get("end_regn_dt")
        if not deadline_str:
            deadline_str = item.get("end_date")

        registration_deadline = None
        if deadline_str:
            try:
                registration_deadline = date_parser.parse(deadline_str)
                if registration_deadline.tzinfo is None:
                    registration_deadline = registration_deadline.replace(tzinfo=IST)
                else:
                    registration_deadline = registration_deadline.astimezone(IST)
            except Exception as e:
                logger.debug("Failed parsing deadline '%s': %s", deadline_str, e)

        # Event end date
        event_end = None
        end_str = item.get("end_date")
        if end_str:
            try:
                event_end = date_parser.parse(end_str)
                if event_end.tzinfo is None:
                    event_end = event_end.replace(tzinfo=IST)
                else:
                    event_end = event_end.astimezone(IST)
            except Exception:
                pass

        # Fee
        is_paid = item.get("isPaid", False)
        entry_fee = "Free"
        if is_paid:
            services = item.get("payment_services") or []
            if services and isinstance(services, list) and isinstance(services[0], dict):
                amount = services[0].get("amount")
                if amount:
                    entry_fee = format_inr_amount(amount) if isinstance(amount, (int, float)) else f"₹{amount}"
            if entry_fee == "Free":
                entry_fee = "Paid (fee applicable)"

        # Participation Type & Team Size
        min_team = 1
        max_team = 1
        if isinstance(reg_req, dict):
            min_team = reg_req.get("min_team_size", 1)
            max_team = reg_req.get("max_team_size", 1)

        if min_team == 1 and max_team == 1:
            part_type = "Solo only"
        elif min_team > 1:
            part_type = f"Team only ({min_team}–{max_team} members)"
        else:
            part_type = f"Team or Solo ({min_team}–{max_team} members)"

        # Prize Pool
        prize_pool = "Not specified"
        prize_inr = 0.0
        prizes = item.get("prizes") or []
        if prizes and isinstance(prizes, list):
            cash_sum = 0
            for p in prizes:
                if isinstance(p, dict):
                    cash_sum += p.get("cash") or 0
            if cash_sum > 0:
                prize_inr = float(cash_sum)
                prize_pool = format_inr_amount(cash_sum)

        # Raw eligibility string
        eligibility_list = []
        filters = item.get("filters") or []
        if isinstance(filters, list):
            for f in filters:
                if isinstance(f, dict) and f.get("name"):
                    eligibility_list.append(f.get("name"))
        if isinstance(reg_req, dict) and reg_req.get("eligibility"):
            eligibility_list.append(str(reg_req.get("eligibility")))
        raw_eligibility = " | ".join(eligibility_list)

        return RawHackathon(
            source="unstop",
            source_id=item_id,
            title=title,
            registration_url=url,
            raw_payload=item,
            organizer=organizer,
            venue=venue,
            city=city,
            mode=mode,
            event_start=None,
            event_end=event_end,
            registration_deadline=registration_deadline,
            entry_fee=entry_fee,
            participation_type=part_type,
            min_team_size=min_team,
            max_team_size=max_team,
            prize_pool=prize_pool,
            prize_pool_inr=prize_inr,
            raw_description=item.get("details", "") or "",
            raw_eligibility=raw_eligibility,
        )
