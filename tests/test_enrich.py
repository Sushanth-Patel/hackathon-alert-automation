"""Tests for Gemini enrichment and regex fallback."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from models import RawHackathon
from storage import Storage
from enrich import HackathonEnricher


def test_gemini_enrichment_success():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        storage = Storage(db_path=db_path)

        enricher = HackathonEnricher(storage=storage)
        enricher.api_key = "dummy_valid_key"

        raw = RawHackathon(
            source="unstop",
            source_id="12345",
            title="Hyderabad AI Hackathon",
            registration_url="https://example.com/register",
            organizer="Vignan Institute",
            venue="Vignan Campus, Hyderabad",
            city="Hyderabad",
            mode="offline",
            raw_description="We provide free accommodation for outstation teams and meals during 24 hours.",
            raw_eligibility="B.Tech all years",
        )

        mock_response_json = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps({
                                    "accommodation": "Yes",
                                    "food_or_travel_support": "Provided (meals & refreshments)",
                                    "participation_type": "Team only (2-4 members)",
                                    "eligibility": "B.Tech Engineering students",
                                    "b_tech_eligible": True,
                                    "final_year_friendly": True,
                                    "perks": ["Internship Opportunity", "Cash Prizes"],
                                    "summary": "24-hour Hyderabad AI hackathon with free stay and meals."
                                })
                            }
                        ]
                    }
                }
            ]
        }

        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_response_json
        mock_resp.raise_for_status = MagicMock()

        with patch("requests.post", return_value=mock_resp):
            with patch.object(enricher.storage, "cache_enrichment", wraps=enricher.storage.cache_enrichment) as mock_cache:
                h = enricher.enrich(raw, reputed_organizers=["Vignan"])

                assert h.accommodation == "Yes"
                assert h.food_or_travel_support == "Provided (meals & refreshments)"
                assert "Internship Opportunity" in h.perks
                assert h.summary == "24-hour Hyderabad AI hackathon with free stay and meals."
                mock_cache.assert_called_once()

        # Second call should hit [CACHE]
        h_cached = enricher.enrich(raw, reputed_organizers=["Vignan"])
        assert h_cached.accommodation == "Yes"


def test_gemini_fallback_on_error():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        storage = Storage(db_path=db_path)

        enricher = HackathonEnricher(storage=storage)
        enricher.api_key = "invalid_key"

        raw = RawHackathon(
            source="devfolio",
            source_id="999",
            title="Builders Day",
            registration_url="https://example.com/builders",
            organizer="Devfolio Community",
            venue="Lords Skill Academy, Hyderabad",
            city="Hyderabad",
            mode="offline",
            raw_description="Join us for a builder sprint in Hyderabad.",
            raw_eligibility="Open to students",
        )

        # Simulate HTTP 400/403 or network failure
        with patch("requests.post", side_effect=Exception("API key not valid")):
            h = enricher.enrich(raw, reputed_organizers=[])
            # Fallback regex must succeed without raising exception
            assert h.title == "Builders Day"
            assert h.b_tech_eligible is True
            assert h.summary != ""


def test_gemini_no_accommodation_strict():
    """Assert accommodation is 'Not specified' when the description does not explicitly mention it."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        storage = Storage(db_path=db_path)

        enricher = HackathonEnricher(storage=storage)
        enricher.api_key = "dummy_valid_key"

        raw = RawHackathon(
            source="unstop",
            source_id="88888",
            title="AI Innovation Sprint",
            registration_url="https://example.com/ai-sprint",
            organizer="Engineering Tech Club",
            venue="Campus Auditorium, Hyderabad",
            city="Hyderabad",
            mode="offline",
            raw_description="A 24-hour coding challenge. Solve real-world AI problems and win cash prizes of ₹2,00,000!",
            raw_eligibility="Engineering Students | Postgraduate | Undergraduate | Management | Medical | Law | Arts, Commerce, Sciences & Others",
        )

        mock_response_json = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps({
                                    "accommodation": "Not specified",
                                    "food_or_travel_support": "Not specified",
                                    "participation_type": "Team only (2-4 members)",
                                    "eligibility": "Open to all streams (incl. Engineering)",
                                    "b_tech_eligible": True,
                                    "final_year_friendly": True,
                                    "prize_pool": "₹2,00,000",
                                    "perks": ["Cash Prizes"],
                                    "summary": "24-hour Hyderabad AI innovation sprint."
                                })
                            }
                        ]
                    }
                }
            ]
        }

        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_response_json
        mock_resp.raise_for_status = MagicMock()

        with patch("requests.post", return_value=mock_resp):
            h = enricher.enrich(raw, reputed_organizers=[], allow_gemini=True)

            # Accommodation must be strictly Not specified
            assert h.accommodation == "Not specified"
            # Eligibility must be cleaned and not show pipe-separated list
            assert h.eligibility == "Open to all streams (incl. Engineering)"
            # Prize pool must be formatted with Indian digit grouping as ₹2,00,000
            assert h.prize_pool == "₹2,00,000"
            assert h.prize_pool_inr == 200000.0


def test_clean_eligibility_broad_streams():
    from enrich import clean_eligibility
    long_list = "Engineering Students | Postgraduate | Undergraduate | Management | Medical | Law | Arts, Commerce, Sciences & Others"
    assert clean_eligibility(long_list) == "Open to all streams (incl. Engineering)"

    comma_list = "Engineering Students, Postgraduate, Undergraduate, Management, Medical, Law, Arts, Commerce, Sciences & Others"
    assert clean_eligibility(comma_list) == "Open to all streams (incl. Engineering)"

    specific_list = "B.Tech / Engineering Students (All years)"
    assert clean_eligibility(specific_list) == "B.Tech / Engineering Students (All years)"


def test_clean_eligibility_preserves_specific_restrictions():
    from enrich import clean_eligibility
    s1 = "Open to 3rd-year, final-year students, and freshers from an IT background"
    assert clean_eligibility(s1) == s1

    s2 = "Open to 3rd-year students, final-year students, and freshers from an IT background"
    assert clean_eligibility(s2) == s2

    s3 = "Batch of 2026 and 2027 CSE only"
    assert clean_eligibility(s3) == s3


def test_currency_formatting_indian_and_western():
    from enrich import format_prize_display, format_inr_amount
    assert format_inr_amount(200000) == "₹2,00,000"
    assert format_inr_amount(100000) == "₹1,00,000"
    assert format_inr_amount(35000) == "₹35,000"
    assert format_inr_amount(699) == "₹699"

    assert format_prize_display("₹200,000") == "₹2,00,000"
    assert format_prize_display("₹100,000") == "₹1,00,000"
    assert format_prize_display("₹35,000") == "₹35,000"
    assert format_prize_display("$138,000") == "$138,000"
    assert format_prize_display("$50000") == "$50,000"


def test_accommodation_grounding_online_and_paid():
    import tempfile
    from pathlib import Path
    from storage import Storage
    from enrich import HackathonEnricher
    from models import RawHackathon

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_enrich.db"
        storage = Storage(db_path)
        enricher = HackathonEnricher(storage=storage)

        # 1. Online event with guest house charges mentioned
        game_jam = RawHackathon(
            source="unstop",
            source_id="1758206",
            title="Game Jam - TantraFiesta 2026",
            registration_url="https://unstop.com/hackathons/gamejam",
            raw_payload={},
            organizer="IIIT Nagpur",
            venue="Online",
            city="Online",
            mode="online",
            raw_description="In case of arrival before 23rd October, finalists must either arrange their own accommodation or contact the organizers for accommodation in the Guest House (charges apply).",
        )
        h_jam = enricher.enrich(game_jam, reputed_organizers=[], allow_gemini=False)
        assert h_jam.accommodation == "Not specified"

        # 2. Codestorm with rest facilities only
        codestorm = RawHackathon(
            source="unstop",
            source_id="1750877",
            title="Nrcm's Codestorm - 2K26",
            registration_url="https://unstop.com/hackathons/codestorm",
            raw_payload={},
            organizer="Narsimha Reddy Engineering College",
            venue="NRCM Campus",
            city="Hyderabad",
            mode="offline",
            raw_description="Rest Facilities: Dedicated rest arrangements during the hackathon.",
        )
        h_code = enricher.enrich(codestorm, reputed_organizers=[], allow_gemini=False)
        assert h_code.accommodation == "Not specified"

        # 3. VJ Hackathon with free accommodation provided
        vj = RawHackathon(
            source="unstop",
            source_id="1750281",
            title="VJ Hackathon 2026",
            registration_url="https://unstop.com/hackathons/vj",
            raw_payload={},
            organizer="VNR VJIET",
            venue="VNR VJIET Campus",
            city="Hyderabad",
            mode="offline",
            raw_description="Accommodation and refreshments will be provided at the venue for the entire duration of the hackathon.",
        )
        h_vj = enricher.enrich(vj, reputed_organizers=[], allow_gemini=False)
        assert h_vj.accommodation == "Yes"

