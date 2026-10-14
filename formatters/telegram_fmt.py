"""Telegram HTML digest formatter and smart block-aware message splitter."""

from __future__ import annotations
import html
import re
from datetime import datetime
from models import Hackathon, IST
from enrich import clean_eligibility, format_prize_display

MAX_TELEGRAM_MSG_LEN = 4000  # Safe threshold below 4096


def format_hackathon_block(h: Hackathon) -> str:
    """Format a single hackathon into an aesthetic, highly detailed HTML card for Telegram."""
    title_esc = html.escape(h.title)
    org_esc = html.escape(h.organizer) if h.organizer and h.organizer != "Not specified" else "Organizer TBA"
    venue_esc = html.escape(h.venue)
    elig_esc = html.escape(clean_eligibility(h.eligibility))
    summary_raw = re.sub(r"₹\s*([\d,]+)", lambda m: format_prize_display(m.group(0)), h.summary)
    summary_esc = html.escape(summary_raw)
    url_esc = html.escape(h.registration_url)

    # Platform source brand name
    source_display_names = {
        "unstop": "Unstop",
        "devfolio": "Devfolio",
        "devpost": "Devpost",
        "hackerearth": "HackerEarth",
        "mlh": "MLH",
    }
    platform_name = source_display_names.get(h.source.lower(), h.source.capitalize())

    # Fee tag
    if "free" in h.entry_fee.lower() or h.entry_fee == "0":
        fee_tag = "🆓 Free"
    else:
        fee_tag = f"💰 {html.escape(h.entry_fee)}"

    # Participation tag with exact team size if available
    pt_clean = h.participation_type or ""
    pt_clean = re.sub(r"\b1\s+solo\b", "Solo", pt_clean, flags=re.IGNORECASE)
    pt_lower = pt_clean.lower().strip()

    size_match = re.search(r"(\d+)\s*(?:[-–to]+)\s*(\d+)", pt_clean)
    if size_match:
        min_s, max_s = size_match.group(1), size_match.group(2)
        if min_s == "1":
            part_tag = f"👥 Team / 🧍 Solo ({min_s}–{max_s})"
        else:
            part_tag = f"👥 Team ({min_s}–{max_s})"
    elif "solo only" in pt_lower or pt_lower == "solo":
        part_tag = "🧍 Solo"
    elif "team only" in pt_lower:
        part_tag = "👥 Team"
    elif "team or solo" in pt_lower or ("team" in pt_lower and "solo" in pt_lower):
        part_tag = "👥 Team / 🧍 Solo"
    elif "team" in pt_lower:
        part_tag = "👥 Team"
    else:
        part_tag = "👥 Team / 🧍 Solo"

    # Badges line
    tags = [fee_tag, part_tag]
    if h.is_closing_soon:
        tags.append("🔥 Closing soon")
    tags_str = " • ".join(tags)

    # Location / Mode cleanly formatted without awkward "Not specified (Online)"
    mode_str = h.mode.capitalize() if h.mode else "Offline"
    if (h.mode or "").lower() == "online" or venue_esc == "Online":
        loc_display = "🌐 Online (Virtual)"
    else:
        # Offline or Hybrid
        if venue_esc and venue_esc != "Not specified":
            if h.city and h.city != "Not specified" and h.city.lower() not in venue_esc.lower():
                loc_display = f"{venue_esc}, {html.escape(h.city)} [{mode_str}]"
            else:
                loc_display = f"{venue_esc} [{mode_str}]"
        elif h.city and h.city != "Not specified":
            loc_display = f"{html.escape(h.city)} [{mode_str}]"
        else:
            loc_display = f"Hyderabad & Telangana [{mode_str}]"

    # Dates string (clean single-day or range display)
    if h.event_start and h.event_end:
        if h.event_start.date() == h.event_end.date():
            dates_display = h.event_end.strftime("%b %d, %Y")
        else:
            start_str = h.event_start.strftime("%b %d")
            end_str = h.event_end.strftime("%b %d, %Y")
            dates_display = f"{start_str} – {end_str}"
    elif h.event_end:
        dates_display = h.event_end.strftime("%b %d, %Y")
    else:
        dates_display = "TBA"

    # Deadline & Remaining time (clean, urgency-aware)
    if not h.has_deadline:
        deadline_display = "⏳ Apply within: <b>Open / Ongoing</b>"
    else:
        deadline_date = h.registration_deadline.strftime("%b %d, %Y")
        hours = h.hours_left()
        if hours is None or hours <= 0:
            apply_within_str = "Closed"
        elif hours < 1:
            mins = max(1, int(hours * 60))
            apply_within_str = f"Closes in {mins}m"
        elif hours < 24:
            hrs = max(1, round(hours))
            apply_within_str = f"Closes today ({hrs}h left)"
        elif h.days_left == 1:
            apply_within_str = "1 day"
        else:
            apply_within_str = f"{h.days_left} days"
        deadline_display = f"⏳ Apply within: <b>{apply_within_str}</b> ({deadline_date})"

    # Prizes & Perks: Always highlight cash rewards and valuable outcomes
    prize_esc = html.escape(format_prize_display(h.prize_pool))
    perks_clean = []
    for p in h.perks:
        p_clean = p.strip()
        if prize_esc != "Not specified" and (
            "prize" in p_clean.lower() or "₹" in p_clean or "$" in p_clean or "cash" in p_clean.lower()
        ):
            continue
        if p_clean and html.escape(p_clean) not in perks_clean:
            perks_clean.append(html.escape(p_clean))

    if prize_esc != "Not specified" and perks_clean:
        prize_perks = f"<b>{prize_esc} Cash Pool</b> • {' • '.join(perks_clean[:3])}"
    elif prize_esc != "Not specified":
        prize_perks = f"<b>{prize_esc} Cash Pool</b>"
    elif perks_clean:
        prize_perks = " • ".join(perks_clean[:3])
    else:
        prize_perks = "Participation Certificates & Goodies"

    # Accommodation: Only display if offline/hybrid and explicitly Yes or known
    accom_line = ""
    if (h.mode or "").lower() != "online":
        if h.accommodation.lower() in ("yes", "provided", "available", "free"):
            accom_line = "\n🏨 <b>Accommodation:</b> Free campus stay provided"
        elif h.food_or_travel_support and h.food_or_travel_support != "Not specified":
            accom_line = f"\n🍔 <b>Support:</b> {html.escape(h.food_or_travel_support)}"

    lines = [
        f"<b>🏆 {title_esc}</b>",
        f"🏢 <i>{org_esc}</i>",
        f"🏷 {tags_str}",
        "",
        f"📍 <b>Venue:</b> {loc_display}",
        f"📅 Dates: {dates_display}   \n{deadline_display}",
        f"🎓 <b>Eligibility:</b> {elig_esc}",
        f"🎁 <b>Prizes & Perks:</b> {prize_perks}{accom_line}",
        "",
        "💡 <b>Overview:</b>",
        f"<i>{summary_esc}</i>",
        "",
        f'👉 <a href="{url_esc}"><b>Apply Now on {platform_name} ↗</b></a>',
        "━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    return "\n".join(lines)


def format_digest(section_a: list[Hackathon], section_b: list[Hackathon]) -> list[str]:
    """Build the full Telegram HTML digest, splitting into sequential chunks under 4000 chars."""
    if not section_a and not section_b:
        return []

    now = datetime.now(IST)
    date_str = now.strftime("%A, %b %d, %Y")
    slot_str = "Morning" if now.hour < 12 else "Evening"

    header = (
        f"🚀 <b>HACKATHON ALERT DIGEST</b>\n"
        f"📅 <i>{date_str} • {slot_str} Edition</i>\n"
        f"⚡ <b>{len(section_a)}</b> in Hyderabad  •  🌟 <b>{len(section_b)}</b> Top Picks\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    blocks: list[str] = [header]

    if section_a:
        blocks.append(
            f"📍 <b>SECTION A: HYDERABAD HACKATHONS</b> ({len(section_a)} found)\n"
            f"<i>In-person & hybrid hackathons in Hyderabad, Secunderabad, and Cyberabad</i>"
        )
        for h in section_a:
            blocks.append(format_hackathon_block(h))

    if section_b:
        blocks.append(
            f"🌟 <b>SECTION B: HIGH-POPULARITY PICKS</b> ({len(section_b)} found)\n"
            f"<i>Top flagship events, premier tech brands, and high prize pools</i>"
        )
        for h in section_b:
            blocks.append(format_hackathon_block(h))

    footer = (
        "🔔 <i>Stay tuned for the next digest at 8:00 AM / 8:00 PM IST!</i>\n"
        "✨ <i>Only verified and new hackathons are delivered.</i>"
    )
    blocks.append(footer)

    # Combine blocks without splitting inside a hackathon block
    messages: list[str] = []
    current_msg = ""

    for block in blocks:
        candidate = f"{current_msg}\n\n{block}".strip() if current_msg else block
        if len(candidate) <= MAX_TELEGRAM_MSG_LEN:
            current_msg = candidate
        else:
            if current_msg:
                messages.append(current_msg)
            # If a single block somehow exceeds max length, split it cleanly by lines
            if len(block) > MAX_TELEGRAM_MSG_LEN:
                lines = block.split("\n")
                sub_msg = ""
                for line in lines:
                    if len(f"{sub_msg}\n{line}") <= MAX_TELEGRAM_MSG_LEN:
                        sub_msg = f"{sub_msg}\n{line}" if sub_msg else line
                    else:
                        messages.append(sub_msg)
                        sub_msg = line
                current_msg = sub_msg
            else:
                current_msg = block

    if current_msg:
        messages.append(current_msg)

    return messages
