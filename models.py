"""Data models for Hackathon Alert Automation.
Normalized schema and raw intermediate representations.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Any, Optional
import math

IST = ZoneInfo("Asia/Kolkata")


@dataclass
class RawHackathon:
    """Raw hackathon data extracted directly from a source."""
    source: str
    source_id: str
    title: str
    registration_url: str
    raw_payload: dict[str, Any] = field(default_factory=dict)
    
    # Pre-extracted fields from source (if available)
    organizer: str = "Not specified"
    venue: str = "Not specified"
    city: str = "Not specified"
    mode: str = "offline"  # offline, hybrid, online
    event_start: Optional[datetime] = None
    event_end: Optional[datetime] = None
    registration_deadline: Optional[datetime] = None
    entry_fee: str = "Free"
    participation_type: str = "Team"
    min_team_size: Optional[int] = None
    max_team_size: Optional[int] = None
    prize_pool: str = "Not specified"
    prize_pool_inr: float = 0.0
    raw_description: str = ""
    raw_eligibility: str = ""


@dataclass
class Hackathon:
    """Single normalized hackathon representation across all platforms."""
    id: str                               # e.g. "unstop_1737808"
    title: str
    source: str                           # "unstop", "devfolio", "devpost", "mlh", "hackerearth"
    organizer: str = "Not specified"
    venue: str = "Not specified"
    city: str = "Not specified"
    mode: str = "offline"                 # "offline", "hybrid", "online"
    event_start: Optional[datetime] = None
    event_end: Optional[datetime] = None
    registration_deadline: Optional[datetime] = None
    entry_fee: str = "Free"               # "Free" or "₹X"
    participation_type: str = "Team"      # e.g. "Team (1-5 members)", "Solo only"
    accommodation: str = "Not specified"  # "Yes", "No", "Not specified"
    food_or_travel_support: str = "Not specified"
    prize_pool: str = "Not specified"
    prize_pool_inr: float = 0.0
    perks: list[str] = field(default_factory=list)
    eligibility: str = "Not specified"
    b_tech_eligible: bool = True
    b_tech_specific: bool = False         # True if explicitly targeted at B.Tech/Engineering
    final_year_friendly: bool = True
    organizer_reputation_flag: bool = False
    summary: str = "Not specified"
    registration_url: str = ""
    
    # Extra metadata
    is_closing_soon: bool = False         # <= 48h left
    score: float = 0.0                    # Ranking score
    raw_ref: Optional[Any] = None         # Reference to original RawHackathon

    def __post_init__(self):
        # Convert all datetimes strictly to Asia/Kolkata
        for dt_field in ["event_start", "event_end", "registration_deadline"]:
            dt_val = getattr(self, dt_field)
            if dt_val is not None:
                if dt_val.tzinfo is None:
                    setattr(self, dt_field, dt_val.replace(tzinfo=IST))
                else:
                    setattr(self, dt_field, dt_val.astimezone(IST))

        # Fallbacks for empty / None strings
        for field_name in [
            "organizer", "venue", "city", "mode", "entry_fee",
            "participation_type", "accommodation", "food_or_travel_support",
            "prize_pool", "eligibility", "summary", "registration_url"
        ]:
            val = getattr(self, field_name)
            if val is None or (isinstance(val, str) and not val.strip()):
                setattr(self, field_name, "Not specified")

        # Compute closing soon (only if deadline exists)
        if self.registration_deadline:
            hrs = self.hours_left()
            self.is_closing_soon = hrs is not None and 0 <= hrs <= 48

    @property
    def has_deadline(self) -> bool:
        """True if a registration deadline is set."""
        return self.registration_deadline is not None

    @property
    def days_left(self) -> Optional[int]:
        """Computed remaining whole days until registration deadline in IST, or None if no deadline."""
        if not self.registration_deadline:
            return None
        now = datetime.now(IST)
        delta = self.registration_deadline - now
        total_seconds = delta.total_seconds()
        if total_seconds <= 0:
            return 0
        return max(0, math.ceil(total_seconds / 86400))

    def hours_left(self) -> Optional[float]:
        """Remaining hours until deadline in IST, or None if no deadline is specified."""
        if not self.registration_deadline:
            return None
        now = datetime.now(IST)
        delta = self.registration_deadline - now
        return delta.total_seconds() / 3600.0

    def is_expired(self) -> bool:
        """Checks if registration deadline has passed in IST. Events with no deadline are never expired."""
        if not self.registration_deadline:
            return False
        hrs = self.hours_left()
        return hrs is not None and hrs <= 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "id": self.id,
            "title": self.title,
            "source": self.source,
            "organizer": self.organizer,
            "venue": self.venue,
            "city": self.city,
            "mode": self.mode,
            "event_start": self.event_start.isoformat() if self.event_start else None,
            "event_end": self.event_end.isoformat() if self.event_end else None,
            "registration_deadline": self.registration_deadline.isoformat() if self.registration_deadline else None,
            "days_left": self.days_left,
            "entry_fee": self.entry_fee,
            "participation_type": self.participation_type,
            "accommodation": self.accommodation,
            "food_or_travel_support": self.food_or_travel_support,
            "prize_pool": self.prize_pool,
            "prize_pool_inr": self.prize_pool_inr,
            "perks": self.perks,
            "eligibility": self.eligibility,
            "b_tech_eligible": self.b_tech_eligible,
            "b_tech_specific": self.b_tech_specific,
            "final_year_friendly": self.final_year_friendly,
            "organizer_reputation_flag": self.organizer_reputation_flag,
            "summary": self.summary,
            "registration_url": self.registration_url,
            "is_closing_soon": self.is_closing_soon,
            "score": self.score,
        }
