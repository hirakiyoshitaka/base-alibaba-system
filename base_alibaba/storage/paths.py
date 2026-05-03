"""Filesystem paths used by the BASE Alibaba tool."""

from pathlib import Path

DATA_DIR = Path.home() / ".base_alibaba"
PRODUCTS_CSV = DATA_DIR / "products.csv"
ORDERS_CSV = DATA_DIR / "orders.csv"
RATE_CACHE = DATA_DIR / "rate_cache.json"
WEBHOOK_CONFIG = DATA_DIR / "webhook_config.json"
WEBHOOK_LOG = DATA_DIR / "webhook_log.jsonl"
NOTION_CONFIG = DATA_DIR / "notion_config.json"
COOKIES_FILE = DATA_DIR / "1688_cookies.json"

PROJECT_ROOT = Path(__file__).resolve().parents[2]
IMAGES_DIR = PROJECT_ROOT / "images"
