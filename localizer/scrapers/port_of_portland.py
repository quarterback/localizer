"""Scraper for Port of Portland procurement (PlanetBids)."""

import logging

from localizer.db import RFP
from localizer.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

PLANETBIDS_URL = "https://vendors.planetbids.com/portal/15598/bo/bo-search"
PORT_INFO_URL = "https://www.portofportland.com/business/Vendors"


class PortOfPortlandScraper(BaseScraper):
    name = "port"
    base_url = PLANETBIDS_URL

    def scrape(self) -> list[RFP]:
        rfps = []

        # PlanetBids portal - may render via JS, try static first
        try:
            resp = self.fetch(PLANETBIDS_URL)
            rfps.extend(self._parse_planetbids(resp.text))
        except Exception as e:
            logger.warning(f"[port] PlanetBids fetch failed (may need JS): {e}")

        # Also try the Port of Portland vendor page
        try:
            resp = self.fetch(PORT_INFO_URL)
            rfps.extend(self._parse_port_page(resp.text))
        except Exception as e:
            logger.warning(f"[port] Port info page fetch failed: {e}")

        return rfps

    def _parse_planetbids(self, html: str) -> list[RFP]:
        rfps = []
        page = self.soup(html)

        # PlanetBids renders bid opportunities in tables or card lists
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
                rfp = self._parse_bid_row(data)
                if rfp:
                    rfps.append(rfp)

        # Card/list based layouts
        for item in page.select(
            ".bid-opportunity, [class*='opportunity'], [class*='bid-item']"
        ):
            title_el = item.select_one("a, .title, h3, h4, [class*='title']")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not title:
                continue
            href = title_el.get("href", "")
            if href and not href.startswith("http"):
                href = f"https://vendors.planetbids.com{href}"

            rfps.append(RFP(
                id=self.make_id(href or title),
                source=self.name,
                title=title,
                url=href or None,
            ))

        return rfps

    def _parse_port_page(self, html: str) -> list[RFP]:
        rfps = []
        page = self.soup(html)

        content = page.select_one("main, .content, article")
        if not content:
            content = page

        for link in content.find_all("a"):
            href = link.get("href", "")
            text = link.get_text(strip=True)
            if not text or len(text) < 10:
                continue
            if any(kw in text.lower() or kw in href.lower() for kw in (
                "rfp", "rfq", "bid", "solicitation", "proposal",
                "planetbids", "procurement",
            )):
                if not href.startswith("http"):
                    href = f"https://www.portofportland.com{href}"
                rfps.append(RFP(
                    id=self.make_id(href),
                    source=self.name,
                    title=text,
                    url=href,
                ))

        return rfps

    def _parse_bid_row(self, data: dict) -> RFP | None:
        title = None
        url = None
        for key in ("title", "name", "bid title", "description", "opportunity"):
            if key in data:
                title = data[key].get_text(strip=True)
                link = data[key].find("a")
                if link and link.get("href"):
                    url = link["href"]
                    if not url.startswith("http"):
                        url = f"https://vendors.planetbids.com{url}"
                break

        if not title:
            return None

        bid_num = None
        for key in ("bid number", "number", "id", "bid #"):
            if key in data:
                bid_num = data[key].get_text(strip=True)
                break

        due = None
        for key in ("due date", "close date", "end date", "deadline"):
            if key in data:
                due = self.parse_date(data[key].get_text(strip=True))
                break

        return RFP(
            id=self.make_id(bid_num or title),
            source=self.name,
            title=title,
            url=url,
            due_date=due,
        )
