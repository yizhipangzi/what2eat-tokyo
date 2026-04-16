"""
Xiaohongshu (小红书) scraper.

Fetches notes (posts) about Chinese restaurants in Tokyo from the current week
by calling Xiaohongshu's internal web search API.

Authentication
--------------
Xiaohongshu requires a valid browser session. Set the ``XHS_COOKIE``
environment variable to the full ``Cookie:`` header value copied from a
logged-in browser session (DevTools → Network → any XHR → copy the cookie
header).

Rate-limiting / retries
-----------------------
The scraper uses :mod:`tenacity` to retry on transient HTTP errors with
exponential back-off.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

# Xiaohongshu internal web search endpoint
_XHS_SEARCH_URL = "https://edith.xiaohongshu.com/api/sns/web/v1/search/notes"

# Tokyo-area keywords we look for in post text / title
_TOKYO_KEYWORDS = ["东京", "Tokyo", "関東", "关东", "新宿", "涩谷", "渋谷", "池袋", "银座", "銀座"]

_DEFAULT_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "zh-CN,zh;q=0.9",
    "content-type": "application/json;charset=UTF-8",
    "origin": "https://www.xiaohongshu.com",
    "referer": "https://www.xiaohongshu.com/",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}


@dataclass
class XHSNote:
    """A single Xiaohongshu note about a restaurant."""

    note_id: str
    title: str
    desc: str
    author: str
    likes: int
    comments: int
    shares: int
    cover_url: str
    note_url: str
    keywords: list[str] = field(default_factory=list)
    # engagement score computed after collection
    engagement_score: float = 0.0


class XiaohongshuScraper:
    """Scrape Chinese-restaurant posts in Tokyo from Xiaohongshu for the current week.

    Parameters
    ----------
    cookie:
        Full ``Cookie`` header string from a logged-in XHS browser session.
    keyword:
        Search keyword (default ``"东京 中餐厅"``).
    max_pages:
        Maximum number of result pages to fetch (20 notes per page).
    """

    def __init__(
        self,
        cookie: str,
        keyword: str = "东京 中餐厅",
        max_pages: int = 3,
    ) -> None:
        self.cookie = cookie
        self.keyword = keyword
        self.max_pages = max_pages
        self._session = requests.Session()
        self._session.headers.update({**_DEFAULT_HEADERS, "cookie": cookie})

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch(self) -> list[XHSNote]:
        """Return all matching notes collected across ``max_pages`` pages.

        Returns an empty list when credentials are missing or the API returns
        an error – so callers can still use data from the other sources.
        """
        if not self.cookie:
            logger.warning("XHS_COOKIE is not set; skipping Xiaohongshu scraping.")
            return []

        notes: list[XHSNote] = []
        cursor = ""
        for page in range(1, self.max_pages + 1):
            logger.info("Fetching XHS page %d (keyword=%r)", page, self.keyword)
            try:
                raw_notes, cursor = self._fetch_page(cursor)
            except Exception as exc:
                logger.error("XHS page %d failed: %s", page, exc)
                break
            notes.extend(raw_notes)
            if not cursor:
                break
            time.sleep(1.5)  # be polite

        # Filter to notes published this week
        notes = self._filter_current_week(notes)
        # Score by engagement
        for note in notes:
            note.engagement_score = self._engagement_score(note)
        notes.sort(key=lambda n: n.engagement_score, reverse=True)
        logger.info("XHS: collected %d notes after filtering", len(notes))
        return notes

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    def _fetch_page(self, cursor: str) -> tuple[list[XHSNote], str]:
        """Fetch one page of search results and return (notes, next_cursor)."""
        payload: dict[str, Any] = {
            "keyword": self.keyword,
            "page": 1,
            "page_size": 20,
            "search_id": self._search_id(),
            "sort": "general",
            "note_type": 0,
            "cursor": cursor,
        }
        resp = self._session.post(_XHS_SEARCH_URL, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 0:
            raise RuntimeError(f"XHS API error {data.get('code')}: {data.get('msg')}")

        items = data.get("data", {}).get("items", [])
        next_cursor: str = data.get("data", {}).get("cursor", "")
        notes = [self._parse_item(item) for item in items if self._is_restaurant_related(item)]
        return notes, next_cursor

    def _parse_item(self, item: dict[str, Any]) -> XHSNote:
        note_card = item.get("note_card", item)
        note_id: str = item.get("id", note_card.get("note_id", ""))
        title: str = note_card.get("display_title", note_card.get("title", ""))
        desc: str = note_card.get("desc", "")
        author: str = note_card.get("user", {}).get("nickname", "")
        interact_info = note_card.get("interact_info", {})
        likes: int = int(interact_info.get("liked_count", 0))
        comments: int = int(interact_info.get("comment_count", 0))
        shares: int = int(interact_info.get("share_count", 0))
        images = note_card.get("image_list", [])
        cover_url: str = images[0].get("url", "") if images else ""
        note_url = f"https://www.xiaohongshu.com/explore/{note_id}"
        return XHSNote(
            note_id=note_id,
            title=title,
            desc=desc,
            author=author,
            likes=likes,
            comments=comments,
            shares=shares,
            cover_url=cover_url,
            note_url=note_url,
        )

    @staticmethod
    def _is_restaurant_related(item: dict[str, Any]) -> bool:
        """Return True if the note looks like a restaurant/food post."""
        note_card = item.get("note_card", item)
        text = " ".join([
            note_card.get("display_title", note_card.get("title", "")),
            note_card.get("desc", ""),
        ]).lower()
        food_keywords = ["餐", "饭", "菜", "食", "吃", "中餐", "restaurant", "dim sum", "点心"]
        return any(kw in text for kw in food_keywords)

    @staticmethod
    def _filter_current_week(notes: list[XHSNote]) -> list[XHSNote]:
        """Keep notes whose XHS note-id encodes a timestamp from this week.

        XHS note IDs embed a millisecond timestamp in the first 8 hex chars
        (MongoDB ObjectId format).  Fall back to keeping all notes when the
        ID cannot be decoded.
        """
        now = datetime.now(tz=timezone.utc)
        week_start = now - timedelta(days=now.weekday())
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)

        filtered: list[XHSNote] = []
        for note in notes:
            try:
                ts_hex = note.note_id[:8]
                ts = datetime.fromtimestamp(int(ts_hex, 16), tz=timezone.utc)
                if ts >= week_start:
                    filtered.append(note)
            except (ValueError, OverflowError):
                # Can't determine timestamp – keep the note
                filtered.append(note)
        return filtered

    @staticmethod
    def _engagement_score(note: XHSNote) -> float:
        """Weighted engagement score used for ranking."""
        return note.likes * 1.0 + note.comments * 2.0 + note.shares * 1.5

    @staticmethod
    def _search_id() -> str:
        """Generate a pseudo-unique search ID (MD5 of current timestamp)."""
        return hashlib.md5(str(time.time()).encode()).hexdigest()
