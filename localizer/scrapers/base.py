"""Base scraper with shared HTTP and parsing logic."""

import hashlib
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from localizer.db import RFP, Database

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """Base class for all RFP portal scrapers."""

    name: str = "base"
    base_url: str = ""

    def __init__(self, db: Database, timeout: float = 30.0):
        self.db = db
        self.client = httpx.Client(
            timeout=timeout,
            headers={
                "User-Agent": "Localizer/0.1 (Portland RFP Monitor; civic-tech research)",
            },
            follow_redirects=True,
        )

    def make_id(self, *parts: str) -> str:
        """Create a deterministic ID from source name + unique parts."""
        raw = f"{self.name}:" + ":".join(str(p) for p in parts)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def fetch(self, url: str, **kwargs) -> httpx.Response:
        """Fetch a URL with error handling."""
        logger.debug(f"[{self.name}] GET {url}")
        resp = self.client.get(url, **kwargs)
        resp.raise_for_status()
        return resp

    def soup(self, html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "lxml")

    @abstractmethod
    def scrape(self) -> list[RFP]:
        """Scrape the portal and return a list of RFPs."""
        ...

    def run(self) -> tuple[int, int]:
        """Execute scrape and persist results. Returns (found, new)."""
        started = datetime.utcnow().isoformat()
        try:
            rfps = self.scrape()
            new_count = 0
            for rfp in rfps:
                if self.db.upsert_rfp(rfp):
                    new_count += 1
            self.db.log_scrape(
                self.name, "success", rfps_found=len(rfps),
                rfps_new=new_count, started_at=started,
            )
            logger.info(f"[{self.name}] Found {len(rfps)} RFPs, {new_count} new")
            return len(rfps), new_count
        except Exception as e:
            logger.error(f"[{self.name}] Scrape failed: {e}")
            self.db.log_scrape(self.name, "error", error=str(e), started_at=started)
            raise

    def close(self):
        self.client.close()

    def parse_date(self, text: Optional[str]) -> Optional[str]:
        """Try to parse a date string into ISO format."""
        if not text:
            return None
        text = text.strip()
        for fmt in (
            "%m/%d/%Y",
            "%m/%d/%Y %I:%M %p",
            "%m/%d/%Y %H:%M",
            "%m-%d-%Y",
            "%Y-%m-%d",
            "%B %d, %Y",
            "%b %d, %Y",
            "%m/%d/%y",
            "%m/%d/%Y %I:%M:%S %p",
        ):
            try:
                return datetime.strptime(text, fmt).date().isoformat()
            except ValueError:
                continue
        logger.debug(f"[{self.name}] Could not parse date: {text!r}")
        return text
