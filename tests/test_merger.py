"""Tests for the DataMerger."""

from __future__ import annotations

import pytest

from processors.data_merger import DataMerger, Restaurant, _normalise
from scrapers.google_maps import GoogleMapsRestaurant
from scrapers.tabelog import TabelogRestaurant
from scrapers.xiaohongshu import XHSNote


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _tabelog(
    name: str = "龍鳳",
    rating: float = 4.0,
    review_count: int = 200,
    area: str = "新宿",
) -> TabelogRestaurant:
    return TabelogRestaurant(
        name=name,
        tabelog_url=f"https://tabelog.com/x/{name}/",
        rating=rating,
        review_count=review_count,
        price_dinner="¥3,000～¥3,999",
        price_lunch="¥1,000～¥1,999",
        area=area,
        cuisine="中国料理",
    )


def _gm(
    name: str = "龍鳳",
    rating: float = 4.2,
    reviews: int = 300,
    lat: float = 35.69,
    lng: float = 139.70,
) -> GoogleMapsRestaurant:
    return GoogleMapsRestaurant(
        place_id="ChIJ_test",
        name=name,
        address="東京都新宿区...",
        lat=lat,
        lng=lng,
        rating=rating,
        user_ratings_total=reviews,
        price_level=2,
        opening_hours=["月曜日: 11:00-22:00"],
        website="https://example.com",
        phone="+81 3-0000-0000",
        maps_url="https://maps.google.com/...",
    )


def _xhs(
    title: str = "龍鳳太好吃了",
    desc: str = "新宿龍鳳超级好吃",
    likes: int = 500,
) -> XHSNote:
    return XHSNote(
        note_id="abc123",
        title=title,
        desc=desc,
        author="foodie",
        likes=likes,
        comments=50,
        shares=20,
        cover_url="https://example.com/img.jpg",
        note_url="https://www.xiaohongshu.com/explore/abc123",
        engagement_score=likes * 1.0 + 50 * 2.0 + 20 * 1.5,
    )


# ---------------------------------------------------------------------------
# Tests: _normalise
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw,expected", [
    ("龍鳳餐厅", "龍鳳"),
    ("龍鳳 Restaurant", "龍鳳"),
    ("龍鳳本店", "龍鳳"),
    ("  龍鳳  ", "龍鳳"),
])
def test_normalise(raw: str, expected: str):
    assert _normalise(raw) == expected


# ---------------------------------------------------------------------------
# Tests: merge
# ---------------------------------------------------------------------------


def test_merge_basic():
    merger = DataMerger()
    tabelog = [_tabelog()]
    result = merger.merge(tabelog, [], [])
    assert len(result) == 1
    assert result[0].name == "龍鳳"


def test_merge_enriches_with_google_maps():
    merger = DataMerger()
    tabelog = [_tabelog(name="龍鳳")]
    gm = [_gm(name="龍鳳", rating=4.5)]
    result = merger.merge(tabelog, gm, [])
    assert result[0].maps_rating == pytest.approx(4.5)
    assert result[0].lat != 0.0


def test_merge_attaches_xhs_notes():
    merger = DataMerger()
    tabelog = [_tabelog(name="龍鳳")]
    note = _xhs(title="龍鳳好吃", desc="龍鳳真的很不错")
    result = merger.merge(tabelog, [], [note])
    assert len(result[0].xhs_notes) == 1
    assert result[0].xhs_engagement > 0


def test_merge_gm_only_restaurant_included():
    """Restaurants only in Google Maps (not Tabelog) should still be included."""
    merger = DataMerger()
    gm = [_gm(name="唐辛子", rating=4.0)]
    result = merger.merge([], gm, [])
    assert any(r.name == "唐辛子" for r in result)


def test_merge_sorted_by_composite_score():
    merger = DataMerger()
    tabelog = [
        _tabelog(name="A店", rating=3.5),
        _tabelog(name="B店", rating=4.8),
    ]
    result = merger.merge(tabelog, [], [])
    # B店 should rank higher due to higher Tabelog rating
    assert result[0].name == "B店"
    assert result[0].composite_score >= result[1].composite_score


# ---------------------------------------------------------------------------
# Tests: _compute_score
# ---------------------------------------------------------------------------


def test_compute_score_all_zeros():
    merger = DataMerger()
    r = Restaurant(name="test")
    score = merger._compute_score(r)
    assert score == pytest.approx(0.0)


def test_compute_score_tabelog_only():
    merger = DataMerger()
    r = Restaurant(name="test", tabelog_rating=5.0)
    score = merger._compute_score(r)
    # Only tabelog signal contributes; maps and xhs are 0
    # tabelog_signal = 10.0, weight=0.4
    # total = (10.0 * 0.4) / 1.0 = 4.0
    assert score > 0.0


def test_compute_score_increases_with_higher_ratings():
    merger = DataMerger()
    r_low = Restaurant(name="low", tabelog_rating=3.0, maps_rating=3.0)
    r_high = Restaurant(name="high", tabelog_rating=5.0, maps_rating=5.0)
    assert merger._compute_score(r_high) > merger._compute_score(r_low)
