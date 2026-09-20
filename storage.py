"""SQLite storage and deduplication manager for Hackathon Alert Automation."""

from __future__ import annotations
import sqlite3
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Any
from pathlib import Path
from contextlib import closing
from models import Hackathon, IST

logger = logging.getLogger(__name__)

DB_PATH_DEFAULT = Path("hackathons.db")


class Storage:
    """Manages SQLite storage for sent alerts, enrichment cache, and deduplication."""

    def __init__(self, db_path: Path | str = DB_PATH_DEFAULT):
        self.db_path = Path(db_path)
        self._init_db()

    def _init_db(self) -> None:
        """Create required tables if they don't exist."""
        with closing(sqlite3.connect(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS sent_hackathons (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    source TEXT NOT NULL,
                    first_sent_at TEXT NOT NULL,
                    last_sent_at TEXT NOT NULL,
                    deadline TEXT,
                    last_call_sent INTEGER DEFAULT 0
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS enrichment_cache (
                    id TEXT PRIMARY KEY,
                    cached_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def is_already_sent(self, hackathon_id: str) -> bool:
        """Check if an alert for this hackathon has ever been sent."""
        with closing(sqlite3.connect(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM sent_hackathons WHERE id = ?", (hackathon_id,))
            return cursor.fetchone() is not None

    def should_send_last_call(self, hackathon_id: str, deadline: Optional[datetime]) -> bool:
        """Check if a previously sent hackathon is eligible for a one-time 'Last call' alert (<= 48h left)."""
        if not deadline:
            return False

        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT last_call_sent FROM sent_hackathons WHERE id = ?",
                (hackathon_id,),
            )
            row = cursor.fetchone()
            if not row:
                # Never sent before; will be sent as a normal new hackathon
                return False
            last_call_sent = bool(row["last_call_sent"])
            if last_call_sent:
                return False

        # Check if deadline is within 0 to 48 hours
        now = datetime.now(IST)
        dl = deadline.astimezone(IST) if deadline.tzinfo else deadline.replace(tzinfo=IST)
        hours_left = (dl - now).total_seconds() / 3600.0
        return 0 < hours_left <= 48.0

    def mark_sent(
        self,
        hackathon: Hackathon,
        is_last_call: bool = False,
    ) -> None:
        """Record that a hackathon alert was sent to the user."""
        now_str = datetime.now(IST).isoformat()
        deadline_str = hackathon.registration_deadline.isoformat() if hackathon.registration_deadline else None

        with closing(sqlite3.connect(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO sent_hackathons (id, title, source, first_sent_at, last_sent_at, deadline, last_call_sent)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    last_sent_at = excluded.last_sent_at,
                    deadline = excluded.deadline,
                    last_call_sent = CASE WHEN ? = 1 THEN 1 ELSE last_call_sent END
                """,
                (
                    hackathon.id,
                    hackathon.title,
                    hackathon.source,
                    now_str,
                    now_str,
                    deadline_str,
                    1 if is_last_call else 0,
                    1 if is_last_call else 0,
                ),
            )
            conn.commit()

    def get_cached_enrichment(self, hackathon_id: str) -> Optional[dict[str, Any]]:
        """Retrieve cached enrichment payload for a hackathon ID."""
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT payload_json FROM enrichment_cache WHERE id = ?", (hackathon_id,))
            row = cursor.fetchone()
            if row:
                try:
                    return json.loads(row["payload_json"])
                except Exception:
                    return None
            return None

    def cache_enrichment(self, hackathon_id: str, payload: dict[str, Any]) -> None:
        """Store enrichment payload in cache."""
        now_str = datetime.now(IST).isoformat()
        with closing(sqlite3.connect(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO enrichment_cache (id, cached_at, payload_json)
                VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    cached_at = excluded.cached_at,
                    payload_json = excluded.payload_json
                """,
                (hackathon_id, now_str, json.dumps(payload)),
            )
            conn.commit()

    def prune_expired(self, days: int = 90) -> int:
        """Prune sent hackathons whose registration deadline is older than `days`."""
        cutoff = (datetime.now(IST) - timedelta(days=days)).isoformat()
        with closing(sqlite3.connect(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM sent_hackathons WHERE deadline IS NOT NULL AND deadline < ?",
                (cutoff,),
            )
            deleted = cursor.rowcount
            conn.commit()
            if deleted > 0:
                logger.info("Pruned %d expired hackathon records (> %d days old)", deleted, days)
            return deleted
