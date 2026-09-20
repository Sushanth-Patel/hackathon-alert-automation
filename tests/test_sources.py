"""Tests for all 5 source parsers using saved JSON/HTML fixtures."""

import json
from pathlib import Path
from bs4 import BeautifulSoup
import pytest

from sources.unstop import UnstopSource
from sources.devfolio import DevfolioSource
from sources.devpost import DevpostSource
from sources.hackerearth import HackerEarthSource
from sources.mlh import MLHSource

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_unstop_parser_fixture():
    fixture_path = FIXTURES_DIR / "unstop_sample.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        sample_item = json.load(f)

    source = UnstopSource(delay_seconds=0)
    raw = source.parse_item(sample_item)

    assert raw is not None
    assert raw.source == "unstop"
    assert raw.source_id == "1737808"
    assert raw.title == "HackCelestial 3.0"
    assert raw.organizer == "Pillai University, Navi Mumbai"
    assert raw.city == "Navi Mumbai"
    assert "Plot No. 10" in raw.venue
    assert raw.mode == "offline"
    assert raw.entry_fee == "₹1,500"
    assert raw.participation_type == "Team or Solo (1–5 members)"
    assert raw.prize_pool == "₹1,50,000"
    assert raw.prize_pool_inr == 150000.0
    assert raw.registration_deadline is not None
    assert raw.registration_url.startswith("https://unstop.com/")


def test_devfolio_parser_fixture():
    fixture_path = FIXTURES_DIR / "devfolio_sample.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        sample_item = json.load(f)

    source = DevfolioSource(delay_seconds=0)
    raw = source.parse_item(sample_item)

    assert raw is not None
    assert raw.source == "devfolio"
    assert raw.source_id == "9f3e3e2ea4194c7195b519b6808c4779"
    assert raw.title == "HackSpire'26"
    assert raw.city == "Kolkata"
    assert raw.mode == "offline"
    assert raw.entry_fee == "Free"
    assert raw.registration_deadline is not None
    assert raw.registration_url == "https://www.hackspire.tech"


def test_devpost_parser_fixture():
    fixture_path = FIXTURES_DIR / "devpost_sample.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        sample_item = json.load(f)

    source = DevpostSource(delay_seconds=0)
    raw = source.parse_item(sample_item)

    assert raw is not None
    assert raw.source == "devpost"
    assert raw.source_id == "29969"
    assert raw.title == "RevenueCat Shipaton 2026"
    assert raw.organizer == "RevenueCat"
    assert raw.mode == "online"
    assert raw.prize_pool == "$740,000"
    assert raw.prize_pool_inr > 0.0
    assert raw.registration_deadline is not None
    assert raw.registration_url == "https://revenuecat-shipaton-2026.devpost.com/"
    assert raw.raw_eligibility == "Open to global participants (Open to India)"


def test_devpost_parser_non_india():
    source = DevpostSource(delay_seconds=0)
    # Offline in Canada
    item_waterloo = {
        "id": "16116",
        "title": "Hack the North 2026",
        "displayed_location": {"location": "University of Waterloo, Canada"},
        "invite_only": True,
        "eligibility_requirement_invite_only_description": "Accepted Hack the North participants",
    }
    raw_ca = source.parse_item(item_waterloo)
    assert raw_ca is not None
    assert raw_ca.raw_eligibility == "Not open to India"


def test_hackerearth_parser_fixture():
    fixture_path = FIXTURES_DIR / "hackerearth_sample.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        sample_item = json.load(f)

    source = HackerEarthSource(delay_seconds=0)
    raw = source.parse_item(sample_item)

    assert raw is not None
    assert raw.source == "hackerearth"
    assert raw.source_id == "github-repo-value-check"
    assert raw.title == "GitHub Repo Value Check"
    assert raw.mode == "online"
    assert raw.entry_fee == "Free"
    assert raw.registration_deadline is not None
    assert raw.registration_url == "https://www.hackerearth.com/challenges/hackathon/github-repo-value-check/"


def test_mlh_parser_fixture():
    fixture_path = FIXTURES_DIR / "mlh_sample_card.html"
    with open(fixture_path, "r", encoding="utf-8") as f:
        card_html = f.read()

    soup = BeautifulSoup(card_html, "html.parser")
    card = soup.find("a")

    source = MLHSource(delay_seconds=0)
    raw = source.parse_card(card)

    assert raw is not None
    assert raw.source == "mlh"
    assert raw.title == "HackPrix Season 3"
    assert raw.city == "Hyderabad"
    assert "Telangana" in raw.venue
    assert raw.mode == "offline"
    assert raw.entry_fee == "Free"
    assert raw.registration_deadline is not None
    assert raw.registration_url.startswith("https://s3.hackprix.tech")
