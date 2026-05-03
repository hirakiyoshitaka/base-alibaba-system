"""Notion API integration helpers."""

import json
import re
import urllib.error
import urllib.request

from base_alibaba.config import NOTION_API, NOTION_VERSION
from base_alibaba.storage.paths import NOTION_CONFIG


def _load_notion_cfg() -> dict:
    return json.loads(NOTION_CONFIG.read_text()) if NOTION_CONFIG.exists() else {}

def _save_notion_cfg(cfg: dict):
    NOTION_CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2))

def _notion_id(raw: str) -> str:
    """URL または生IDから Notion UUID を正規化して返す"""
    raw = raw.strip().split("?")[0].split("#")[0]
    h = re.sub(r"[^0-9a-fA-F]", "", raw)[-32:]  # 末尾32桁のhex
    if len(h) == 32:
        return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"
    return raw  # 変換できなければそのまま返す

def _notion_req(method: str, path: str, token: str, body: dict | None = None) -> dict:
    url  = f"{NOTION_API}/{path.lstrip('/')}"
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req  = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Authorization":  f"Bearer {token}",
            "Content-Type":   "application/json",
            "Notion-Version": NOTION_VERSION,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            msg = json.loads(raw).get("message", raw)
        except Exception:
            msg = raw[:200]
        raise RuntimeError(f"Notion API {e.code}: {msg}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Notion API接続失敗: {e}") from e

def _create_notion_db(token: str, parent_page_id: str) -> str:
    """BASEアリババ商品管理DBをNotionに作成してDB IDを返す"""
    body = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "icon":   {"type": "emoji", "emoji": "🛒"},
        "title":  [{"type": "text", "text": {"content": "BASEアリババ商品管理"}}],
        "properties": {
            "商品名":          {"title": {}},
            "アリババURL":     {"url": {}},
            "仕入れ価格(元)":  {"number": {"format": "yuan"}},
            "販売価格(円)":    {"number": {"format": "yen"}},
            "利益率":          {"number": {"format": "percent"}},
            "カテゴリ": {"select": {"options": [
                {"name": "ファッション",      "color": "pink"},
                {"name": "雑貨",             "color": "blue"},
                {"name": "美容・健康",        "color": "green"},
                {"name": "家電・ガジェット",  "color": "gray"},
                {"name": "その他",           "color": "default"},
            ]}},
            "販売状況": {"select": {"options": [
                {"name": "販売中",  "color": "green"},
                {"name": "品切れ",  "color": "yellow"},
                {"name": "停止中",  "color": "red"},
            ]}},
            "BASE URL": {"url": {}},
            "メモ":     {"rich_text": {}},
        },
    }
    result = _notion_req("POST", "databases", token, body)
    return result["id"]

def _to_notion_props(p: dict) -> dict:
    """product dict → Notion property値に変換"""
    def safe_float(v, default=0.0):
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    def url_val(v):
        v = str(v or "").strip()
        return v if v.startswith("http") else None

    stock_map = {
        "available":    "販売中",
        "out_of_stock": "品切れ",
        "discontinued": "停止中",
    }
    status = stock_map.get(str(p.get("stock_status", "")).strip(), "販売中")

    props: dict = {
        "商品名":         {"title":     [{"text": {"content": str(p.get("name", ""))}}]},
        "仕入れ価格(元)": {"number":    safe_float(p.get("purchase_price_cny"))},
        "販売価格(円)":   {"number":    safe_float(p.get("sell_price_jpy"))},
        "利益率":         {"number":    round(safe_float(p.get("profit_rate")) / 100, 5)},
        "販売状況":       {"select":    {"name": status}},
        "メモ":           {"rich_text": [{"text": {"content": str(p.get("notes", "") or "")}}]},
    }

    ali = url_val(p.get("alibaba_url"))
    if ali:
        props["アリババURL"] = {"url": ali}

    base = url_val(p.get("base_url"))
    if base:
        props["BASE URL"] = {"url": base}

    cat = str(p.get("category", "") or "").strip()
    if cat:
        props["カテゴリ"] = {"select": {"name": cat}}

    return props

def _query_all_pages(token: str, db_id: str) -> list[dict]:
    pages, cursor = [], None
    while True:
        body: dict = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        result = _notion_req("POST", f"databases/{db_id}/query", token, body)
        pages.extend(result.get("results", []))
        if not result.get("has_more"):
            break
        cursor = result.get("next_cursor")
    return pages

def _title_of(page: dict) -> str:
    for prop in page.get("properties", {}).values():
        if prop.get("type") == "title":
            items = prop.get("title", [])
            return items[0]["plain_text"] if items else ""
    return ""

def _read_prop(props: dict, key: str):
    """Notionプロパティから値を読み出す"""
    p = props.get(key, {})
    t = p.get("type", "")
    if t == "title":
        items = p.get("title", [])
        return items[0]["plain_text"] if items else ""
    if t == "rich_text":
        items = p.get("rich_text", [])
        return items[0]["plain_text"] if items else ""
    if t == "number":
        return p.get("number") or 0
    if t == "url":
        return p.get("url") or ""
    if t == "select":
        sel = p.get("select")
        return sel["name"] if sel else ""
    return ""
