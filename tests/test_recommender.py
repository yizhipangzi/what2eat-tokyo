"""Tests for the daily recommender."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from processors.data_merger import Restaurant
from recommender.daily_recommender import DailyRecommender


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_restaurant(
    name: str,
    score: float = 5.0,
    tabelog_rating: float = 3.5,
    maps_rating: float = 4.0,
    area: str = "新宿",
) -> Restaurant:
    r = Restaurant(
        name=name,
        area=area,
        tabelog_rating=tabelog_rating,
        maps_rating=maps_rating,
    )
    r.composite_score = score
    return r


def _ranked_restaurants(n: int = 10) -> list[Restaurant]:
    return [
        _make_restaurant(f"Restaurant_{i}", score=float(10 - i))
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Tests: _select_picks
# ---------------------------------------------------------------------------


def test_select_picks_returns_top_n(tmp_path):
    rec = DailyRecommender(output_dir=str(tmp_path), top_n=3)
    restaurants = _ranked_restaurants(10)
    picks = rec._select_picks(restaurants, date(2024, 4, 1))
    assert len(picks) == 3


def test_select_picks_fewer_than_top_n(tmp_path):
    rec = DailyRecommender(output_dir=str(tmp_path), top_n=5)
    restaurants = _ranked_restaurants(2)
    picks = rec._select_picks(restaurants, date(2024, 4, 1))
    assert len(picks) == 2


def test_select_picks_rotates_by_day(tmp_path):
    """Different days should potentially produce different orderings."""
    rec = DailyRecommender(output_dir=str(tmp_path), top_n=3)
    restaurants = _ranked_restaurants(10)
    picks_day1 = rec._select_picks(restaurants, date(2024, 4, 1))
    picks_day2 = rec._select_picks(restaurants, date(2024, 4, 2))
    # At least the first pick should differ on consecutive days
    # (true as long as list length > top_n, which it is here)
    assert picks_day1[0].name != picks_day2[0].name


def test_select_picks_empty_list(tmp_path):
    rec = DailyRecommender(output_dir=str(tmp_path), top_n=5)
    picks = rec._select_picks([], date(2024, 4, 1))
    assert picks == []


# ---------------------------------------------------------------------------
# Tests: recommend() – output files
# ---------------------------------------------------------------------------


def test_recommend_creates_json_file(tmp_path):
    rec = DailyRecommender(output_dir=str(tmp_path), top_n=3)
    restaurants = _ranked_restaurants(5)
    target_date = date(2024, 4, 16)
    rec.recommend(restaurants, today=target_date)

    json_file = tmp_path / "recommendations_2024-04-16.json"
    assert json_file.exists()


def test_recommend_creates_markdown_file(tmp_path):
    rec = DailyRecommender(output_dir=str(tmp_path), top_n=3)
    restaurants = _ranked_restaurants(5)
    target_date = date(2024, 4, 16)
    rec.recommend(restaurants, today=target_date)

    md_file = tmp_path / "recommendations_2024-04-16.md"
    assert md_file.exists()


def test_recommend_json_structure(tmp_path):
    rec = DailyRecommender(output_dir=str(tmp_path), top_n=3)
    restaurants = _ranked_restaurants(5)
    target_date = date(2024, 4, 16)
    rec.recommend(restaurants, today=target_date)

    json_file = tmp_path / "recommendations_2024-04-16.json"
    data = json.loads(json_file.read_text(encoding="utf-8"))
    assert data["date"] == "2024-04-16"
    assert "recommendations" in data
    assert len(data["recommendations"]) == 3
    assert "name" in data["recommendations"][0]


def test_recommend_returns_picks(tmp_path):
    rec = DailyRecommender(output_dir=str(tmp_path), top_n=3)
    restaurants = _ranked_restaurants(5)
    target_date = date(2024, 4, 16)
    picks = rec.recommend(restaurants, today=target_date)
    assert len(picks) == 3
    assert all(isinstance(p, Restaurant) for p in picks)


def test_recommend_markdown_contains_restaurant_names(tmp_path):
    rec = DailyRecommender(output_dir=str(tmp_path), top_n=3)
    restaurants = _ranked_restaurants(5)
    target_date = date(2024, 4, 16)
    picks = rec.recommend(restaurants, today=target_date)

    md_file = tmp_path / "recommendations_2024-04-16.md"
    content = md_file.read_text(encoding="utf-8")
    for pick in picks:
        assert pick.name in content


def test_recommend_markdown_contains_date(tmp_path):
    rec = DailyRecommender(output_dir=str(tmp_path), top_n=3)
    restaurants = _ranked_restaurants(5)
    target_date = date(2024, 4, 16)
    rec.recommend(restaurants, today=target_date)

    md_file = tmp_path / "recommendations_2024-04-16.md"
    content = md_file.read_text(encoding="utf-8")
    assert "2024-04-16" in content


def test_recommend_uses_utc_today_by_default(tmp_path):
    """When no date is provided, recommend() should use UTC today."""
    from datetime import datetime, timezone
    rec = DailyRecommender(output_dir=str(tmp_path), top_n=2)
    restaurants = _ranked_restaurants(3)
    rec.recommend(restaurants)  # no date argument

    today_str = datetime.now(tz=timezone.utc).date().isoformat()
    json_file = tmp_path / f"recommendations_{today_str}.json"
    assert json_file.exists()
