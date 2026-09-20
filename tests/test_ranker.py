"""Tests for Ranker scoring, section partitioning, quality threshold, recruitment filter, and location rules."""

from datetime import datetime, timedelta
import yaml
from pathlib import Path
from models import Hackathon, IST
from ranker import Ranker

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def get_test_ranker():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return Ranker(cfg)


def test_ranker_btech_separator():
    ranker = get_test_ranker()
    now = datetime.now(IST)

    # Ineligible event
    h_ineligible = Hackathon(
        id="h_ineligible",
        title="High School Hack",
        source="mlh",
        b_tech_eligible=False,
        registration_deadline=now + timedelta(days=10),
    )
    # Eligible event - Open to all
    h_eligible_all = Hackathon(
        id="h_eligible_all",
        title="College Hack Open To All",
        source="devfolio",
        b_tech_eligible=True,
        b_tech_specific=False,
        registration_deadline=now + timedelta(days=10),
    )
    # Eligible event - specifically B.Tech/Engineering
    h_eligible_btech = Hackathon(
        id="h_eligible_btech",
        title="B.Tech Engineering Hackathon",
        source="unstop",
        b_tech_eligible=True,
        b_tech_specific=True,
        registration_deadline=now + timedelta(days=10),
    )

    s_ineligible = ranker.calculate_score(h_ineligible)
    s_eligible_all = ranker.calculate_score(h_eligible_all)
    s_eligible_btech = ranker.calculate_score(h_eligible_btech)

    assert s_eligible_btech > s_eligible_all > s_ineligible
    assert s_eligible_btech >= 100.0


def test_ranker_partitioning_hyderabad_and_popularity():
    ranker = get_test_ranker()
    now = datetime.now(IST)

    # Section A candidate (Hyderabad offline)
    h_hyd = Hackathon(
        id="h_hyd",
        title="Hyderabad AI Hack",
        source="unstop",
        city="Hyderabad",
        venue="Gachibowli Stadium",
        mode="offline",
        registration_deadline=now + timedelta(days=5),
        b_tech_eligible=True,
        b_tech_specific=True,
    )

    # Section B candidate (Online, reputed organizer, meets min_score)
    h_pop = Hackathon(
        id="h_pop",
        title="Google Cloud Hackathon",
        source="devpost",
        city="Online",
        venue="Online",
        mode="online",
        organizer_reputation_flag=True,
        registration_deadline=now + timedelta(days=5),
        b_tech_eligible=True,
        b_tech_specific=True,
    )

    # Expired event (should be filtered out)
    h_expired = Hackathon(
        id="h_expired",
        title="Old Hackathon",
        source="unstop",
        city="Hyderabad",
        registration_deadline=now - timedelta(days=2),
    )

    sec_a, sec_b = ranker.rank_and_partition([h_hyd, h_pop, h_expired])

    assert len(sec_a) == 1
    assert sec_a[0].id == "h_hyd"

    assert len(sec_b) == 1
    assert sec_b[0].id == "h_pop"

    # Verify no overlap between Section A and Section B
    sec_a_ids = {x.id for x in sec_a}
    sec_b_ids = {x.id for x in sec_b}
    assert sec_a_ids.isdisjoint(sec_b_ids)


def test_section_b_reserve_india_slots():
    ranker = get_test_ranker()
    now = datetime.now(IST)

    # 4 global high-scoring Devpost online events (score ~170)
    global_events = [
        Hackathon(
            id=f"global_{i}",
            title=f"Global Big Tech Challenge {i}",
            source="devpost",
            city="Online",
            mode="online",
            b_tech_eligible=True,
            b_tech_specific=True,
            organizer_reputation_flag=True,
            prize_pool_inr=500000.0,
            registration_deadline=now + timedelta(days=10),
        )
        for i in range(4)
    ]

    # 2 India-based online events meeting min_score (score ~150)
    india_events = [
        Hackathon(
            id=f"india_{i}",
            title=f"India University Online Hackathon {i}",
            source="unstop",
            city="Online",
            mode="online",
            b_tech_eligible=True,
            b_tech_specific=True,
            prize_pool_inr=10000.0,
            registration_deadline=now + timedelta(days=5),
        )
        for i in range(2)
    ]

    all_events = global_events + india_events
    _, sec_b = ranker.rank_and_partition(all_events)

    # Section B cap is 5, with reserve_india_slots: 2
    assert len(sec_b) == 5
    sec_b_sources = [h.source for h in sec_b]
    # At least 2 picks must be India-based (unstop)
    assert sec_b_sources.count("unstop") == 2


def test_section_b_min_score_quality_gate():
    """Verify Section B does NOT pad with low-quality events if fewer than 5 meet min_score."""
    ranker = get_test_ranker()
    now = datetime.now(IST)

    # 2 high quality online events (score > 110)
    strong_events = [
        Hackathon(
            id=f"strong_{i}",
            title=f"Flagship Hackathon {i}",
            source="devpost",
            city="Online",
            mode="online",
            b_tech_eligible=True,
            b_tech_specific=True,
            registration_deadline=now + timedelta(days=5),
        )
        for i in range(2)
    ]

    # 3 weak events (score < 110)
    weak_events = [
        Hackathon(
            id=f"weak_{i}",
            title=f"Random Low Quality Fest {i}",
            source="unstop",
            city="Online",
            mode="online",
            b_tech_eligible=False,  # Ineligible drops score < 0
            registration_deadline=now + timedelta(days=5),
        )
        for i in range(3)
    ]

    _, sec_b = ranker.rank_and_partition(strong_events + weak_events)
    # Must only include the 2 strong events, never pad with weak events
    assert len(sec_b) == 2
    for h in sec_b:
        assert h.score >= ranker.sec_b_min_score


def test_section_b_location_rule_excludes_distant_offline():
    """Verify Section B excludes offline events located outside Telangana (e.g. Kerala college fest)."""
    ranker = get_test_ranker()
    now = datetime.now(IST)

    # Offline event in Kerala (e.g. Hackify 3.0)
    kerala_offline = Hackathon(
        id="kerala_fest",
        title="Hackify 3.0",
        source="unstop",
        city="Kothamangalam",
        venue="M.A. College of Engineering, Kerala",
        mode="offline",
        b_tech_eligible=True,
        b_tech_specific=True,
        registration_deadline=now + timedelta(days=5),
    )

    # Online event
    online_event = Hackathon(
        id="online_event",
        title="National Online Hackathon",
        source="devfolio",
        city="Online",
        mode="online",
        b_tech_eligible=True,
        b_tech_specific=True,
        registration_deadline=now + timedelta(days=5),
    )

    assert not ranker.is_allowed_in_section_b(kerala_offline)
    assert ranker.is_allowed_in_section_b(online_event)

    _, sec_b = ranker.rank_and_partition([kerala_offline, online_event])
    sec_b_ids = [h.id for h in sec_b]
    assert "kerala_fest" not in sec_b_ids
    assert "online_event" in sec_b_ids


def test_recruitment_and_coding_contest_filter():
    """Verify pure hiring challenges / coding contests are excluded, but hiring hackathons with internship/PPO are kept."""
    ranker = get_test_ranker()

    # 1. Pure hiring challenge (e.g. Juspay Hiring Challenge) -> EXCLUDED
    juspay_challenge = Hackathon(
        id="juspay_hiring",
        title="Juspay Hiring Challenge 2026",
        source="hackerearth",
        summary="Online recruitment challenge for developers.",
        perks=[],
    )
    assert ranker.is_recruitment_or_contest(juspay_challenge) is True

    # 2. Coding contest / challenge -> EXCLUDED
    coding_contest = Hackathon(
        id="contest_1",
        title="Weekly Coding Contest 400",
        source="hackerearth",
        summary="Competitive programming test.",
        perks=[],
    )
    assert ranker.is_recruitment_or_contest(coding_contest) is True

    # 3. Hiring Hackathon with internship/PPO -> KEPT
    hiring_hackathon_with_internship = Hackathon(
        id="hiring_hack_1",
        title="FinTech Hiring Hackathon 2026",
        source="hackerearth",
        summary="Build financial models in a 24-hour hackathon.",
        perks=["Internship Opportunity", "Pre-Placement Offer (PPO)"],
    )
    assert ranker.is_recruitment_or_contest(hiring_hackathon_with_internship) is False

    # 4. Regular hackathon -> KEPT
    real_hackathon = Hackathon(
        id="hack_standard",
        title="Smart Mobility AI Hackathon",
        source="hackerearth",
        summary="36-hour sprint to solve urban transit challenges.",
        perks=["Cash Prizes"],
    )
    assert ranker.is_recruitment_or_contest(real_hackathon) is False


def test_closing_soon_cutoff():
    """Verify events with < min_hours_left (default 2h) are dropped."""
    ranker = get_test_ranker()
    now = datetime.now(IST)

    # Event with 1 hour left (< 2.0h cutoff)
    h_too_soon = Hackathon(
        id="too_soon",
        title="Closing in 1 hour Hack",
        source="devpost",
        city="Online",
        mode="online",
        b_tech_eligible=True,
        b_tech_specific=True,
        registration_deadline=now + timedelta(hours=1),
    )

    # Event with 3 hours left (>= 2.0h cutoff)
    h_ok = Hackathon(
        id="ok_time",
        title="Closing in 3 hours Hack",
        source="devpost",
        city="Online",
        mode="online",
        b_tech_eligible=True,
        b_tech_specific=True,
        registration_deadline=now + timedelta(hours=3),
    )

    _, sec_b = ranker.rank_and_partition([h_too_soon, h_ok])
    sec_b_ids = [h.id for h in sec_b]
    assert "too_soon" not in sec_b_ids
    assert "ok_time" in sec_b_ids


def test_no_deadline_events_sorted_last():
    ranker = get_test_ranker()
    now = datetime.now(IST)

    h_with_dl = Hackathon(
        id="with_dl",
        title="Hackathon with Deadline",
        source="unstop",
        city="Online",
        mode="online",
        b_tech_eligible=True,
        b_tech_specific=True,
        registration_deadline=now + timedelta(days=5),
        prize_pool_inr=50000.0,
    )
    h_no_dl = Hackathon(
        id="no_dl",
        title="Hackathon with No Deadline",
        source="devpost",
        city="Online",
        mode="online",
        b_tech_eligible=True,
        b_tech_specific=True,
        registration_deadline=None,
        prize_pool_inr=50000.0,  # Same prize pool / score
    )

    _, sec_b = ranker.rank_and_partition([h_no_dl, h_with_dl])
    # The event with deadline must be sorted before the one without deadline
    assert sec_b[0].id == "with_dl"
    assert sec_b[1].id == "no_dl"


def test_sort_within_section_24h_urgent_first():
    """Verify events closing within 24 hours (e.g. Builders Day) are ALWAYS placed first in a section."""
    ranker = get_test_ranker()
    now = datetime.now(IST)

    # Event with lower score but closing in 9 hours
    h_closing_today = Hackathon(
        id="h_today",
        title="Closing Today Hack",
        source="devfolio",
        city="Hyderabad",
        venue="Lords Academy",
        mode="offline",
        registration_deadline=now + timedelta(hours=9),
        b_tech_eligible=True,
    )

    # Event with much higher score and prize money, but closing in 10 days
    h_later = Hackathon(
        id="h_later",
        title="Big Prize Hack",
        source="unstop",
        city="Hyderabad",
        venue="Gachibowli",
        mode="offline",
        prize_pool_inr=200000.0,
        registration_deadline=now + timedelta(days=10),
        b_tech_eligible=True,
        b_tech_specific=True,
    )

    sec_a, _ = ranker.rank_and_partition([h_later, h_closing_today])
    assert len(sec_a) == 2
    # The event closing within 24 hours MUST be placed first
    assert sec_a[0].id == "h_today"
    assert sec_a[1].id == "h_later"


def test_section_b_india_slots_at_most_2_and_global_flagship_not_crowded_out():
    """Verify India reserve slots are AT MOST 2 and do not crowd out higher-scoring global flagship events."""
    ranker = get_test_ranker()
    now = datetime.now(IST)

    # 4 global flagship events (e.g. Amazon, NVIDIA)
    global_flagships = [
        Hackathon(
            id=f"global_flagship_{i}",
            title=f"Global Flagship Challenge {i}",
            source="devpost",
            city="Online",
            mode="online",
            organizer_reputation_flag=True,
            prize_pool_inr=1000000.0,  # $12k+ USD
            b_tech_eligible=True,
            registration_deadline=now + timedelta(days=20),
        )
        for i in range(4)
    ]

    # 5 India online events
    india_events = [
        Hackathon(
            id=f"india_event_{i}",
            title=f"India Online Hackathon {i}",
            source="unstop",
            city="Online",
            mode="online",
            b_tech_eligible=True,
            b_tech_specific=True,
            prize_pool_inr=10000.0,
            registration_deadline=now + timedelta(days=10),
        )
        for i in range(5)
    ]

    _, sec_b = ranker.rank_and_partition(global_flagships + india_events)
    assert len(sec_b) == 5

    india_in_sec_b = [h for h in sec_b if ranker.is_india_based(h)]
    global_in_sec_b = [h for h in sec_b if not ranker.is_india_based(h)]

    # India events must take at most 2 slots
    assert len(india_in_sec_b) <= 2
    # Global flagship events must not be crowded out
    assert len(global_in_sec_b) >= 3

