"""Gemini-based unstructured field extraction and enrichment with SQLite caching and regex fallback."""

from __future__ import annotations
import os
import json
import logging
import re
import time
from typing import Any, Optional
import requests
from bs4 import BeautifulSoup
from models import RawHackathon, Hackathon
from storage import Storage

logger = logging.getLogger(__name__)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
DEFAULT_GEMINI_MODEL = "gemini-flash-lite-latest"


def format_inr_amount(val: int | float) -> str:
    """Format an integer or float into Indian digit grouped INR string e.g. ₹2,00,000."""
    num = int(round(val))
    s = str(num)
    if len(s) <= 3:
        return f"₹{s}"
    last_three = s[-3:]
    remaining = s[:-3]
    parts = []
    while len(remaining) > 2:
        parts.insert(0, remaining[-2:])
        remaining = remaining[:-2]
    if remaining:
        parts.insert(0, remaining)
    return f"₹{','.join(parts)},{last_three}"


def format_prize_display(prize_str: str) -> str:
    """Format a prize string ensuring Indian digit grouping for INR (₹2,00,000)
    and Western digit grouping for USD ($138,000)."""
    if not prize_str or prize_str == "Not specified":
        return "Not specified"

    # Check for INR
    if "₹" in prize_str or "inr" in prize_str.lower() or "rs" in prize_str.lower():
        match = re.search(r"[\d,]+", prize_str)
        if match:
            raw_num_str = match.group(0).replace(",", "")
            if raw_num_str.isdigit():
                return format_inr_amount(int(raw_num_str))
        return prize_str

    # Check for USD
    if "$" in prize_str or "usd" in prize_str.lower():
        match = re.search(r"[\d,]+", prize_str)
        if match:
            raw_num_str = match.group(0).replace(",", "")
            if raw_num_str.isdigit():
                return f"${int(raw_num_str):,}"
        return prize_str

    return prize_str


def clean_eligibility(elig: str) -> str:
    """Normalize verbose eligibility lists into clean, readable strings.
    Only collapse lists that genuinely cover all/broad university streams without restrictions.
    Specific restrictions (e.g. year, branch, freshers, degrees) MUST be preserved verbatim.
    """
    if not elig or elig == "Not specified":
        return "Open to all students"
    text = elig.lower()

    # Specific restrictions: year, department, freshers, degree requirements MUST be preserved verbatim
    specific_indicators = [
        "3rd-year", "3rd year", "final-year", "final year", "freshers", "fresher",
        "it background", "cs only", "cse only", "women only", "high school",
        "working professionals", "batch of", "passout", "graduating", "semester",
        "undergraduate only", "postgraduate only"
    ]
    if any(ind in text for ind in specific_indicators):
        return elig.strip().rstrip(".")

    # Check for verbose Unstop stream list covering all disciplines
    broad_disciplines = ["management", "medical", "law", "arts", "commerce", "sciences"]
    matches = sum(1 for kw in broad_disciplines if kw in text)
    if matches >= 3 or ("engineering" in text and any(k in text for k in ["management", "medical", "law"]) and "others" in text):
        return "Open to all streams (incl. Engineering)"

    # Pure generic strings without stream or year qualifications
    generic_exact = [
        "open to all students", "open to all university students", "open to all college students",
        "open to all", "open to students", "all college students", "all students"
    ]
    if text.strip().rstrip(".") in generic_exact:
        return "Open to all streams (incl. Engineering)"

    return elig.strip().rstrip(".")


class HackathonEnricher:
    """Enriches raw hackathons with unstructured field extraction and 1-line summaries."""

    def __init__(self, storage: Storage, model_name: str = DEFAULT_GEMINI_MODEL, max_wait_time: float = 120.0):
        self.storage = storage
        self.model_name = model_name
        self.api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.total_wait_time: float = 0.0
        self.max_wait_time: float = max_wait_time
        self.gemini_call_count: int = 0

    def enrich_all(self, raw_items: list[RawHackathon], reputed_organizers: list[str], allow_gemini: bool = True) -> list[Hackathon]:
        """Enrich a list of RawHackathon objects into fully populated Hackathon objects."""
        results: list[Hackathon] = []
        for raw in raw_items:
            enriched = self.enrich(raw, reputed_organizers, allow_gemini=allow_gemini)
            results.append(enriched)
        return results

    def enrich(self, raw: RawHackathon, reputed_organizers: list[str], allow_gemini: bool = True) -> Hackathon:
        """Enrich single RawHackathon, checking SQLite cache first."""
        item_id = f"{raw.source}_{raw.source_id}"

        # 1. Check cache
        cached = self.storage.get_cached_enrichment(item_id)
        if cached:
            logger.info("Enriching '%s' (%s): [CACHE]", raw.title, item_id)
            return self._build_hackathon(raw, cached, reputed_organizers)

        # 2. Try Gemini enrichment if permitted and API key present
        enrichment_data: Optional[dict[str, Any]] = None
        if allow_gemini and self.api_key:
            try:
                enrichment_data = self._call_gemini(raw)
                self.gemini_call_count += 1
                logger.info("Enriching '%s' (%s): [GEMINI API]", raw.title, item_id)
                time.sleep(1.0)  # Gentle spacing to respect free tier RPM
            except Exception as e:
                logger.warning("Gemini enrichment failed for %s: %s. Falling back to rule-based.", item_id, e)

        # 3. Fallback to rule-based regex extraction
        if not enrichment_data:
            enrichment_data = self._fallback_extract(raw)
            if allow_gemini:
                logger.info("Enriching '%s' (%s): [FALLBACK REGEX]", raw.title, item_id)

        # Cache valid enrichment only if it was produced with Gemini allowed
        if enrichment_data and allow_gemini:
            self.storage.cache_enrichment(item_id, enrichment_data)

        return self._build_hackathon(raw, enrichment_data, reputed_organizers)

    @staticmethod
    def extract_prize_pool(text: str, default_pool: str = "Not specified", default_inr: float = 0.0) -> tuple[str, float]:
        """Extract numeric prize pool string and INR numeric value from text with Indian formatting."""
        if default_pool != "Not specified" and default_inr > 0:
            if "₹" in default_pool:
                return format_inr_amount(default_inr), default_inr
            return default_pool, default_inr

        # Dollar matching: e.g. $138,000 or $50,000
        dollar_match = re.search(r"\$\s*([\d,]+)", text)
        if dollar_match:
            amount_str = dollar_match.group(1).replace(",", "")
            if amount_str.isdigit() and int(amount_str) >= 500:
                val = float(amount_str)
                return f"${int(val):,}", val * 85.0

        # INR matching: ₹2,00,000 or Rs. 2,00,000 or 2,00,000 INR
        inr_match = re.search(
            r"(?:prize\s*pool|prizes?\s*worth|cash\s*prizes?|total\s*prizes?|worth)[^\w\d]{0,10}(?:₹|rs\.?|inr)?\s*([\d,]+)",
            text,
            re.IGNORECASE,
        )
        if inr_match:
            amount_str = inr_match.group(1).replace(",", "")
            if amount_str.isdigit() and int(amount_str) >= 500:
                val = float(amount_str)
                return format_inr_amount(val), val

        direct_inr = re.search(r"₹\s*([\d,]+)", text)
        if direct_inr:
            amount_str = direct_inr.group(1).replace(",", "")
            if amount_str.isdigit() and int(amount_str) >= 500:
                val = float(amount_str)
                return format_inr_amount(val), val

        return default_pool, default_inr

    def _call_gemini(self, raw: RawHackathon) -> dict[str, Any]:
        """Call Gemini generateContent API with strict JSON instructions and grounding rules."""
        clean_desc = BeautifulSoup(raw.raw_description, "html.parser").get_text(separator=" ", strip=True)
        
        prompt = f"""You are a precise data extractor for college student hackathons.
Extract the structured fields from this hackathon announcement.

CRITICAL RULES - STRICT GROUNDING REQUIRED:
1. accommodation: MUST be "Yes" ONLY if FREE overnight accommodation, hostel stay, or lodging is explicitly provided without extra charges by the organizers for participants.
   - If accommodation requires payment ("charges apply"), if participants must arrange their own, if only "rest facilities/chairs" during the sprint are provided, or for ANY Online/virtual hackathon, you MUST return "Not specified". Never assume or infer accommodation is provided.
2. food_or_travel_support: MUST be "Not specified" unless food, meals, snacks, refreshments, or travel reimbursements are explicitly stated in the text.
3. perks: ONLY list perks explicitly stated in the text (e.g. "Certificate", "Internship", "PPO", "Swag", "Goodies"). If no perks are explicitly mentioned, return an empty list []. Never invent or infer perks.
4. prize_pool: Extract the exact total cash prize pool with currency symbol (e.g. "₹2,00,000", "$50,000", "₹35,000") if stated in the title or text. If no prize amount is mentioned, return "Not specified".
5. eligibility: If the announcement indicates all streams/branches or broad university disciplines can participate without restriction, return "Open to all streams (incl. Engineering)". If restricted to specific years, batches, freshers, branches, degrees, or regions (e.g. "Open to 3rd-year, final-year students, and freshers from an IT background" or "Open to global participants (Open to India)"), preserve those specific requirements verbatim.
6. summary: One punchy, informative 1-line sentence summarizing the hackathon theme and objective (under 120 chars).

Title: {raw.title}
Source: {raw.source}
Organizer: {raw.organizer}
Venue/Location: {raw.venue} ({raw.city})
Mode: {raw.mode}
Pre-extracted Prize Pool: {raw.prize_pool}
Raw Eligibility Details: {raw.raw_eligibility}
Description/Details:
{clean_desc}

Return ONLY a valid JSON object matching this schema:
{{
  "accommodation": "Yes" | "No" | "Not specified",
  "food_or_travel_support": "string description or 'Not specified'",
  "participation_type": "Solo only" | "Team only (X-Y members)" | "Team or Solo (X-Y members)",
  "eligibility": "concise description or 'Open to all streams (incl. Engineering)'",
  "b_tech_eligible": true | false,
  "final_year_friendly": true | false,
  "prize_pool": "exact cash prize pool amount or 'Not specified'",
  "perks": ["list of detected perks"],
  "summary": "1-line summary under 120 chars"
}}"""

        url = GEMINI_API_URL.format(model=self.model_name, key=self.api_key)
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "response_mime_type": "application/json"
            }
        }

        for attempt in range(3):
            resp = requests.post(url, headers=headers, json=payload, timeout=20)
            if resp.status_code in [429, 503] and attempt < 2:
                wait_sec = 4.0
                if self.total_wait_time + wait_sec > self.max_wait_time:
                    logger.warning("Gemini rate-limit wait cap (%.1fs) reached. Skipping retry for '%s'.", self.max_wait_time, raw.title)
                    break
                logger.info("Gemini HTTP %d for '%s'. Waiting 4s before retry (%d/2)...", resp.status_code, raw.title, attempt + 1)
                time.sleep(wait_sec)
                self.total_wait_time += wait_sec
                continue
            resp.raise_for_status()
            break
        resp_json = resp.json()
        
        # Parse output JSON
        candidates = resp_json.get("candidates", [])
        if candidates and "content" in candidates[0]:
            parts = candidates[0]["content"].get("parts", [])
            if parts and "text" in parts[0]:
                text = parts[0]["text"].strip()
                data = json.loads(text)
                if isinstance(data, dict):
                    # Ensure prize pool numeric resolution: NEVER overwrite a known raw prize with 'Not specified'
                    gemini_pool = data.get("prize_pool")
                    if gemini_pool and gemini_pool != "Not specified":
                        resolved_pool, resolved_inr = self.extract_prize_pool(
                            gemini_pool,
                            default_pool=gemini_pool,
                            default_inr=0.0,
                        )
                        data["prize_pool"] = resolved_pool
                        data["prize_pool_inr"] = resolved_inr
                    elif raw.prize_pool and raw.prize_pool != "Not specified":
                        data["prize_pool"] = raw.prize_pool
                        data["prize_pool_inr"] = raw.prize_pool_inr
                    else:
                        resolved_pool, resolved_inr = self.extract_prize_pool(
                            f"{raw.title} {clean_desc}",
                            default_pool="Not specified",
                            default_inr=0.0,
                        )
                        data["prize_pool"] = resolved_pool
                        data["prize_pool_inr"] = resolved_inr

                    data["eligibility"] = clean_eligibility(data.get("eligibility", ""))
                    return data

        raise ValueError("Invalid response structure from Gemini API")

    def _fallback_extract(self, raw: RawHackathon) -> dict[str, Any]:
        """Rule-based regex extractor when Gemini is not available or errors out."""
        clean_desc_orig = BeautifulSoup(raw.raw_description, "html.parser").get_text(separator=" ", strip=True)
        combined_text = f"{raw.title} {raw.raw_eligibility} {clean_desc_orig}".lower()

        # Accommodation
        if (raw.mode or "").lower() == "online":
            accommodation = "Not specified"
        elif re.search(r"\b(free accommodation|accommodation\s*(?:and\s*[\w\s]{1,30})?\s*(?:will be|is)?\s*provided|stay provided|accommodation within campus|hostel accommodation|hostel stay)\b", combined_text):
            if "charges apply" in combined_text or "arrange their own" in combined_text or "paid accommodation" in combined_text:
                accommodation = "Not specified"
            else:
                accommodation = "Yes"
        elif re.search(r"\b(no accommodation|accommodation not provided)\b", combined_text):
            accommodation = "No"
        else:
            accommodation = "Not specified"

        # Food & Travel
        food_match = re.search(r"\b(free food|food accessibility|meals provided|breakfast|lunch|dinner|travel allowance|travel reimbursement)\b", combined_text)
        if food_match:
            food_support = "Provided (food / refreshments)"
        else:
            food_support = "Not specified"

        # Perks
        perks: list[str] = []
        if re.search(r"\b(internship|internships)\b", combined_text):
            perks.append("Internship Opportunity")
        if re.search(r"\b(ppo|pre-placement|job offer|full-time offer)\b", combined_text):
            perks.append("Pre-Placement Offer (PPO)")
        if re.search(r"\b(certificate|certificates|certification)\b", combined_text):
            perks.append("Certificate")
        if re.search(r"\b(goodies|swag|swags|merchandise|t-shirt|stickers)\b", combined_text):
            perks.append("Goodies & Swag")
        if raw.prize_pool and raw.prize_pool != "Not specified":
            perks.append("Cash Prizes")

        # Eligibility & B.Tech checks
        b_tech_eligible = True
        b_tech_specific = False
        final_year_friendly = True

        # If explicitly restricted to non-engineering or school only
        if "school only" in combined_text or "high school only" in combined_text:
            b_tech_eligible = False
            b_tech_specific = False
            final_year_friendly = False
            eligibility_str = "High school students only"
        elif "working professionals only" in combined_text:
            b_tech_eligible = False
            b_tech_specific = False
            final_year_friendly = False
            eligibility_str = "Working professionals only"
        else:
            # Check if description mentions specific eligibility (e.g. 3rd-year, final-year, IT background)
            elig_match = re.search(
                r"(?:eligibility\s*[:\-–]?\s*)([^\n\.\<]{10,120})",
                clean_desc_orig,
                re.IGNORECASE,
            )
            if elig_match and any(ind in elig_match.group(1).lower() for ind in ["3rd-year", "final-year", "freshers", "it background"]):
                eligibility_str = elig_match.group(1).strip()
                b_tech_eligible = True
                b_tech_specific = True
            elif re.search(r"\b(b\.?tech|engineering|b\.e\.?|cse|ece|bca|mca|information\s*technology|computer\s*science)\b", combined_text) or re.search(r"\b(B\.?E\.?|IT)\b", clean_desc_orig):
                b_tech_eligible = True
                b_tech_specific = True
                eligibility_str = "B.Tech / Engineering Students (All years)"
            else:
                b_tech_eligible = True
                b_tech_specific = False
                eligibility_str = "Open to all university students"

        # Smarter prize pool extraction if source didn't pre-populate
        prize_pool, prize_pool_inr = self.extract_prize_pool(
            f"{raw.title} {combined_text}",
            default_pool=raw.prize_pool,
            default_inr=raw.prize_pool_inr,
        )
        if prize_pool != "Not specified" and "Cash Prizes" not in perks:
            perks.append("Cash Prizes")

        # Clean, well-formed Summary without lowercasing, leading boilerplate, or raw addresses
        summary = ""
        if clean_desc_orig:
            # Strip boilerplate prefixes case-insensitively
            cleaned_text = re.sub(
                r"^(?:overview\s*[:\-–]?|about\s*(?:the\s*)?(?:hackathon|event)?\s*[:\-–]?|description\s*[:\-–]?|note\s*[:\-–]?|devfolio hackathon\s*[:\-–]?)\s*",
                "",
                clean_desc_orig,
                flags=re.IGNORECASE,
            ).strip()

            # Discard if it starts with an address/venue fragment
            if not re.match(r"^(?:plot|sector|road|campus|near|opp|street|building|ground)\b", cleaned_text, re.IGNORECASE):
                # Split by sentence endings
                sentences = re.split(r"(?<=[.!?])\s+", cleaned_text)
                if sentences and sentences[0]:
                    first_sent = sentences[0].strip()
                    if 20 <= len(first_sent) <= 137:
                        summary = first_sent
                    elif len(first_sent) > 137:
                        # Truncate at clean word boundary
                        truncated = first_sent[:137].rsplit(" ", 1)[0].rstrip(" ,.-")
                        summary = truncated + "..."

        # Fallback to high-quality synthesized summary if text was missing, messy, or address-only
        if not summary or len(summary) < 20 or re.search(r"\b(road|colony|nagar|campus|plot no)\b", summary, re.IGNORECASE):
            org_str = f" hosted by {raw.organizer}" if raw.organizer and raw.organizer != "Not specified" else ""
            summary = f"{raw.title}{org_str}: innovation sprint and competitive hackathon."

        return {
            "accommodation": accommodation,
            "food_or_travel_support": food_support,
            "participation_type": raw.participation_type,
            "eligibility": clean_eligibility(eligibility_str),
            "b_tech_eligible": b_tech_eligible,
            "b_tech_specific": b_tech_specific,
            "final_year_friendly": final_year_friendly,
            "perks": perks,
            "prize_pool": prize_pool,
            "prize_pool_inr": prize_pool_inr,
            "summary": summary,
        }

    def _build_hackathon(
        self,
        raw: RawHackathon,
        data: dict[str, Any],
        reputed_organizers: list[str],
    ) -> Hackathon:
        """Construct full Hackathon model from RawHackathon and enrichment data."""
        item_id = f"{raw.source}_{raw.source_id}"

        # Organizer reputation flag
        reputed = False
        org_name = raw.organizer or ""
        title = raw.title
        for target in reputed_organizers:
            pattern = rf"\b{re.escape(target)}\b"
            if re.search(pattern, org_name, re.IGNORECASE) or re.search(pattern, title, re.IGNORECASE):
                reputed = True
                break

        # Perks list
        raw_perks = data.get("perks") or []
        perks_list = raw_perks if isinstance(raw_perks, list) else [str(raw_perks)]

        # Use refined prize pool if found during fallback/enrichment, or extract from full description
        prize_pool = raw.prize_pool
        prize_pool_inr = raw.prize_pool_inr
        data_pool = data.get("prize_pool")
        if data_pool and data_pool != "Not specified":
            prize_pool = data_pool
            prize_pool_inr = data.get("prize_pool_inr", raw.prize_pool_inr)

        if prize_pool == "Not specified" or prize_pool_inr == 0.0:
            prize_pool, prize_pool_inr = self.extract_prize_pool(
                f"{raw.title} {raw.raw_description}",
                default_pool=prize_pool,
                default_inr=prize_pool_inr,
            )
        prize_pool = format_prize_display(prize_pool)

        # Strict accommodation grounding:
        # 1. Online events CANNOT offer campus accommodation
        # 2. Guard against paid accommodation or sprint rest facilities
        accommodation = data.get("accommodation") or "Not specified"
        if (raw.mode or "").lower() == "online":
            accommodation = "Not specified"
        elif accommodation.lower() == "yes":
            desc_lower = f"{raw.title} {raw.raw_description}".lower()
            if "charges apply" in desc_lower or "arrange their own" in desc_lower or "paid accommodation" in desc_lower:
                accommodation = "Not specified"
            elif ("rest arrangements" in desc_lower or "rest facilities" in desc_lower) and not any(k in desc_lower for k in ["free accommodation", "accommodation provided", "hostel stay", "accommodation will be provided", "accommodation is provided"]):
                accommodation = "Not specified"

        # Normalize eligibility
        raw_elig_text = data.get("eligibility") or raw.raw_eligibility or "Not specified"
        eligibility = clean_eligibility(raw_elig_text)

        # Check if description has specific eligibility restrictions that might have been flattened
        if "open to all" in eligibility.lower():
            m_elig = re.search(r"(?:eligibility\s*[:\-–]?\s*)([^\n\.\<]{10,120})", raw.raw_description, re.IGNORECASE)
            if m_elig:
                cand = m_elig.group(1).strip()
                if any(ind in cand.lower() for ind in ["3rd-year", "final-year", "freshers", "it background"]):
                    eligibility = cand

        if raw.source.lower() == "devpost":
            if "not open to india" in (raw.raw_eligibility or "").lower():
                eligibility = "Not open to India"
            elif "open to india" not in eligibility.lower():
                eligibility = f"{eligibility} (Open to India)"

        b_tech_eligible = bool(data.get("b_tech_eligible", True))
        b_tech_specific = bool(data.get("b_tech_specific", False))
        if "not open to india" in eligibility.lower():
            b_tech_eligible = False
            b_tech_specific = False
        elif eligibility == "Open to all streams (incl. Engineering)":
            b_tech_specific = False
            b_tech_eligible = True

        return Hackathon(
            id=item_id,
            title=raw.title,
            source=raw.source,
            organizer=raw.organizer,
            venue=raw.venue,
            city=raw.city,
            mode=raw.mode,
            event_start=raw.event_start,
            event_end=raw.event_end,
            registration_deadline=raw.registration_deadline,
            entry_fee=raw.entry_fee,
            participation_type=data.get("participation_type") or raw.participation_type,
            accommodation=accommodation,
            food_or_travel_support=data.get("food_or_travel_support") or "Not specified",
            prize_pool=prize_pool,
            prize_pool_inr=prize_pool_inr,
            perks=perks_list,
            eligibility=eligibility,
            b_tech_eligible=b_tech_eligible,
            b_tech_specific=b_tech_specific,
            final_year_friendly=bool(data.get("final_year_friendly", True)),
            organizer_reputation_flag=reputed,
            summary=data.get("summary") or "Not specified",
            registration_url=raw.registration_url,
            raw_ref=raw,
        )
