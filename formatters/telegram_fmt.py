"""Telegram HTML digest formatter and smart block-aware message splitter."""

from __future__ import annotations
import html
import re
from datetime import datetime
from models import Hackathon, IST
from enrich import clean_eligibility, format_prize_display

MAX_TELEGRAM_MSG_LEN = 4000  # Safe threshold below 4096


def format_hackathon_block(h: Hackathon) -> str:
    """Format a single hackathon into an HTML block for Telegram."""
    title_esc = html.escape(h.title)
    org_esc = html.escape(h.organizer)
    venue_esc = html.escape(h.venue)
    elig_esc = html.escape(clean_eligibility(h.eligibility))
    accom_esc = html.escape(h.accommodation)
    summary_raw = re.sub(r"₹\s*([\d,]+)", lambda m: format_prize_display(m.group(0)), h.summary)
    summary_esc = html.escape(summary_raw)
    url_esc = html.escape(h.registration_url)

    # Fee tag
    if "free" in h.entry_fee.lower() or h.entry_fee == "0":
        fee_tag = "🆓 Free"
    else:
        fee_tag = f"💰 {html.escape(h.entry_fee)}"

    # Participation tag
    pt_clean = h.participation_type or ""
    pt_clean = re.sub(r"\b1\s+solo\b", "Solo", pt_clean, flags=re.IGNORECASE)
    pt_lower = pt_clean.lower().strip()

    if "solo only" in pt_lower or pt_lower == "solo":
        part_tag = "🧍 Solo"
    elif "team only" in pt_lower:
        part_tag = "👥 Team"
    elif re.search(r"\b1\s*[-–to]\s*\d+", pt_lower) or "team or solo" in pt_lower or ("team" in pt_lower and "solo" in pt_lower):
        part_tag = "👥 Team / 🧍 Solo"
    elif "team" in pt_lower:
        part_tag = "👥 Team"
    else:
        part_tag = "👥 Team / 🧍 Solo"

    # Tags line
    tags = [fee_tag, part_tag]
    if h.is_closing_soon:
        tags.append("🔥 Closing soon")
    tags_str = ", ".join(tags)

    # Mode and Venue
    mode_str = h.mode.capitalize()
    loc_display = f"{venue_esc} ({mode_str})" if venue_esc != "Online" else "Online"

    # Dates string (clean single-day display)
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

    # Deadline & Remaining time (cleaner and accurate when closing today, or Not specified)
    if not h.has_deadline:
        deadline_display = "⏳ Deadline: <b>Not specified</b>"
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

    # Prizes & Perks: Always show numeric prize pool first when known
    prize_esc = html.escape(format_prize_display(h.prize_pool))
    perks_clean = []
    for p in h.perks:
        p_clean = p.strip()
        # Filter out redundant prize mentions from perks list if numeric prize is already known
        if prize_esc != "Not specified" and (
            "prize" in p_clean.lower() or "₹" in p_clean or "$" in p_clean or "cash" in p_clean.lower()
        ):
            continue
        if p_clean and html.escape(p_clean) not in perks_clean:
            perks_clean.append(html.escape(p_clean))

    if prize_esc != "Not specified" and perks_clean:
        prize_perks = f"{prize_esc} • {', '.join(perks_clean[:3])}"
    elif prize_esc != "Not specified":
        prize_perks = prize_esc
    elif perks_clean:
        prize_perks = ", ".join(perks_clean[:3])
    else:
        prize_perks = "Not specified"

    lines = [
        f"<b>🏆 {title_esc}</b>  ({tags_str})",
        f"🏢 Hosted by: {org_esc}",
        f"📍 Venue: {loc_display}",
        f"📅 Dates: {dates_display}   {deadline_display}",
        f"🎓 Eligibility: {elig_esc}",
        f"🏨 Accommodation: {accom_esc}",
        f"🎁 Prize / Perks: {prize_perks}",
        f"📝 {summary_esc}",
        f'🔗 <a href="{url_esc}">Register Now</a>',
        "──────────────",
    ]
    return "\n".join(lines)


def format_digest(section_a: list[Hackathon], section_b: list[Hackathon]) -> list[str]:
    """Build the full Telegram HTML digest, splitting into sequential chunks under 4096 chars."""
    if not section_a and not section_b:
        return []

    now = datetime.now(IST)
    date_str = now.strftime("%A, %b %d, %Y")
    slot_str = "Morning" if now.hour < 12 else "Evening"

    header = (
        f"🗓 <b>Hackathon Alert</b> • <i>{date_str}</i> • <i>{slot_str} Edition</i>\n"
        f"⚡ <b>{len(section_a)}</b> in Hyderabad • <b>{len(section_b)}</b> popular picks\n"
        "══════════════════════════════"
    )

    blocks: list[str] = [header]

    if section_a:
        blocks.append(
            f"\n📍 <b>SECTION A: HYDERABAD HACKATHONS</b> ({len(section_a)} found)\n"
            f"<i>Offline & Hybrid events in Hyderabad, Secunderabad, and Cyberabad</i>\n"
        )
        for h in section_a:
            blocks.append(format_hackathon_block(h))

    if section_b:
        blocks.append(
            f"\n🌟 <b>SECTION B: HIGH-POPULARITY PICKS</b> ({len(section_b)} found)\n"
            f"<i>Top flagship events, premier tech brands, and high prize pools</i>\n"
        )
        for h in section_b:
            blocks.append(format_hackathon_block(h))

    footer = "\n🔔 <i>Stay tuned for the next digest at 7:30 AM / 6:30 PM IST!</i>"
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
