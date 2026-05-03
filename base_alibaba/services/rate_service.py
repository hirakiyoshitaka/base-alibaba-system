"""CNY/JPY rate retrieval and cache handling."""

import json
import urllib.request
from datetime import datetime

from base_alibaba.config import RATE_CACHE_TTL
from base_alibaba.storage.paths import RATE_CACHE


def get_cny_jpy_rate(force_refresh: bool = False) -> float:
    """CNY→JPY レートを取得（1時間キャッシュ付き）"""
    now = datetime.now().timestamp()

    if not force_refresh and RATE_CACHE.exists():
        cache = json.loads(RATE_CACHE.read_text())
        if now - cache.get("timestamp", 0) < RATE_CACHE_TTL:
            return cache["rate"]

    try:
        url = "https://open.er-api.com/v6/latest/CNY"
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = json.loads(resp.read())
        rate = data["rates"]["JPY"]
        RATE_CACHE.write_text(json.dumps({"rate": rate, "timestamp": now}))
        print(f"💱 為替レート更新: 1元 = {rate:.4f}円")
        return rate
    except Exception as e:
        print(f"⚠️  為替レート取得失敗: {e}")
        if RATE_CACHE.exists():
            cached = json.loads(RATE_CACHE.read_text())
            print(f"   キャッシュ値を使用: 1元 = {cached['rate']:.4f}円")
            return cached["rate"]
        val = input("CNY/JPY レートを手動入力（例: 21.5）: ")
        return float(val)
