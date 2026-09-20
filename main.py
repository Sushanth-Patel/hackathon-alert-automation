"""Hackathon Alert Automation Orchestrator.

Twice a day (7:30 AM IST and 6:30 PM IST), fetches new hackathons from
Unstop, Devfolio, Devpost, MLH, and HackerEarth, enriches with Gemini / regex fallback,
ranks for B.Tech students (prioritizing Hyderabad and high-popularity events),
deduplicates in SQLite, and dispatches an HTML digest to Telegram.
"""

from __future__ import annotations
import argparse
import logging
import sys
import time
from pathlib import Path
import yaml
from dotenv import load_dotenv

# Load environment variables from local .env if present
load_dotenv()
from storage import Storage
from enrich import HackathonEnricher
from ranker import Ranker
from formatters.telegram_fmt import format_digest
from formatters.email_fmt import format_email_digest
from notifiers.telegram import TelegramNotifier
from notifiers.email_smtp import EmailNotifier
from sources.unstop import UnstopSource
from sources.devfolio import DevfolioSource
from sources.devpost import DevpostSource
from sources.hackerearth import HackerEarthSource
from sources.mlh import MLHSource

# Configure UTF-8 for console output (prevents Windows charmap codec errors)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("hackathon_alert")


def load_config(config_path: Path | str = "config.yaml") -> dict:
    """Load YAML configuration."""
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_active_sources(config: dict, filter_source: str | None = None) -> list:
    """Instantiate enabled scraping sources."""
    cfg_sources = config.get("sources", {})
    scraping_cfg = config.get("scraping", {})
    delay = scraping_cfg.get("request_delay_seconds", 2.0)
    timeout = scraping_cfg.get("timeout_seconds", 15)
    max_retries = scraping_cfg.get("max_retries", 3)

    source_map = {
        "unstop": UnstopSource,
        "devfolio": DevfolioSource,
        "devpost": DevpostSource,
        "hackerearth": HackerEarthSource,
        "mlh": MLHSource,
    }

    active = []
    for name, cls in source_map.items():
        if filter_source:
            if name.lower() == filter_source.lower():
                active.append(cls(delay_seconds=delay, timeout=timeout, max_retries=max_retries))
        elif cfg_sources.get(name, True):
            active.append(cls(delay_seconds=delay, timeout=timeout, max_retries=max_retries))

    return active


def main():
    parser = argparse.ArgumentParser(description="Hackathon Alert Automation")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the exact Telegram digest to console instead of sending.",
    )
    parser.add_argument(
        "--force-resend",
        action="store_true",
        help="Ignore deduplication and process all hackathons as new.",
    )
    parser.add_argument(
        "--source",
        type=str,
        default=None,
        help="Run only a specific source (e.g. unstop, devfolio, devpost, hackerearth, mlh).",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="Path to config.yaml",
    )
    args = parser.parse_args()
    start_time = time.time()

    # 1. Load environment and config
    load_dotenv()
    config = load_config(args.config)
    reputed_orgs = config.get("reputed_organizers", [])

    # 2. Storage & pruning
    storage = Storage("hackathons.db")
    storage.prune_expired(days=90)

    # 3. Sources fetching
    sources = get_active_sources(config, filter_source=args.source)
    if not sources:
        logger.warning("No active sources configured or matched.")
        return

    logger.info("Fetching hackathons from %d sources...", len(sources))
    raw_hackathons: list[RawHackathon] = []
    for src in sources:
        items = src.safe_fetch()
        raw_hackathons.extend(items)

    logger.info("Total raw hackathons collected: %d", len(raw_hackathons))

    # 4. Deduplication & filtering
    candidates_to_enrich: list[tuple[RawHackathon, bool]] = []
    for raw in raw_hackathons:
        item_id = f"{raw.source}_{raw.source_id}"

        if args.force_resend:
            candidates_to_enrich.append((raw, False))
            continue

        if not storage.is_already_sent(item_id):
            candidates_to_enrich.append((raw, False))
        elif storage.should_send_last_call(item_id, raw.registration_deadline):
            logger.info("Re-alerting last call for closing-soon hackathon: %s", raw.title)
            candidates_to_enrich.append((raw, True))

    if not candidates_to_enrich:
        logger.info("Zero new hackathons found and no closing-soon re-alerts. Exiting cleanly.")
        return

    logger.info("Found %d hackathon candidates for enrichment and ranking.", len(candidates_to_enrich))

    # 5. Fast Rule-Based Screening (Stage 1)
    logger.info("Screening %d candidates with fast rule-based extraction...", len(candidates_to_enrich))
    enricher = HackathonEnricher(storage=storage)
    fast_hackathons: list[Hackathon] = []
    last_call_flags: dict[str, bool] = {}

    for raw, is_last_call in candidates_to_enrich:
        h = enricher.enrich(raw, reputed_organizers=reputed_orgs, allow_gemini=False)
        if is_last_call:
            h.is_closing_soon = True
        last_call_flags[h.id] = is_last_call
        fast_hackathons.append(h)

    # 6. Preliminary Ranking & Section Partitioning
    ranker = Ranker(config)
    section_a, section_b = ranker.rank_and_partition(fast_hackathons)

    logger.info(
        "Screened candidates partitioned: %d in Section A (Hyderabad), %d in Section B (High-Popularity)",
        len(section_a),
        len(section_b),
    )

    if not section_a and not section_b:
        logger.info("All candidates were filtered out (e.g. expired). Nothing to send.")
        return

    # 7. Finalist AI Enrichment (Stage 2: Gemini called ONLY on digest finalists)
    finalists = section_a + section_b
    logger.info("Enriching %d digest finalists with Gemini AI / Cache...", len(finalists))
    enriched_finalists: dict[str, Hackathon] = {}
    for h in finalists:
        raw = getattr(h, "raw_ref", None)
        if raw is not None:
            enriched_h = enricher.enrich(raw, reputed_organizers=reputed_orgs, allow_gemini=True)
            if last_call_flags.get(h.id):
                enriched_h.is_closing_soon = True
            enriched_finalists[h.id] = enriched_h
        else:
            enriched_finalists[h.id] = h

    # Replace finalists in sections and re-sort
    section_a = [enriched_finalists.get(h.id, h) for h in section_a]
    section_b = [enriched_finalists.get(h.id, h) for h in section_b]
    for h in section_a + section_b:
        ranker.calculate_score(h)
    section_a = ranker.sort_section_events(section_a)
    section_b = ranker.sort_section_events(section_b)

    # 7. Formatting
    telegram_chunks = format_digest(section_a, section_b)

    # 8. Dispatch or Dry-Run
    if args.dry_run:
        print("\n" + "=" * 60)
        print("          DRY RUN: RENDERED TELEGRAM DIGEST OUTPUT")
        print("=" * 60)
        for i, chunk in enumerate(telegram_chunks, 1):
            print(f"\n--- [MESSAGE CHUNK {i}/{len(telegram_chunks)}] ({len(chunk)} chars) ---\n")
            print(chunk)
        print("\n" + "=" * 60)
        print("                 END OF DRY RUN OUTPUT")
        print("=" * 60 + "\n")
        total_time = time.time() - start_time
        logger.info(
            "Dry run complete in %.2fs. Gemini calls made: %d (rate-limit wait: %.1fs).",
            total_time,
            enricher.gemini_call_count,
            enricher.total_wait_time,
        )
        return

    # Real sending
    notif_cfg = config.get("notifiers", {})
    tg_enabled = notif_cfg.get("telegram", {}).get("enabled", True)
    telegram_notifier = TelegramNotifier(enabled=tg_enabled)
    sent_ok = telegram_notifier.send(telegram_chunks)

    # Optional Email Add-on
    email_enabled = notif_cfg.get("email", {}).get("enabled", False)
    if email_enabled:
        email_notifier = EmailNotifier(enabled=True)
        email_html = format_email_digest(section_a, section_b)
        email_notifier.send(email_html)

    # 9. Mark sent in SQLite upon successful dispatch
    if sent_ok:
        all_sent = section_a + section_b
        for h in all_sent:
            is_last_call = last_call_flags.get(h.id, False)
            storage.mark_sent(h, is_last_call=is_last_call)
        logger.info("Successfully recorded %d sent hackathons in SQLite.", len(all_sent))
    else:
        logger.error("Notification delivery encountered errors. Sent flags not updated.")


if __name__ == "__main__":
    main()
