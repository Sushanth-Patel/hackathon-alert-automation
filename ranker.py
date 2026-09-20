"""Ranking and section filtering engine for Hackathon Alert Automation."""

from __future__ import annotations
import logging
import math
from typing import Any
from models import Hackathon

logger = logging.getLogger(__name__)


class Ranker:
    """Calculates hackathon ranking scores and partitions into sections."""

    def __init__(self, config: dict[str, Any]):
        self.weights = config.get("weights", {})
        self.hyderabad_keywords = [
            kw.lower() for kw in config.get("hyderabad_keywords", [])
        ]
        self.section_cfg = config.get("sections", {})
        self.sec_a_cap = self.section_cfg.get("section_a", {}).get("cap", 10)
        self.sec_b_cap = self.section_cfg.get("section_b", {}).get("cap", 5)
        self.sec_b_min_score = float(self.section_cfg.get("section_b", {}).get("min_score", 110.0))
        self.sort_within_section = self.section_cfg.get("sort_within_section", "score")
        
        filtering_cfg = config.get("filtering", {})
        self.min_hours_left = float(filtering_cfg.get("min_hours_left", 2.0))
        self.recruitment_keywords = [
            kw.lower() for kw in filtering_cfg.get("recruitment_exclusion_keywords", [])
        ]

    def is_recruitment_or_contest(self, h: Hackathon) -> bool:
        """Filter out pure recruitment assessments/coding challenges unless it's a real hackathon offering internships/PPO."""
        text = f"{h.title} {h.registration_url} {h.summary}".lower()
        for kw in self.recruitment_keywords:
            if kw in text:
                perks_str = " ".join(h.perks).lower()
                has_career = "internship" in perks_str or "ppo" in perks_str
                is_hack = "hackathon" in h.title.lower() or "hack" in h.title.lower()
                if not (is_hack and has_career):
                    return True
        return False

    def is_allowed_in_section_b(self, h: Hackathon) -> bool:
        """Section B allows online events, or offline/hybrid events located in Telangana. Excludes offline elsewhere."""
        mode = h.mode.lower()
        if mode == "online":
            return True
        loc_text = f"{h.city} {h.venue}".lower()
        return self.is_hyderabad(h) or "telangana" in loc_text

    def calculate_score(self, h: Hackathon) -> float:
        """Compute the weighted score for a hackathon."""
        score = 0.0

        # 1. B.Tech eligibility (must-have filter / separator)
        # Flagship events with reputed organizers or high prize pools (>= 100k INR) are premium for B.Tech
        if h.b_tech_eligible:
            if h.b_tech_specific or h.organizer_reputation_flag or h.prize_pool_inr >= 100000:
                score += self.weights.get("b_tech_eligible", 100.0)
            else:
                score += self.weights.get("open_to_all_eligible", 50.0)
        else:
            score -= 500.0  # Ineligible events rank strictly below all eligible ones

        # 2. Final-year friendly bonus
        if h.final_year_friendly:
            score += self.weights.get("final_year_friendly", 20.0)

        # 3. Free entry fee
        if "free" in h.entry_fee.lower() or h.entry_fee == "0":
            score += self.weights.get("free_entry", 15.0)

        # 4. Career opportunities (Internship / PPO)
        perks_str = " ".join(h.perks).lower()
        if "internship" in perks_str or "ppo" in perks_str or "pre-placement" in perks_str:
            score += self.weights.get("internship_or_ppo", 25.0)

        # 5. Reputed organizer
        if h.organizer_reputation_flag:
            score += self.weights.get("reputed_organizer", 20.0)

        # 6. Prize pool (normalized 0 to prize_pool_weight)
        max_prize_weight = self.weights.get("prize_pool_weight", 15.0)
        if h.prize_pool_inr > 0:
            norm = min(1.0, math.log10(h.prize_pool_inr + 1) / 6.0)
            score += norm * max_prize_weight

        # 7. Deadline urgency (bonus if <= 3 days left)
        if h.days_left is not None and 0 < h.days_left <= 3:
            score += self.weights.get("urgency_bonus", 10.0)

        # 8. Accommodation provided
        if h.accommodation.lower() == "yes":
            score += self.weights.get("accommodation", 15.0)

        h.score = round(score, 2)
        return h.score

    def is_hyderabad(self, h: Hackathon) -> bool:
        """Check if hackathon location is in Hyderabad/Telangana."""
        text = f"{h.city} {h.venue}".lower()
        return any(kw in text for kw in self.hyderabad_keywords)

    def is_india_based(self, h: Hackathon) -> bool:
        """Check if hackathon is India-based (Unstop, Devfolio, HackerEarth, or Indian venue)."""
        if h.source.lower() in ["unstop", "devfolio", "hackerearth"]:
            return True
        loc_text = f"{h.city} {h.venue}".lower()
        return "india" in loc_text or ", in" in loc_text

    @staticmethod
    def _sort_key(h: Hackathon):
        """Sort key: higher score first, events with deadlines before events without deadlines, then urgency."""
        has_dl = 1 if h.has_deadline else 0
        days = h.days_left if h.days_left is not None else 99999
        return (h.score, has_dl, -days)

    def rank_and_partition(
        self, hackathons: list[Hackathon]
    ) -> tuple[list[Hackathon], list[Hackathon]]:
        """Filter out expired events, score all, and partition into Section A and Section B."""
        # 1. Filter out expired hackathons, recruitment tests, and events with < min_hours_left
        active: list[Hackathon] = []
        for h in hackathons:
            if h.is_expired():
                logger.debug("Filtered out expired hackathon: %s", h.title)
                continue

            if h.has_deadline:
                hrs = h.hours_left()
                if hrs is not None and hrs < self.min_hours_left:
                    logger.debug("Filtered out event with < %.1fh left: %s", self.min_hours_left, h.title)
                    continue

            if self.is_recruitment_or_contest(h):
                logger.info("Filtered out non-hackathon recruitment/contest: %s", h.title)
                continue

            if "not open to india" in h.eligibility.lower() or not h.b_tech_eligible:
                logger.info("Filtered out hackathon not open to Indian students: %s", h.title)
                continue

            self.calculate_score(h)
            active.append(h)

        # 2. Section A: Hyderabad offline / hybrid events
        section_a_candidates = [
            h for h in active
            if self.is_hyderabad(h) and h.mode.lower() in ["offline", "hybrid"]
        ]
        # Sort descending by score, events with deadlines first
        section_a_candidates.sort(key=self._sort_key, reverse=True)
        section_a = section_a_candidates[: self.sec_a_cap]
        sec_a_ids = {h.id for h in section_a}

        # 3. Section B: High-Popularity Picks
        # Exclude items in Section A, exclude distant offline events, require score >= min_score
        remaining = [
            h for h in active
            if h.id not in sec_a_ids
            and self.is_allowed_in_section_b(h)
            and h.score >= self.sec_b_min_score
        ]
        # Sort candidates in score order
        remaining.sort(key=self._sort_key, reverse=True)

        max_india_slots = self.section_cfg.get("section_b", {}).get("reserve_india_slots", 2)
        india_pool = [h for h in remaining if self.is_india_based(h)]
        global_pool = [h for h in remaining if not self.is_india_based(h)]

        # 1. Allocate up to max_india_slots for top India events meeting min_score
        india_picks = india_pool[:max_india_slots]

        # 2. Allocate remaining slots for top global flagship events
        needed_global = max(0, self.sec_b_cap - len(india_picks))
        global_picks = global_pool[:needed_global]

        section_b_picks = india_picks + global_picks

        # 3. If global picks are fewer than needed, fill remaining slots from India pool up to cap
        if len(section_b_picks) < self.sec_b_cap:
            picked_ids = {h.id for h in section_b_picks}
            for h in india_pool:
                if h.id not in picked_ids:
                    section_b_picks.append(h)
                    if len(section_b_picks) >= self.sec_b_cap:
                        break

        # Apply final within-section sort (closing <= 24h ALWAYS first, then configured order)
        section_a = self.sort_section_events(section_a)
        section_b_picks = self.sort_section_events(section_b_picks)
        return section_a, section_b_picks

    def sort_section_events(self, events: list[Hackathon]) -> list[Hackathon]:
        """Sort events within a section:
        1. Events closing within 24 hours ALWAYS come first (urgency tier).
        2. Within each tier, sort by sort_within_section ('score' or 'deadline_first').
        """
        def _tier_key(h: Hackathon):
            hrs = h.hours_left()
            is_closing_24h = h.has_deadline and hrs is not None and 0 <= hrs <= 24.0
            tier = 0 if is_closing_24h else 1

            has_dl = 1 if h.has_deadline else 0
            days = h.days_left if h.days_left is not None else 99999

            if self.sort_within_section == "deadline_first":
                return (tier, -has_dl, days, -h.score)
            else:
                return (tier, -h.score, -has_dl, days)

        return sorted(events, key=_tier_key)
