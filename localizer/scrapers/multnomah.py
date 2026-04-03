"""Scraper for Multnomah County procurement (JAGGAER/SciQuest)."""

import logging

from localizer.db import RFP
from localizer.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# JAGGAER public events page - no login required
PUBLIC_EVENTS_URL = (
    "https://bids.sciquest.com/apps/Router/PublicEvent?CustomerOrg=Multnomah"
)


class MultnomahScraper(BaseScraper):
    name = "multnomah"
    base_url = PUBLIC_EVENTS_URL

    def scrape(self) -> list[RFP]:
        rfps = []
        resp = self.fetch(PUBLIC_EVENTS_URL)
        page = self.soup(resp.text)

        # JAGGAER public events page renders a table of open solicitations
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

                data = {}
                for i, cell in enumerate(cells):
                    key = headers[i] if i < len(headers) else f"col{i}"
                    data[key] = cell

                rfp = self._parse_row(data)
                if rfp:
                    rfps.append(rfp)

        # Also look for div-based layouts (JAGGAER sometimes uses card layouts)
        for card in page.select(".event-card, .bid-card, [class*='eventRow']"):
            rfp = self._parse_card(card)
            if rfp:
                rfps.append(rfp)

        return rfps

    def _parse_row(self, data: dict) -> RFP | None:
        title = None
        url = None
        for key in ("event name", "title", "solicitation", "description", "name"):
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
        for key in ("event id", "id", "number", "event number", "solicitation number"):
            if key in data:
                event_id = data[key].get_text(strip=True)
                break

        due_date = None
        for key in ("close date", "end date", "due date", "closing date", "response deadline"):
            if key in data:
                due_date = self.parse_date(data[key].get_text(strip=True))
                break

        posted_date = None
        for key in ("start date", "open date", "posted", "publish date"):
            if key in data:
                posted_date = self.parse_date(data[key].get_text(strip=True))
                break

        category = None
        for key in ("category", "type", "commodity", "event type"):
            if key in data:
                category = data[key].get_text(strip=True)
                break

        rfp_id = self.make_id(event_id or title)
        return RFP(
            id=rfp_id,
            source=self.name,
            title=title,
            url=url,
            posted_date=posted_date,
            due_date=due_date,
            category=category,
        )

    def _parse_card(self, card) -> RFP | None:
        title_el = card.select_one("a, .title, [class*='title'], [class*='name']")
        if not title_el:
            return None
        title = title_el.get_text(strip=True)
        if not title:
            return None

        href = title_el.get("href", "")
        if href and not href.startswith("http"):
            href = f"https://bids.sciquest.com{href}"

        rfp_id = self.make_id(href or title)
        return RFP(
            id=rfp_id,
            source=self.name,
            title=title,
            url=href or None,
        )
