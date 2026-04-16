"""Tests for the Xiaohongshu scraper."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from scrapers.xiaohongshu import XHSNote, XiaohongshuScraper


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_note(
    note_id: str = "000000000000000000000001",
    title: str = "东京中餐厅推荐",
    desc: str = "好吃的中餐",
    author: str = "test_user",
    likes: int = 100,
    comments: int = 20,
    shares: int = 10,
) -> XHSNote:
    return XHSNote(
        note_id=note_id,
        title=title,
        desc=desc,
        author=author,
        likes=likes,
        comments=comments,
        shares=shares,
        cover_url="https://example.com/img.jpg",
        note_url=f"https://www.xiaohongshu.com/explore/{note_id}",
    )


def _note_api_item(
    note_id: str = "000000000000000000000001",
    title: str = "东京中餐厅推荐",
    desc: str = "好吃的中餐",
    likes: int = 100,
    comments: int = 20,
    shares: int = 10,
) -> dict:
    """Mimic a single item returned by the XHS search API."""
    return {
        "id": note_id,
        "note_card": {
            "display_title": title,
            "desc": desc,
            "user": {"nickname": "test_user"},
            "interact_info": {
                "liked_count": likes,
                "comment_count": comments,
                "share_count": shares,
            },
            "image_list": [{"url": "https://example.com/img.jpg"}],
        },
    }


# ---------------------------------------------------------------------------
# Tests: fetch() – no cookie
# ---------------------------------------------------------------------------


def test_fetch_returns_empty_when_no_cookie():
    scraper = XiaohongshuScraper(cookie="")
    result = scraper.fetch()
    assert result == []


# ---------------------------------------------------------------------------
# Tests: _parse_item
# ---------------------------------------------------------------------------


def test_parse_item_basic():
    scraper = XiaohongshuScraper(cookie="test_cookie")
    item = _note_api_item(likes=50, comments=5, shares=2)
    note = scraper._parse_item(item)
    assert note.title == "东京中餐厅推荐"
    assert note.author == "test_user"
    assert note.likes == 50
    assert note.comments == 5
    assert note.shares == 2
    assert note.note_url.startswith("https://www.xiaohongshu.com/explore/")


def test_parse_item_missing_images():
    scraper = XiaohongshuScraper(cookie="test_cookie")
    item = _note_api_item()
    item["note_card"]["image_list"] = []
    note = scraper._parse_item(item)
    assert note.cover_url == ""


# ---------------------------------------------------------------------------
# Tests: _is_restaurant_related
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("title,desc,expected", [
    ("东京中餐厅推荐", "好吃的中餐", True),
    ("东京旅游攻略", "景点介绍", False),
    ("Tokyo restaurant guide", "Chinese food", True),
    ("日本行程规划", "交通住宿", False),
    ("点心推荐", "港式饮茶", True),
])
def test_is_restaurant_related(title: str, desc: str, expected: bool):
    item = {"note_card": {"display_title": title, "desc": desc}}
    assert XiaohongshuScraper._is_restaurant_related(item) == expected


# ---------------------------------------------------------------------------
# Tests: _engagement_score
# ---------------------------------------------------------------------------


def test_engagement_score():
    note = _make_note(likes=100, comments=50, shares=20)
    score = XiaohongshuScraper._engagement_score(note)
    # 100*1.0 + 50*2.0 + 20*1.5 = 100 + 100 + 30 = 230
    assert score == pytest.approx(230.0)


# ---------------------------------------------------------------------------
# Tests: _filter_current_week
# ---------------------------------------------------------------------------


def _hex_timestamp(dt: datetime) -> str:
    """Encode a datetime as 8-char hex timestamp (ObjectId prefix)."""
    return format(int(dt.timestamp()), "08x")


def test_filter_current_week_keeps_this_week():
    now = datetime.now(tz=timezone.utc)
    note = _make_note(note_id=_hex_timestamp(now) + "0000000000000000")
    result = XiaohongshuScraper._filter_current_week([note])
    assert note in result


def test_filter_current_week_drops_old_note():
    three_weeks_ago = datetime.now(tz=timezone.utc) - timedelta(weeks=3)
    note = _make_note(note_id=_hex_timestamp(three_weeks_ago) + "0000000000000000")
    result = XiaohongshuScraper._filter_current_week([note])
    assert note not in result


def test_filter_current_week_keeps_unparseable_id():
    """Notes whose IDs cannot be decoded as timestamps should be kept."""
    note = _make_note(note_id="ZZZZZZZZ0000000000000000")
    result = XiaohongshuScraper._filter_current_week([note])
    assert note in result


# ---------------------------------------------------------------------------
# Tests: fetch() – mocked HTTP
# ---------------------------------------------------------------------------


def _api_response(items: list[dict], cursor: str = "") -> dict:
    return {"code": 0, "data": {"items": items, "cursor": cursor}}


def test_fetch_with_mocked_api():
    scraper = XiaohongshuScraper(cookie="valid_cookie", max_pages=1)
    now = datetime.now(tz=timezone.utc)
    note_id = _hex_timestamp(now) + "0000000000000000"
    items = [_note_api_item(note_id=note_id, likes=200, comments=30, shares=15)]

    mock_resp = MagicMock()
    mock_resp.json.return_value = _api_response(items, cursor="")
    mock_resp.raise_for_status.return_value = None

    with patch.object(scraper._session, "post", return_value=mock_resp):
        notes = scraper.fetch()

    assert len(notes) == 1
    assert notes[0].likes == 200
    assert notes[0].engagement_score > 0


def test_fetch_api_error_returns_empty():
    """When the API returns a non-zero code, fetch() should return []."""
    scraper = XiaohongshuScraper(cookie="valid_cookie", max_pages=1)

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"code": -1, "msg": "Unauthorized"}
    mock_resp.raise_for_status.return_value = None

    with patch.object(scraper._session, "post", return_value=mock_resp):
        notes = scraper.fetch()

    assert notes == []
