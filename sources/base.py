"""Base source class with retry logic, polite delays, and common session setup."""

from __future__ import annotations
from abc import ABC, abstractmethod
import logging
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from typing import Optional, Any
from models import RawHackathon

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, application/xhtml+xml, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


class BaseSource(ABC):
    """Abstract base class for all hackathon scraping/fetching sources."""

    def __init__(
        self,
        name: str,
        delay_seconds: float = 2.0,
        timeout: int = 15,
        max_retries: int = 3,
        backoff_factor: float = 2.0,
    ):
        self.name = name
        self.delay_seconds = delay_seconds
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update(DEFAULT_HEADERS)
        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=self.backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def get(self, url: str, **kwargs: Any) -> requests.Response:
        """Issue a GET request with configured timeout and polite delay."""
        time.sleep(self.delay_seconds)
        kwargs.setdefault("timeout", self.timeout)
        response = self.session.get(url, **kwargs)
        response.raise_for_status()
        return response

    def post(self, url: str, **kwargs: Any) -> requests.Response:
        """Issue a POST request with configured timeout and polite delay."""
        time.sleep(self.delay_seconds)
        kwargs.setdefault("timeout", self.timeout)
        response = self.session.post(url, **kwargs)
        response.raise_for_status()
        return response

    @abstractmethod
    def fetch(self) -> list[RawHackathon]:
        """Fetch hackathons from the source and return list of RawHackathon."""
        pass

    def safe_fetch(self) -> list[RawHackathon]:
        """Execute fetch wrapped in try/except so one source failure never halts the process."""
        try:
            logger.info("Starting fetch for source: %s", self.name)
            results = self.fetch()
            logger.info("Successfully fetched %d items from %s", len(results), self.name)
            return results
        except Exception as exc:
            logger.error("Error fetching from source %s: %s", self.name, exc, exc_info=True)
            return []
