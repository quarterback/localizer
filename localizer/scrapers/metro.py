"""Scraper for Oregon Metro procurement (Bid Locker)."""

import logging

from localizer.db import RFP
from localizer.scrapers.base import BaseScraper, PROCUREMENT_KEYWORDS

logger = logging.getLogger(__name__)

BIDLOCKER_URL = "https://bidlocker.us/a/oregonmetro/BidLocker"
METRO_INFO_URL = (
    "https://www.oregonmetro.gov/about-metro/doing-business-metro/"
    "current-contract-opportunities"
)


class MetroScraper(BaseScraper):
    name = "metro"
    base_url = BIDLOCKER_URL

    def scrape(self) -> list[RFP]:
        rfps = []

        # Try Bid Locker first
        try:
            resp = self.fetch(BIDLOCKER_URL)
            rfps.extend(self._parse_bidlocker(resp.text))
        except Exception as e:
            logger.warning(f"[metro] Bid Locker fetch failed (may need JS): {e}")

        # Also scrape Metro's own contract opportunities page
        try:
            resp = self.fetch(METRO_INFO_URL)
            rfps.extend(self._parse_metro_page(resp.text))
        except Exception as e:
            logger.warning(f"[metro] Metro info page fetch failed: {e}")

        return rfps

    def _parse_bidlocker(self, html: str) -> list[RFP]:
        rfps = []
        page = self.soup(html)

        # Bid Locker typically renders solicitations in a table or card list
        for table in page.find_all("table"):
            rows = table.find_all("tr")
            if len(rows) < 2:
                continue
            headers = [
                th.get_text(strip=True).lower()
                for th in rows[0].find_all(["th", "td"])
            ]
            for row in rows[1:]:
                cells = row.find_all("td")
                if len(cells) < 2:
                    continue
                data = {
                    headers[i] if i < len(headers) else f"col{i}": cell
                    for i, cell in enumerate(cells)
                }
                rfp = self._table_row_to_rfp(data)
                if rfp:
                    rfps.append(rfp)

        # Card/div based layouts
        for item in page.select(
            ".bid-item, .solicitation, [class*='bid'], [class*='solicitation']"
        ):
            title_el = item.select_one("a, .title, h3, h4")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            href = title_el.get("href", "")
            if href and not href.startswith("http"):
                href = f"https://bidlocker.us{href}"

            rfps.append(RFP(
                id=self.make_id(href or title),
                source=self.name,
                title=title,
                solicitation_type=self.detect_type(title),
                url=href or None,
            ))

        return rfps

    def _parse_metro_page(self, html: str) -> list[RFP]:
        rfps = []
        page = self.soup(html)

        # Metro's Drupal page lists opportunities with links
        content = page.select_one(".field--name-body, .node__content, main, article")
        if not content:
            content = page

        for link in content.find_all("a"):
            href = link.get("href", "")
            text = link.get_text(strip=True)
            # Filter for links that look like solicitations
            if not text or len(text) < 10:
                continue
            combined = (href + " " + text).lower()
            if any(kw in combined for kw in PROCUREMENT_KEYWORDS + ("bidlocker",)):
                if not href.startswith("http"):
                    href = f"https://www.oregonmetro.gov{href}"
                rfps.append(RFP(
                    id=self.make_id(href),
                    source=self.name,
                    title=text,
                    solicitation_type=self.detect_type(text),
                    url=href,
                ))

        return rfps

    def _table_row_to_rfp(self, data: dict) -> RFP | None:
        title = None
        url = None
        for key in ("title", "name", "solicitation", "description", "project"):
            if key in data:
                title = data[key].get_text(strip=True)
                link = data[key].find("a")
                if link and link.get("href"):
                    url = link["href"]
                    if not url.startswith("http"):
                        url = f"https://bidlocker.us{url}"
                break

        if not title:
            vals = list(data.values())
            if vals:
                title = vals[0].get_text(strip=True)
                link = vals[0].find("a")
                if link and link.get("href"):
                    url = link["href"]

        if not title or len(title) < 3:
            return None

        due = None
        for key in ("due date", "close date", "end date", "deadline"):
            if key in data:
                due = self.parse_date(data[key].get_text(strip=True))
                break

        return RFP(
            id=self.make_id(title),
            source=self.name,
            title=title,
            solicitation_type=self.detect_type(title),
            url=url,
            due_date=due,
        )
