"""
Google Maps Places API integration.

Uses the ``googlemaps`` Python client to search for Chinese restaurants near
Tokyo and enrich restaurant records with ratings, review counts, and
coordinates.

Requires a Google Maps API key with the **Places API** enabled.
Set ``GOOGLE_MAPS_API_KEY`` in your ``.env`` file.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import googlemaps
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

_CHINESE_CUISINE_TYPES = ["chinese_restaurant", "restaurant"]


@dataclass
class GoogleMapsRestaurant:
    """A restaurant entry from the Google Maps Places API."""

    place_id: str
    name: str
    address: str
    lat: float
    lng: float
    rating: float          # 1–5 scale
    user_ratings_total: int
    price_level: int       # 0–4 (0=free, 4=very expensive)
    opening_hours: list[str]
    website: str
    phone: str
    maps_url: str


class GoogleMapsScraper:
    """Fetch Chinese restaurant data near Tokyo from the Google Maps Places API.

    Parameters
    ----------
    api_key:
        Google Maps API key.
    lat, lng:
        Centre of the search area (default: central Tokyo).
    radius_meters:
        Search radius in metres (default: 30,000).
    min_rating:
        Minimum Maps rating to include (1–5 scale).
    """

    def __init__(
        self,
        api_key: str,
        lat: float = 35.6895,
        lng: float = 139.6917,
        radius_meters: int = 30_000,
        min_rating: float = 3.5,
    ) -> None:
        self.lat = lat
        self.lng = lng
        self.radius_meters = radius_meters
        self.min_rating = min_rating
        if api_key:
            self._client = googlemaps.Client(key=api_key)
        else:
            self._client = None
            logger.warning("GOOGLE_MAPS_API_KEY is not set; skipping Google Maps scraping.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch(self) -> list[GoogleMapsRestaurant]:
        """Return Chinese restaurants near Tokyo sorted by rating."""
        if self._client is None:
            return []

        restaurants: list[GoogleMapsRestaurant] = []
        try:
            results = self._search_nearby()
            for result in results:
                place_id = result.get("place_id", "")
                detail = self._get_details(place_id)
                restaurant = self._parse_detail(detail or result)
                if restaurant and restaurant.rating >= self.min_rating:
                    restaurants.append(restaurant)
        except Exception as exc:
            logger.error("Google Maps fetch failed: %s", exc)

        restaurants.sort(key=lambda r: r.rating, reverse=True)
        logger.info("Google Maps: collected %d restaurants", len(restaurants))
        return restaurants

    def get_place_details(self, place_id: str) -> GoogleMapsRestaurant | None:
        """Fetch details for a single place by its ``place_id``."""
        if self._client is None:
            return None
        try:
            detail = self._get_details(place_id)
            return self._parse_detail(detail) if detail else None
        except Exception as exc:
            logger.error("Google Maps place detail failed (%s): %s", place_id, exc)
            return None

    def find_place(self, name: str, address_hint: str = "Tokyo") -> GoogleMapsRestaurant | None:
        """Find a single restaurant by name and enrich it with Maps data."""
        if self._client is None:
            return None
        try:
            result = self._client.find_place(
                input=f"{name} {address_hint}",
                input_type="textquery",
                fields=["place_id", "name", "geometry", "rating", "formatted_address"],
            )
            candidates = result.get("candidates", [])
            if not candidates:
                return None
            place_id = candidates[0]["place_id"]
            detail = self._get_details(place_id)
            return self._parse_detail(detail) if detail else None
        except Exception as exc:
            logger.debug("find_place failed for %r: %s", name, exc)
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
    def _search_nearby(self) -> list[dict]:
        """Call Places API nearby search for Chinese restaurants."""
        response = self._client.places_nearby(
            location=(self.lat, self.lng),
            radius=self.radius_meters,
            keyword="中華料理 中国料理 Chinese restaurant",
            type="restaurant",
            language="zh-CN",
        )
        results: list[dict] = response.get("results", [])
        # Follow next_page_token up to 2 extra pages (60 total)
        for _ in range(2):
            token = response.get("next_page_token")
            if not token:
                break
            import time
            time.sleep(2)  # Google requires a short delay before using the token
            response = self._client.places_nearby(page_token=token)
            results.extend(response.get("results", []))
        return results

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
    def _get_details(self, place_id: str) -> dict | None:
        """Fetch full place details for a given place_id."""
        response = self._client.place(
            place_id=place_id,
            fields=[
                "name", "place_id", "formatted_address", "geometry",
                "rating", "user_ratings_total", "price_level",
                "opening_hours", "website", "formatted_phone_number", "url",
            ],
            language="zh-CN",
        )
        return response.get("result")

    @staticmethod
    def _parse_detail(detail: dict) -> GoogleMapsRestaurant | None:
        try:
            location = detail.get("geometry", {}).get("location", {})
            hours_data = detail.get("opening_hours", {})
            weekday_text: list[str] = hours_data.get("weekday_text", []) if hours_data else []
            return GoogleMapsRestaurant(
                place_id=detail.get("place_id", ""),
                name=detail.get("name", ""),
                address=detail.get("formatted_address", ""),
                lat=float(location.get("lat", 0.0)),
                lng=float(location.get("lng", 0.0)),
                rating=float(detail.get("rating", 0.0)),
                user_ratings_total=int(detail.get("user_ratings_total", 0)),
                price_level=int(detail.get("price_level", 0)),
                opening_hours=weekday_text,
                website=detail.get("website", ""),
                phone=detail.get("formatted_phone_number", ""),
                maps_url=detail.get("url", ""),
            )
        except Exception as exc:
            logger.debug("Failed to parse Google Maps detail: %s", exc)
            return None
