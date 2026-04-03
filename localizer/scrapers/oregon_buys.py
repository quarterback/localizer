"""Scraper for OregonBuys (state procurement portal)."""

import logging

from localizer.db import RFP
from localizer.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

OREGON_BUYS_URL = (
    "https://oregonbuys.gov/bso/view/search/external/advancedSearchBid.xhtml"
    "?openBids=true"
)


class OregonBuysScraper(BaseScraper):
    name = "oregonbuys"
    base_url = OREGON_BUYS_URL

    def scrape(self) -> list[RFP]:
        rfps = []
        resp = self.fetch(OREGON_BUYS_URL)
        page = self.soup(resp.text)

        # OregonBuys uses a BuySpeed-derived interface with tables of open bids
        for table in page.find_all("table"):
            rows = table.find_all("tr")
            if len(rows) < 2:
                continue

            headers = [
                th.get_text(strip=True).lower()
                for th in rows[0].find_all(["th", "td"])
            ]

            # Skip tables that don't look like bid listings
            if not any(kw in " ".join(headers) for kw in (
                "title", "solicitation", "bid", "description", "name", "number",
            )):
                continue

            for row in rows[1:]:
                cells = row.find_all("td")
                if len(cells) < 2:
                    continue
                data = {
                    headers[i] if i < len(headers) else f"col{i}": cell
                    for i, cell in enumerate(cells)
                }
                rfp = self._parse_row(data)
                if rfp:
                    rfps.append(rfp)

        # Also look for links in the page that point to bid details
        for link in page.select("a[href*='bidDetail'], a[href*='BidDetail']"):
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if title and len(title) > 5:
                if not href.startswith("http"):
                    href = f"https://oregonbuys.gov{href}"
                rfps.append(RFP(
                    id=self.make_id(href),
                    source=self.name,
                    title=title,
                    url=href,
                ))

        return rfps

    def _parse_row(self, data: dict) -> RFP | None:
        title = None
        url = None
        for key in ("title", "solicitation title", "bid title", "description", "name"):
            if key in data:
                title = data[key].get_text(strip=True)
                link = data[key].find("a")
                if link and link.get("href"):
                    url = link["href"]
                    if not url.startswith("http"):
                        url = f"https://oregonbuys.gov{url}"
                break

        if not title:
            return None

        sol_num = None
        for key in ("solicitation number", "bid number", "number", "id", "solicitation #"):
            if key in data:
                sol_num = data[key].get_text(strip=True)
                break

        due = None
        for key in ("due date", "close date", "closing date", "end date", "bid opening"):
            if key in data:
                due = self.parse_date(data[key].get_text(strip=True))
                break

        posted = None
        for key in ("posted date", "publish date", "open date", "start date"):
            if key in data:
                posted = self.parse_date(data[key].get_text(strip=True))
                break

        category = None
        for key in ("category", "type", "commodity", "class"):
            if key in data:
                category = data[key].get_text(strip=True)
                break

        agency = None
        for key in ("agency", "department", "organization", "buyer"):
            if key in data:
                agency = data[key].get_text(strip=True)
                break

        rfp_id = self.make_id(sol_num or title)
        return RFP(
            id=rfp_id,
            source=self.name,
            title=f"{agency}: {title}" if agency else title,
            url=url,
            posted_date=posted,
            due_date=due,
            category=category,
        )
