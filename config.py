"""
Configuration for what2eat-tokyo.

Copy .env.example to .env and fill in your credentials.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Google Maps ───────────────────────────────────────────────────────────────
GOOGLE_MAPS_API_KEY: str = os.getenv("GOOGLE_MAPS_API_KEY", "")

# ── Xiaohongshu (小红书) ───────────────────────────────────────────────────────
# Paste the value of the `a1` cookie from a logged-in browser session.
XHS_COOKIE: str = os.getenv("XHS_COOKIE", "")

# ── Search parameters ─────────────────────────────────────────────────────────
# Keyword used when searching Xiaohongshu
XHS_SEARCH_KEYWORD: str = os.getenv("XHS_SEARCH_KEYWORD", "东京 中餐厅")

# Tokyo bounding box used by Google Maps radius search
TOKYO_LAT: float = float(os.getenv("TOKYO_LAT", "35.6895"))
TOKYO_LNG: float = float(os.getenv("TOKYO_LNG", "139.6917"))
TOKYO_RADIUS_METERS: int = int(os.getenv("TOKYO_RADIUS_METERS", "30000"))

# ── Output ────────────────────────────────────────────────────────────────────
OUTPUT_DIR: str = os.getenv("OUTPUT_DIR", "output")
DAILY_TOP_N: int = int(os.getenv("DAILY_TOP_N", "5"))
