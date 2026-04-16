"""
what2eat-tokyo – main entry point.

Usage
-----
::

    # Run with all three data sources (requires .env credentials):
    python main.py

    # Run with only Tabelog (no API keys needed):
    python main.py --tabelog-only

    # Dry-run: print picks to stdout without writing files:
    python main.py --dry-run

    # Specify a date for the recommendation:
    python main.py --date 2024-04-16

"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date

import config
from processors.data_merger import DataMerger
from recommender.daily_recommender import DailyRecommender
from scrapers.google_maps import GoogleMapsScraper
from scrapers.tabelog import TabelogScraper
from scrapers.xiaohongshu import XiaohongshuScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate daily Tokyo Chinese restaurant recommendations."
    )
    parser.add_argument(
        "--date",
        type=lambda s: date.fromisoformat(s),
        default=None,
        help="Target date (YYYY-MM-DD). Defaults to today (UTC).",
    )
    parser.add_argument(
        "--tabelog-only",
        action="store_true",
        help="Use only Tabelog data (no API keys required).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print recommendations to stdout without writing output files.",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=config.DAILY_TOP_N,
        help=f"Number of restaurants to recommend (default: {config.DAILY_TOP_N}).",
    )
    parser.add_argument(
        "--output-dir",
        default=config.OUTPUT_DIR,
        help=f"Directory for output files (default: {config.OUTPUT_DIR!r}).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # ── 1. Scrape ────────────────────────────────────────────────────────────
    logger.info("Step 1/3 – Scraping data sources …")

    tabelog_scraper = TabelogScraper(max_pages=3, min_rating=3.0)
    tabelog_restaurants = tabelog_scraper.fetch()
    logger.info("Tabelog: %d restaurants", len(tabelog_restaurants))

    if args.tabelog_only:
        google_maps_restaurants = []
        xhs_notes = []
        gm_scraper = None
    else:
        gm_scraper = GoogleMapsScraper(
            api_key=config.GOOGLE_MAPS_API_KEY,
            lat=config.TOKYO_LAT,
            lng=config.TOKYO_LNG,
            radius_meters=config.TOKYO_RADIUS_METERS,
        )
        google_maps_restaurants = gm_scraper.fetch()
        logger.info("Google Maps: %d restaurants", len(google_maps_restaurants))

        xhs_scraper = XiaohongshuScraper(
            cookie=config.XHS_COOKIE,
            keyword=config.XHS_SEARCH_KEYWORD,
        )
        xhs_notes = xhs_scraper.fetch()
        logger.info("Xiaohongshu: %d notes", len(xhs_notes))

    # ── 2. Merge ─────────────────────────────────────────────────────────────
    logger.info("Step 2/3 – Merging data …")
    merger = DataMerger(google_maps_scraper=gm_scraper)
    restaurants = merger.merge(tabelog_restaurants, google_maps_restaurants, xhs_notes)
    logger.info("Merged: %d restaurants", len(restaurants))

    # ── 3. Recommend ─────────────────────────────────────────────────────────
    logger.info("Step 3/3 – Generating recommendations …")
    recommender = DailyRecommender(output_dir=args.output_dir, top_n=args.top_n)
    picks = recommender.recommend(restaurants, today=args.date)

    # ── Output ───────────────────────────────────────────────────────────────
    if args.dry_run:
        print(json.dumps(
            [{"name": r.name, "score": r.composite_score} for r in picks],
            ensure_ascii=False,
            indent=2,
        ))
    else:
        print(f"\n🍜 Today's top {args.top_n} Tokyo Chinese restaurants:\n")
        for i, r in enumerate(picks, 1):
            score_str = f"{r.composite_score:.2f}"
            print(f"  {i}. {r.name} – score {score_str}")
            if r.tabelog_rating:
                print(f"     Tabelog: ⭐ {r.tabelog_rating:.2f}")
            if r.maps_rating:
                print(f"     Google Maps: ⭐ {r.maps_rating:.1f}")
            if r.area:
                print(f"     Area: {r.area}")
            print()
        print(f"Full results written to {args.output_dir}/")


if __name__ == "__main__":
    main()
