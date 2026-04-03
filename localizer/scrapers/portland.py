"""Scraper for City of Portland procurement (SAP Ariba Discovery)."""

import logging
import re
from typing import Optional

from localizer.db import RFP
from localizer.scrapers.base import BaseScraper, PROCUREMENT_KEYWORDS

logger = logging.getLogger(__name__)

# Portland migrated to SAP Ariba in March 2026.
# The Ariba Discovery public buyer page lists open solicitations.
# Fallback: the portland.gov business opportunities page also links to active bids.
ARIBA_URL = "https://service.ariba.com/Discovery.aw/ad/buyer?anid=AN11181807487"
PORTLAND_BIZ_URL = "https://www.portland.gov/business-opportunities"


class PortlandScraper(BaseScraper):
    name = "portland"
    base_url = PORTLAND_BIZ_URL

    def scrape(self) -> list[RFP]:
        rfps = []

        # Strategy: scrape the portland.gov business-opportunities page which aggregates
        # links to active solicitations regardless of procurement platform.
        resp = self.fetch(PORTLAND_BIZ_URL)
        page = self.soup(resp.text)

        # Look for solicitation links in the main content area
        # Portland.gov uses Drupal; solicitation listings are typically in views or tables
        rfps.extend(self._parse_portland_gov(page, resp.text))

        # Also try Ariba Discovery page
        try:
            ariba_resp = self.fetch(ARIBA_URL)
            rfps.extend(self._parse_ariba(ariba_resp.text))
        except Exception as e:
            logger.warning(f"[portland] Ariba fetch failed (may need JS): {e}")

        return rfps

    def _parse_portland_gov(self, page, raw_html: str) -> list[RFP]:
        rfps = []

        # Look for table rows or list items containing solicitation info
        # Common patterns: tables with bid number, title, due date
        for table in page.find_all("table"):
            rows = table.find_all("tr")
            if len(rows) < 2:
                continue
            headers = [th.get_text(strip=True).lower() for th in rows[0].find_all(["th", "td"])]
            for row in rows[1:]:
                cells = row.find_all(["td", "th"])
                if len(cells) < 2:
                    continue
                data = {h: c for h, c in zip(headers, cells)}
                rfp = self._row_to_rfp(data)
                if rfp:
                    rfps.append(rfp)

        # Also look for linked items in article/content blocks
        selectors = ", ".join(
            f"a[href*='{kw}']"
            for kw in ("solicitation", "bid", "rfp", "rfq", "rfi", "proposal", "procurement")
        )
        for link in page.select(selectors):
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if title and len(title) > 5:
                rfp_id = self.make_id(href or title)
                if not href.startswith("http"):
                    href = f"https://www.portland.gov{href}"
                rfps.append(RFP(
                    id=rfp_id,
                    source=self.name,
                    title=title,
                    solicitation_type=self.detect_type(title),
                    url=href,
                ))

        return rfps

    def _parse_ariba(self, html: str) -> list[RFP]:
        rfps = []
        page = self.soup(html)

        # Ariba Discovery lists postings in a structured format
        for posting in page.select(".posting, .search-result, tr.data-row, [class*='posting']"):
            title_el = posting.select_one(
                "a, .title, [class*='title'], [class*='name']"
            )
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            href = title_el.get("href", "")
            if href and not href.startswith("http"):
                href = f"https://service.ariba.com{href}"

            rfp_id = self.make_id("ariba", href or title)
            desc = self._extract_text(posting, ".description, [class*='desc']")
            rfps.append(RFP(
                id=rfp_id,
                source=self.name,
                title=title,
                solicitation_type=self.detect_type(f"{title} {desc or ''}"),
                url=href,
                description=desc,
            ))

        return rfps

    def _row_to_rfp(self, data: dict) -> Optional[RFP]:
        """Convert a table row dict (header->cell) to an RFP."""
        title_cell = None
        for key in ("title", "solicitation", "description", "name", "project"):
            if key in data:
                title_cell = data[key]
                break
        if not title_cell:
            # Take second column as fallback
            vals = list(data.values())
            if len(vals) >= 2:
                title_cell = vals[1]
        if not title_cell:
            return None

        title = title_cell.get_text(strip=True)
        if not title or len(title) < 3:
            return None

        link = title_cell.find("a")
        url = link["href"] if link and link.get("href") else None
        if url and not url.startswith("http"):
            url = f"https://www.portland.gov{url}"

        bid_num = None
        for key in ("bid number", "number", "id", "solicitation number", "bid #"):
            if key in data:
                bid_num = data[key].get_text(strip=True)
                break

        due = None
        for key in ("due date", "closing date", "close date", "deadline", "due"):
            if key in data:
                due = self.parse_date(data[key].get_text(strip=True))
                break

        posted = None
        for key in ("posted", "post date", "publish date", "open date"):
            if key in data:
                posted = self.parse_date(data[key].get_text(strip=True))
                break

        rfp_id = self.make_id(bid_num or title)
        return RFP(
            id=rfp_id,
            source=self.name,
            title=title,
            solicitation_type=self.detect_type(title),
            url=url,
            posted_date=posted,
            due_date=due,
        )

    def _extract_text(self, el, selector: str) -> Optional[str]:
        found = el.select_one(selector)
        return found.get_text(strip=True) if found else None
