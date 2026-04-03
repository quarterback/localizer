"""Scraper registry for Portland-area government RFP portals."""

from localizer.scrapers.base import BaseScraper
from localizer.scrapers.portland import PortlandScraper
from localizer.scrapers.multnomah import MultnomahScraper
from localizer.scrapers.metro import MetroScraper
from localizer.scrapers.trimet import TriMetScraper
from localizer.scrapers.port_of_portland import PortOfPortlandScraper
from localizer.scrapers.oregon_buys import OregonBuysScraper

SCRAPERS: dict[str, type[BaseScraper]] = {
    "portland": PortlandScraper,
    "multnomah": MultnomahScraper,
    "metro": MetroScraper,
    "trimet": TriMetScraper,
    "port": PortOfPortlandScraper,
    "oregonbuys": OregonBuysScraper,
}

__all__ = ["SCRAPERS", "BaseScraper"]
