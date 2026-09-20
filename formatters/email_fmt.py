"""Responsive HTML email digest formatter (for optional EmailNotifier add-on)."""

from __future__ import annotations
import html
from datetime import datetime
from models import Hackathon, IST
from enrich import format_prize_display


def format_email_digest(section_a: list[Hackathon], section_b: list[Hackathon]) -> str:
    """Render responsive HTML email body."""
    now = datetime.now(IST)
    date_str = now.strftime("%A, %b %d, %Y")
    slot_str = "Morning" if now.hour < 12 else "Evening"

    def render_cards(hackathons: list[Hackathon]) -> str:
        cards = []
        for h in hackathons:
            title = html.escape(h.title)
            org = html.escape(h.organizer)
            venue = html.escape(h.venue)
            summary = html.escape(h.summary)
            fee = html.escape(h.entry_fee)
            prize = html.escape(format_prize_display(h.prize_pool))
            eligibility = html.escape(h.eligibility)
            url = html.escape(h.registration_url)
            deadline = (
                h.registration_deadline.strftime("%b %d, %Y")
                if h.registration_deadline
                else "TBA"
            )

            closing_badge = (
                '<span style="background-color:#fee2e2;color:#991b1b;padding:2px 8px;border-radius:12px;font-size:12px;font-weight:bold;margin-left:8px;">🔥 Closing soon</span>'
                if h.is_closing_soon
                else ""
            )

            # Deadline string (accurate when closing today, or Not specified)
            if not h.has_deadline:
                deadline_html = "<p style=\"margin:4px 0;color:#475569;font-size:14px;\"><strong>Deadline:</strong> Not specified</p>"
            else:
                hours = h.hours_left()
                if hours is None or hours <= 0:
                    time_left_str = "Closed"
                elif hours < 1:
                    time_left_str = f"Closes in {max(1, int(hours * 60))}m"
                elif hours < 24:
                    hrs = max(1, round(hours))
                    time_left_str = f"Closes today ({hrs}h left)"
                elif h.days_left == 1:
                    time_left_str = "1 day left"
                else:
                    time_left_str = f"{h.days_left} days left"
                deadline_html = f"<p style=\"margin:4px 0;color:#475569;font-size:14px;\"><strong>Deadline:</strong> {deadline} ({time_left_str})</p>"

            card_html = f"""
            <div style="background:#ffffff;border:1px solid #e2e8f0;border-radius:8px;padding:20px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,0.05);">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                    <h3 style="margin:0;font-size:18px;color:#0f172a;">{title} {closing_badge}</h3>
                    <span style="background:#e0f2fe;color:#0369a1;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600;">{fee}</span>
                </div>
                <p style="margin:4px 0;color:#475569;font-size:14px;"><strong>Hosted by:</strong> {org}</p>
                <p style="margin:4px 0;color:#475569;font-size:14px;"><strong>Venue:</strong> {venue} ({h.mode.capitalize()})</p>
                {deadline_html}
                <p style="margin:4px 0;color:#475569;font-size:14px;"><strong>Eligibility:</strong> {eligibility}</p>
                <p style="margin:4px 0;color:#475569;font-size:14px;"><strong>Prize Pool:</strong> {prize}</p>
                <p style="margin:8px 0;color:#334155;font-size:14px;font-style:italic;">{summary}</p>
                <div style="margin-top:12px;">
                    <a href="{url}" style="background:#2563eb;color:#ffffff;text-decoration:none;padding:8px 18px;border-radius:6px;font-size:14px;font-weight:bold;display:inline-block;">Register Now &rarr;</a>
                </div>
            </div>
            """
            cards.append(card_html)
        return "\n".join(cards)

    sec_a_cards = render_cards(section_a) if section_a else "<p style='color:#64748b;'>No new Hyderabad hackathons today.</p>"
    sec_b_cards = render_cards(section_b) if section_b else "<p style='color:#64748b;'>No new popular picks today.</p>"

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hackathon Alert Digest</title>
</head>
<body style="background-color:#f8fafc;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;margin:0;padding:24px;color:#1e293b;">
    <div style="max-width:680px;margin:0 auto;">
        <div style="background:#1e293b;color:#ffffff;border-radius:12px;padding:24px;text-align:center;margin-bottom:24px;">
            <h1 style="margin:0 0 8px 0;font-size:24px;letter-spacing:-0.5px;">🗓 Hackathon Alert</h1>
            <p style="margin:0;font-size:14px;color:#94a3b8;">{date_str} • {slot_str} Edition</p>
            <p style="margin:8px 0 0 0;font-size:14px;color:#38bdf8;"><strong>{len(section_a)}</strong> in Hyderabad • <strong>{len(section_b)}</strong> Popular Picks</p>
        </div>

        <h2 style="font-size:18px;color:#0f172a;border-bottom:2px solid #e2e8f0;padding-bottom:8px;margin-top:24px;">📍 Section A: Hyderabad Hackathons</h2>
        {sec_a_cards}

        <h2 style="font-size:18px;color:#0f172a;border-bottom:2px solid #e2e8f0;padding-bottom:8px;margin-top:32px;">🌟 Section B: High-Popularity Picks</h2>
        {sec_b_cards}

        <div style="text-align:center;margin-top:36px;color:#94a3b8;font-size:12px;">
            <p>Automated digest sent by Hackathon Alert Automation.</p>
        </div>
    </div>
</body>
</html>"""
