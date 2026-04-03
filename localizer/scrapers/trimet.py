"""Scraper for TriMet procurement (JAGGAER/SciQuest)."""

import logging

from localizer.db import RFP
from localizer.scrapers.base import BaseScraper, PROCUREMENT_KEYWORDS

logger = logging.getLogger(__name__)

PUBLIC_EVENTS_URL = (
    "https://bids.sciquest.com/apps/Router/PublicEvent?CustomerOrg=TriMet"
)
TRIMET_PROCUREMENT_URL = "https://trimet.org/procurement/"


class TriMetScraper(BaseScraper):
    name = "trimet"
    base_url = PUBLIC_EVENTS_URL

    def scrape(self) -> list[RFP]:
        rfps = []

        # Primary: JAGGAER public events
        resp = self.fetch(PUBLIC_EVENTS_URL)
        rfps.extend(self._parse_jaggaer(resp.text))

        # Secondary: TriMet procurement page (may list things not in JAGGAER)
        try:
            resp = self.fetch(TRIMET_PROCUREMENT_URL)
            rfps.extend(self._parse_trimet_page(resp.text))
        except Exception as e:
            logger.warning(f"[trimet] Procurement page fetch failed: {e}")

        return rfps

    def _parse_jaggaer(self, html: str) -> list[RFP]:
        rfps = []
        page = self.soup(html)

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
                rfp = self._parse_jaggaer_row(data)
                if rfp:
                    rfps.append(rfp)

        return rfps

    def _parse_jaggaer_row(self, data: dict) -> RFP | None:
        title = None
        url = None
        for key in ("event name", "title", "solicitation", "description"):
            if key in data:
                title = data[key].get_text(strip=True)
                link = data[key].find("a")
                if link and link.get("href"):
                    url = link["href"]
                    if not url.startswith("http"):
                        url = f"https://bids.sciquest.com{url}"
                break

        if not title:
            return None

        event_id = None
        for key in ("event id", "id", "number"):
            if key in data:
                event_id = data[key].get_text(strip=True)
                break

        due_date = None
        for key in ("close date", "end date", "due date", "response deadline"):
            if key in data:
                due_date = self.parse_date(data[key].get_text(strip=True))
                break

        return RFP(
            id=self.make_id(event_id or title),
            source=self.name,
            title=title,
            solicitation_type=self.detect_type(title),
            url=url,
            due_date=due_date,
        )

    def _parse_trimet_page(self, html: str) -> list[RFP]:
        rfps = []
        page = self.soup(html)

        # TriMet's procurement page lists active solicitations
        content = page.select_one("main, .content, article, #content")
        if not content:
            content = page

        for link in content.find_all("a"):
            href = link.get("href", "")
            text = link.get_text(strip=True)
            if not text or len(text) < 10:
                continue
            combined = (text + " " + href).lower()
            if any(kw in combined for kw in PROCUREMENT_KEYWORDS + ("sciquest", "jaggaer")):
                if not href.startswith("http"):
                    href = f"https://trimet.org{href}"
                rfps.append(RFP(
                    id=self.make_id(href),
                    source=self.name,
                    title=text,
                    solicitation_type=self.detect_type(text),
                    url=href,
                ))

        return rfps
