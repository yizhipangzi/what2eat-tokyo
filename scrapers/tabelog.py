"""
Tabelog scraper.

Fetches Chinese restaurant data from Tabelog's Tokyo listings using HTTP
requests and BeautifulSoup HTML parsing.

No API key is required, but Tabelog may rate-limit aggressive crawlers.
The scraper includes polite delays and retries.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

# Tabelog Chinese restaurant search in Tokyo, sorted by rating
_BASE_URL = "https://tabelog.com"
_SEARCH_URL = "https://tabelog.com/tokyo/rstLst/chinese/?Srt=D&SrtT=rt&sort_mode=1"

_HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "accept-language": "ja,zh-CN;q=0.9,zh;q=0.8,en;q=0.7",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}


@dataclass
class TabelogRestaurant:
    """A restaurant entry parsed from Tabelog."""

    name: str
    tabelog_url: str
    rating: float
    review_count: int
    price_dinner: str
    price_lunch: str
    area: str
    cuisine: str
    address: str = ""
    # will be populated by the merger from Google Maps
    lat: float = 0.0
    lng: float = 0.0


class TabelogScraper:
    """Scrape top-rated Chinese restaurants in Tokyo from Tabelog.

    Parameters
    ----------
    max_pages:
        Number of result pages to scrape (20 restaurants per page).
    min_rating:
        Only include restaurants with a Tabelog rating ≥ this value.
    """

    def __init__(
        self,
        max_pages: int = 3,
        min_rating: float = 3.0,
    ) -> None:
        self.max_pages = max_pages
        self.min_rating = min_rating
        self._session = requests.Session()
        self._session.headers.update(_HEADERS)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch(self) -> list[TabelogRestaurant]:
        """Return top-rated Chinese restaurants in Tokyo sorted by rating."""
        restaurants: list[TabelogRestaurant] = []
        for page in range(1, self.max_pages + 1):
            url = _SEARCH_URL if page == 1 else f"{_SEARCH_URL}&PG={page}"
            logger.info("Fetching Tabelog page %d: %s", page, url)
            try:
                page_restaurants = self._fetch_page(url)
            except Exception as exc:
                logger.error("Tabelog page %d failed: %s", page, exc)
                break
            restaurants.extend(page_restaurants)
            if not page_restaurants:
                break
            time.sleep(2.0)

        # Filter by minimum rating
        restaurants = [r for r in restaurants if r.rating >= self.min_rating]
        restaurants.sort(key=lambda r: r.rating, reverse=True)
        logger.info("Tabelog: collected %d restaurants (min_rating=%.1f)", len(restaurants), self.min_rating)
        return restaurants

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    def _fetch_page(self, url: str) -> list[TabelogRestaurant]:
        resp = self._session.get(url, timeout=20)
        resp.raise_for_status()
        return self._parse_listing_page(resp.text)

    def _parse_listing_page(self, html: str) -> list[TabelogRestaurant]:
        soup = BeautifulSoup(html, "lxml")
        results: list[TabelogRestaurant] = []

        # Each restaurant is an <li class="list-rst__item"> element
        items = soup.select("li.list-rst__item")
        if not items:
            # fallback selector used on some Tabelog pages
            items = soup.select("article.list-rst__item")

        for item in items:
            restaurant = self._parse_item(item)
            if restaurant:
                results.append(restaurant)

        return results

    def _parse_item(self, item: Any) -> TabelogRestaurant | None:
        try:
            name_tag = item.select_one(".list-rst__rst-name-main")
            if not name_tag:
                return None
            name = name_tag.get_text(strip=True)

            link_tag = item.select_one("a.list-rst__rst-name")
            tabelog_url = urljoin(_BASE_URL, link_tag["href"]) if link_tag else ""

            rating_tag = item.select_one(".c-rating__val")
            rating = float(rating_tag.get_text(strip=True)) if rating_tag else 0.0

            review_tag = item.select_one(".list-rst__rvw-count")
            review_text = review_tag.get_text(strip=True) if review_tag else "0"
            review_count = int("".join(filter(str.isdigit, review_text)) or "0")

            price_tags = item.select(".c-rating-v2__val")
            price_dinner = price_tags[0].get_text(strip=True) if len(price_tags) > 0 else "-"
            price_lunch = price_tags[1].get_text(strip=True) if len(price_tags) > 1 else "-"

            area_tag = item.select_one(".list-rst__area-cuisine .list-rst__area-cuisine-inner")
            area_cuisine = area_tag.get_text(strip=True) if area_tag else ""
            # Split "新宿 / 中国料理" → area="新宿", cuisine="中国料理"
            parts = [p.strip() for p in area_cuisine.split("/")]
            area = parts[0] if parts else ""
            cuisine = parts[1] if len(parts) > 1 else "中国料理"

            return TabelogRestaurant(
                name=name,
                tabelog_url=tabelog_url,
                rating=rating,
                review_count=review_count,
                price_dinner=price_dinner,
                price_lunch=price_lunch,
                area=area,
                cuisine=cuisine,
            )
        except Exception as exc:
            logger.debug("Failed to parse Tabelog item: %s", exc)
            return None
