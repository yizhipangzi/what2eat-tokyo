"""
Daily recommendation generator.

Takes the merged, ranked list of restaurants produced by
:class:`~processors.data_merger.DataMerger` and selects a curated set of
daily picks, rotating day-by-day so the same restaurant is not recommended
every day.

Output
------
- JSON file:      ``output/recommendations_YYYY-MM-DD.json``
- Markdown file:  ``output/recommendations_YYYY-MM-DD.md``
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from processors.data_merger import Restaurant

logger = logging.getLogger(__name__)


class DailyRecommender:
    """Select and format the daily restaurant recommendations.

    Parameters
    ----------
    output_dir:
        Directory where output files are written.
    top_n:
        Number of restaurants to recommend each day.
    """

    def __init__(self, output_dir: str = "output", top_n: int = 5) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.top_n = top_n

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def recommend(
        self,
        restaurants: list[Restaurant],
        today: date | None = None,
    ) -> list[Restaurant]:
        """Select today's top-N picks and write output files.

        The rotation is based on ``today.toordinal()`` so that each day a
        different sub-set of restaurants is shifted to the front.

        Parameters
        ----------
        restaurants:
            Full ranked list from the merger (highest ``composite_score`` first).
        today:
            Date for the recommendation (defaults to UTC today).

        Returns
        -------
        list[Restaurant]
            The selected daily picks in recommendation order.
        """
        if today is None:
            today = datetime.now(tz=timezone.utc).date()

        picks = self._select_picks(restaurants, today)
        self._write_json(picks, today)
        self._write_markdown(picks, today)
        logger.info("Recommendations for %s written to %s", today, self.output_dir)
        return picks

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    def _select_picks(self, restaurants: list[Restaurant], today: date) -> list[Restaurant]:
        """Rotate through the ranked list to produce today's picks."""
        if not restaurants:
            return []
        n = len(restaurants)
        offset = today.toordinal() % n
        # Rotate so each day uses a different starting index
        rotated = restaurants[offset:] + restaurants[:offset]
        return rotated[: self.top_n]

    # ------------------------------------------------------------------
    # Output writers
    # ------------------------------------------------------------------

    def _write_json(self, picks: list[Restaurant], today: date) -> None:
        path = self.output_dir / f"recommendations_{today}.json"
        payload = {
            "date": str(today),
            "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            "recommendations": [self._restaurant_to_dict(r) for r in picks],
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("JSON written: %s", path)

    def _write_markdown(self, picks: list[Restaurant], today: date) -> None:
        path = self.output_dir / f"recommendations_{today}.md"
        lines: list[str] = [
            f"# 🍜 东京圈今日美食推荐 – {today}",
            "",
            f"> 综合小红书、Tabelog 和 Google 地图数据，精选 {self.top_n} 家中餐厅。",
            "",
        ]
        for i, r in enumerate(picks, 1):
            lines.append(f"## {i}. {r.name}")
            if r.area:
                lines.append(f"**地区**: {r.area}")
            if r.address:
                lines.append(f"**地址**: {r.address}")
            if r.tabelog_rating:
                lines.append(f"**Tabelog 评分**: ⭐ {r.tabelog_rating:.2f} ({r.tabelog_reviews} 条评价)")
            if r.maps_rating:
                lines.append(f"**Google 评分**: ⭐ {r.maps_rating:.1f} ({r.maps_reviews} 条评价)")
            if r.price_dinner:
                lines.append(f"**晚餐价格**: {r.price_dinner}")
            if r.price_lunch:
                lines.append(f"**午餐价格**: {r.price_lunch}")
            if r.opening_hours:
                lines.append("**营业时间**:")
                for h in r.opening_hours:
                    lines.append(f"  - {h}")
            links: list[str] = []
            if r.tabelog_url:
                links.append(f"[Tabelog]({r.tabelog_url})")
            if r.maps_url:
                links.append(f"[Google 地图]({r.maps_url})")
            if r.website:
                links.append(f"[官网]({r.website})")
            if links:
                lines.append(f"**链接**: {' | '.join(links)}")
            if r.xhs_notes:
                lines.append("**小红书相关帖子**:")
                for note in r.xhs_notes[:3]:
                    lines.append(f"  - [{note['title']}]({note['url']}) ❤️ {note['likes']}")
            lines.append(f"**综合评分**: {r.composite_score:.2f} / 10")
            lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")
        logger.info("Markdown written: %s", path)

    @staticmethod
    def _restaurant_to_dict(r: Restaurant) -> dict:
        d = asdict(r)
        return d
