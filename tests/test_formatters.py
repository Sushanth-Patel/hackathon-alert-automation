"""Tests for Telegram and Email digest formatters."""

from datetime import datetime, timedelta
from models import Hackathon, IST
from formatters.telegram_fmt import format_digest, format_hackathon_block
from formatters.email_fmt import format_email_digest


def test_telegram_block_formatting_and_escaping():
    now = datetime.now(IST)
    h = Hackathon(
        id="t1",
        title="Hackathon <AI & Web3>",
        source="unstop",
        organizer="College & Tech Labs",
        venue="HITEC City, Hyderabad",
        city="Hyderabad",
        event_start=now + timedelta(days=2),
        event_end=now + timedelta(days=2),  # Single-day event
        registration_deadline=now + timedelta(hours=5),  # Closes today
        entry_fee="Free",
        participation_type="Team only (2-4 members)",
        prize_pool="₹1,00,000",
        perks=["Internship", "Swag"],
        summary="A sprint exploring generative AI <innovations>.",
        registration_url="https://example.com/register?a=1&b=2",
    )

    block = format_hackathon_block(h)

    # Check HTML escaping
    assert "&lt;AI &amp; Web3&gt;" in block
    assert "College &amp; Tech Labs" in block
    assert "&lt;innovations&gt;" in block
    assert "https://example.com/register?a=1&amp;b=2" in block

    # Check single-day event formatting (not "Sep X - Sep X")
    single_date_str = (now + timedelta(days=2)).strftime("%b %d, %Y")
    assert f"Dates: {single_date_str}" in block
    assert " – " not in block.split("Dates: ")[1].split("   ")[0]

    # Check closes today formatting
    assert "Closes today (5h left)" in block

    # Check tags
    assert "🆓 Free" in block
    assert "👥 Team" in block
    assert "🔥 Closing soon" in block


def test_participation_tag_min_1_and_no_literal_1():
    """Verify team size with min=1 renders as '👥 Team / 🧍 Solo', never a literal '1'."""
    cases = [
        "1-4 members",
        "1 - 4 Members",
        "1 to 5 members",
        "Team (1-4 members)",
        "Team or Solo (1-4 members)",
        "1 Solo",
    ]
    for pt in cases:
        h = Hackathon(
            id="pt_test",
            title="Participation Test Hack",
            source="devpost",
            participation_type=pt,
        )
        block = format_hackathon_block(h)
        # Must never have literal "1 Solo"
        assert "1 Solo" not in block
        # Must contain 🧍 Solo
        assert "🧍 Solo" in block


def test_telegram_message_splitting_under_4096_chars():
    now = datetime.now(IST)
    # Generate 15 hackathons to ensure content exceeds 4000 characters
    items = []
    for i in range(15):
        items.append(
            Hackathon(
                id=f"h_{i}",
                title=f"Mega Hackathon Challenge {i}",
                source="unstop",
                organizer=f"University of Technology {i}",
                venue="Gachibowli, Hyderabad",
                city="Hyderabad",
                mode="offline",
                registration_deadline=now + timedelta(days=i + 1),
                entry_fee="Free",
                participation_type="Team",
                summary="A full-day intensive coding marathon focused on solving urban transport challenges with AI.",
                registration_url=f"https://example.com/hack/{i}",
            )
        )

    chunks = format_digest(section_a=items, section_b=[])
    assert len(chunks) > 1

    for chunk in chunks:
        assert len(chunk) <= 4096
        # Ensure divider or proper structure
        assert "Hackathon Alert" in chunk or "Mega Hackathon Challenge" in chunk


def test_email_digest_renders():
    now = datetime.now(IST)
    h = Hackathon(
        id="h1",
        title="Email Test Hack",
        source="devpost",
        registration_deadline=now + timedelta(days=5),
    )
    email_html = format_email_digest(section_a=[h], section_b=[])
    assert "<!DOCTYPE html>" in email_html
    assert "Email Test Hack" in email_html
    assert "Section A: Hyderabad Hackathons" in email_html
