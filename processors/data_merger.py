"""
Data merger.

Combines restaurant data from Xiaohongshu, Tabelog, and Google Maps into a
unified list of :class:`Restaurant` records that the recommender can rank.

Matching strategy
-----------------
1. Build a candidate set from Tabelog restaurants (most structured data).
2. For each Tabelog restaurant, try to find a matching Google Maps record by
   name similarity and enrich it with Maps data (coords, Maps rating).
3. Attach any Xiaohongshu notes that mention the restaurant name.
4. Score each restaurant using a weighted composite formula.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scrapers.google_maps import GoogleMapsRestaurant
    from scrapers.tabelog import TabelogRestaurant
    from scrapers.xiaohongshu import XHSNote

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Unified data model
# ---------------------------------------------------------------------------


@dataclass
class Restaurant:
    """A restaurant enriched with data from all three sources."""

    # Identity
    name: str
    area: str = ""
    address: str = ""
    lat: float = 0.0
    lng: float = 0.0

    # Tabelog
    tabelog_url: str = ""
    tabelog_rating: float = 0.0
    tabelog_reviews: int = 0
    price_dinner: str = ""
    price_lunch: str = ""

    # Google Maps
    maps_url: str = ""
    maps_rating: float = 0.0
    maps_reviews: int = 0
    maps_price_level: int = 0
    opening_hours: list[str] = field(default_factory=list)
    website: str = ""
    phone: str = ""

    # Xiaohongshu
    xhs_notes: list[dict] = field(default_factory=list)
    xhs_engagement: float = 0.0

    # Composite
    composite_score: float = 0.0


# ---------------------------------------------------------------------------
# Merger
# ---------------------------------------------------------------------------


class DataMerger:
    """Merge data from all three sources into a ranked list of restaurants.

    Parameters
    ----------
    google_maps_scraper:
        An already-instantiated :class:`~scrapers.google_maps.GoogleMapsScraper`
        used to look up Maps data for Tabelog restaurants.
    tabelog_weight, maps_weight, xhs_weight:
        Weights for the three signal sources when computing ``composite_score``.
    """

    def __init__(
        self,
        google_maps_scraper=None,
        *,
        tabelog_weight: float = 0.4,
        maps_weight: float = 0.35,
        xhs_weight: float = 0.25,
    ) -> None:
        self._gm = google_maps_scraper
        self._tabelog_w = tabelog_weight
        self._maps_w = maps_weight
        self._xhs_w = xhs_weight

    def merge(
        self,
        tabelog_restaurants: list[TabelogRestaurant],
        google_maps_restaurants: list[GoogleMapsRestaurant],
        xhs_notes: list[XHSNote],
    ) -> list[Restaurant]:
        """Merge all three data sources and return restaurants sorted by composite score."""
        # Index Google Maps results by normalised name for fast lookup
        gm_index = self._build_gm_index(google_maps_restaurants)

        merged: list[Restaurant] = []
        for tr in tabelog_restaurants:
            restaurant = Restaurant(
                name=tr.name,
                area=tr.area,
                tabelog_url=tr.tabelog_url,
                tabelog_rating=tr.rating,
                tabelog_reviews=tr.review_count,
                price_dinner=tr.price_dinner,
                price_lunch=tr.price_lunch,
            )

            # Enrich with Google Maps data
            gm = self._find_gm_match(tr.name, tr.area, gm_index)
            if gm is None and self._gm is not None:
                gm = self._gm.find_place(tr.name, tr.area or "Tokyo")
            if gm:
                restaurant.address = gm.address
                restaurant.lat = gm.lat
                restaurant.lng = gm.lng
                restaurant.maps_url = gm.maps_url
                restaurant.maps_rating = gm.rating
                restaurant.maps_reviews = gm.user_ratings_total
                restaurant.maps_price_level = gm.price_level
                restaurant.opening_hours = gm.opening_hours
                restaurant.website = gm.website
                restaurant.phone = gm.phone

            # Attach matching XHS notes
            matching_notes = self._find_xhs_notes(tr.name, xhs_notes)
            restaurant.xhs_notes = [
                {
                    "title": n.title,
                    "author": n.author,
                    "likes": n.likes,
                    "url": n.note_url,
                }
                for n in matching_notes
            ]
            restaurant.xhs_engagement = sum(n.engagement_score for n in matching_notes)

            restaurant.composite_score = self._compute_score(restaurant)
            merged.append(restaurant)

        # Also include Google Maps restaurants not in Tabelog
        tabelog_names_norm = {_normalise(r.name) for r in tabelog_restaurants}
        for gm in google_maps_restaurants:
            if _normalise(gm.name) not in tabelog_names_norm:
                restaurant = Restaurant(
                    name=gm.name,
                    address=gm.address,
                    lat=gm.lat,
                    lng=gm.lng,
                    maps_url=gm.maps_url,
                    maps_rating=gm.rating,
                    maps_reviews=gm.user_ratings_total,
                    maps_price_level=gm.price_level,
                    opening_hours=gm.opening_hours,
                    website=gm.website,
                    phone=gm.phone,
                )
                matching_notes = self._find_xhs_notes(gm.name, xhs_notes)
                restaurant.xhs_notes = [
                    {"title": n.title, "author": n.author, "likes": n.likes, "url": n.note_url}
                    for n in matching_notes
                ]
                restaurant.xhs_engagement = sum(n.engagement_score for n in matching_notes)
                restaurant.composite_score = self._compute_score(restaurant)
                merged.append(restaurant)

        merged.sort(key=lambda r: r.composite_score, reverse=True)
        logger.info("DataMerger: %d restaurants after merge", len(merged))
        return merged

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def _compute_score(self, r: Restaurant) -> float:
        """Compute a composite 0–10 score from all three signals."""
        # Tabelog signal: rating on 1–5 scale → normalise to 0–10
        tabelog_signal = (r.tabelog_rating / 5.0) * 10.0 if r.tabelog_rating else 0.0

        # Google Maps signal: rating on 1–5 scale → normalise to 0–10,
        # weighted slightly by review count (log-damped)
        import math
        if r.maps_rating:
            maps_signal = (r.maps_rating / 5.0) * 10.0
            if r.maps_reviews > 0:
                maps_signal *= min(1.0, math.log10(r.maps_reviews + 1) / 3.0) + 0.5
        else:
            maps_signal = 0.0

        # XHS signal: engagement score capped and normalised to 0–10
        xhs_signal = min(r.xhs_engagement / 500.0, 1.0) * 10.0 if r.xhs_engagement else 0.0

        # Weighted sum
        total_weight = self._tabelog_w + self._maps_w + self._xhs_w
        score = (
            tabelog_signal * self._tabelog_w
            + maps_signal * self._maps_w
            + xhs_signal * self._xhs_w
        ) / total_weight
        return round(score, 3)

    # ------------------------------------------------------------------
    # Matching helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_gm_index(gm_restaurants: list[GoogleMapsRestaurant]) -> dict[str, GoogleMapsRestaurant]:
        return {_normalise(r.name): r for r in gm_restaurants}

    @staticmethod
    def _find_gm_match(
        name: str,
        area: str,
        gm_index: dict[str, GoogleMapsRestaurant],
    ) -> GoogleMapsRestaurant | None:
        """Try exact and prefix-based name matching against the GM index."""
        norm = _normalise(name)
        if norm in gm_index:
            return gm_index[norm]
        # Try if norm is a sub-string of any indexed key or vice-versa
        for key, val in gm_index.items():
            if norm in key or key in norm:
                return val
        return None

    @staticmethod
    def _find_xhs_notes(name: str, notes: list[XHSNote]) -> list[XHSNote]:
        """Return notes that mention the restaurant name."""
        norm = _normalise(name)
        return [
            n for n in notes
            if norm in _normalise(n.title) or norm in _normalise(n.desc)
        ]


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _normalise(text: str) -> str:
    """Lower-case, strip whitespace and common restaurant suffixes."""
    text = text.lower().strip()
    # Remove common Japanese/Chinese restaurant suffixes that vary between sources
    text = re.sub(r"(餐厅|餐廳|restaurant|レストラン|本店|支店|\s+)", "", text)
    return text
