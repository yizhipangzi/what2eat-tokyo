"""Tests for the Tabelog scraper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from scrapers.tabelog import TabelogRestaurant, TabelogScraper


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_restaurant(
    name: str = "チャイナハウス",
    tabelog_url: str = "https://tabelog.com/tokyo/A1301/A130101/13000001/",
    rating: float = 3.8,
    review_count: int = 120,
    price_dinner: str = "¥3,000～¥3,999",
    price_lunch: str = "¥1,000～¥1,999",
    area: str = "新宿",
    cuisine: str = "中国料理",
) -> TabelogRestaurant:
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


# ---------------------------------------------------------------------------
# Minimal HTML fixtures
# ---------------------------------------------------------------------------

_LISTING_HTML = """
<html><body>
<ul>
  <li class="list-rst__item">
    <a class="list-rst__rst-name" href="/tokyo/A1301/A130101/13000001/">
      <span class="list-rst__rst-name-main">老四川</span>
    </a>
    <span class="c-rating__val">3.85</span>
    <a class="list-rst__rvw-count">(234件)</a>
    <div class="list-rst__area-cuisine">
      <span class="list-rst__area-cuisine-inner">新宿 / 中国料理</span>
    </div>
  </li>
  <li class="list-rst__item">
    <a class="list-rst__rst-name" href="/tokyo/A1301/A130101/13000002/">
      <span class="list-rst__rst-name-main">龍鳳</span>
    </a>
    <span class="c-rating__val">4.10</span>
    <a class="list-rst__rvw-count">(512件)</a>
    <div class="list-rst__area-cuisine">
      <span class="list-rst__area-cuisine-inner">渋谷 / 中国料理</span>
    </div>
  </li>
</ul>
</body></html>
"""

_EMPTY_LISTING_HTML = "<html><body><p>No results</p></body></html>"


# ---------------------------------------------------------------------------
# Tests: _parse_listing_page
# ---------------------------------------------------------------------------


def test_parse_listing_page_returns_correct_count():
    scraper = TabelogScraper()
    results = scraper._parse_listing_page(_LISTING_HTML)
    assert len(results) == 2


def test_parse_listing_page_names():
    scraper = TabelogScraper()
    results = scraper._parse_listing_page(_LISTING_HTML)
    names = {r.name for r in results}
    assert "老四川" in names
    assert "龍鳳" in names


def test_parse_listing_page_rating():
    scraper = TabelogScraper()
    results = scraper._parse_listing_page(_LISTING_HTML)
    by_name = {r.name: r for r in results}
    assert by_name["老四川"].rating == pytest.approx(3.85)
    assert by_name["龍鳳"].rating == pytest.approx(4.10)


def test_parse_listing_page_area():
    scraper = TabelogScraper()
    results = scraper._parse_listing_page(_LISTING_HTML)
    by_name = {r.name: r for r in results}
    assert by_name["老四川"].area == "新宿"
    assert by_name["龍鳳"].area == "渋谷"


def test_parse_listing_page_url():
    scraper = TabelogScraper()
    results = scraper._parse_listing_page(_LISTING_HTML)
    by_name = {r.name: r for r in results}
    assert by_name["老四川"].tabelog_url.startswith("https://tabelog.com/")


def test_parse_listing_page_empty():
    scraper = TabelogScraper()
    results = scraper._parse_listing_page(_EMPTY_LISTING_HTML)
    assert results == []


# ---------------------------------------------------------------------------
# Tests: fetch() – min_rating filter
# ---------------------------------------------------------------------------


def test_fetch_filters_by_min_rating():
    """fetch() should exclude restaurants below min_rating."""
    scraper = TabelogScraper(max_pages=1, min_rating=4.0)

    mock_resp = MagicMock()
    mock_resp.text = _LISTING_HTML
    mock_resp.raise_for_status.return_value = None

    with patch.object(scraper._session, "get", return_value=mock_resp):
        results = scraper.fetch()

    # Only 龍鳳 (4.10) should pass the 4.0 threshold
    assert all(r.rating >= 4.0 for r in results)
    assert any(r.name == "龍鳳" for r in results)
    assert all(r.name != "老四川" for r in results)


def test_fetch_sorted_descending():
    """fetch() results should be sorted by rating (highest first)."""
    scraper = TabelogScraper(max_pages=1, min_rating=0.0)

    mock_resp = MagicMock()
    mock_resp.text = _LISTING_HTML
    mock_resp.raise_for_status.return_value = None

    with patch.object(scraper._session, "get", return_value=mock_resp):
        results = scraper.fetch()

    ratings = [r.rating for r in results]
    assert ratings == sorted(ratings, reverse=True)


def test_fetch_returns_empty_on_http_error():
    """fetch() should return [] gracefully when the request fails."""
    scraper = TabelogScraper(max_pages=1)

    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = Exception("404")

    with patch.object(scraper._session, "get", return_value=mock_resp):
        results = scraper.fetch()

    assert results == []
