"""BASE webhook parsing, persistence, and HTTP handling."""

import hashlib
import hmac
import http.server
import json
from datetime import datetime

from base_alibaba.services.order_service import generate_supplier_memo
from base_alibaba.storage.csv_store import CSV_LOCK, read_orders, read_products, write_orders
from base_alibaba.storage.paths import WEBHOOK_CONFIG, WEBHOOK_LOG


def load_webhook_config() -> dict:
    if WEBHOOK_CONFIG.exists():
        return json.loads(WEBHOOK_CONFIG.read_text())
    return {"secret": "", "port": 8080}

def save_webhook_config(cfg: dict):
    WEBHOOK_CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2))

def _verify_signature(body: bytes, header_sig: str, secret: str) -> bool:
    """BASE X-Base-Hmac-Sha256 ヘッダーを検証（タイミング攻撃対策付き）"""
    if not secret:
        return True  # シークレット未設定時は検証スキップ（開発中用）
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header_sig)

def _parse_base_payload(payload: dict) -> list[dict]:
    """BASE webhook JSON → 内部order dict のリストに変換"""
    item = payload.get("order_item") or payload  # イベント形式の差吸収
    products = read_products()
    orders   = []

    customer = item.get("customer", {})
    name = customer.get("name", "不明")
    pref = customer.get("pref", "")
    addr = customer.get("address", "")
    addr2 = customer.get("address2", "")
    zip_code = customer.get("zip_code", "")
    full_address = f"〒{zip_code} {pref}{addr}{addr2}".strip()

    ordered_ts = item.get("ordered", 0)
    order_date = (datetime.fromtimestamp(ordered_ts).strftime("%Y-%m-%d")
                  if ordered_ts else datetime.now().strftime("%Y-%m-%d"))
    base_order_id = str(item.get("unique_key", ""))

    for idx, line in enumerate(item.get("order_items", []), start=1):
        title    = line.get("title", "不明")
        price    = line.get("price", 0)
        quantity = line.get("amount", 1)
        sub_id   = f"{base_order_id}-{idx}" if len(item.get("order_items", [])) > 1 else base_order_id

        # 商品マスタと名前でマッチング
        matched = next(
            (p for p in products if p["name"].strip() == title.strip()), None
        )
        orders.append({
            "order_id":          sub_id or f"BASE-{datetime.now().strftime('%Y%m%d%H%M%S')}-{idx}",
            "order_date":        order_date,
            "buyer_name":        name,
            "buyer_address":     full_address,
            "product_id":        matched["id"] if matched else "",
            "product_name":      title,
            "quantity":          str(quantity),
            "sell_price_jpy":    str(price),
            "alibaba_url":       matched["alibaba_url"] if matched else "（要設定）",
            "purchase_price_cny": matched["purchase_price_cny"] if matched else "（要設定）",
            "status":            "pending",
            "tracking_number":   "",
            "notes":             f"BASE webhook自動取込 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        })
    return orders

def _append_orders_safe(new_orders: list[dict]):
    with CSV_LOCK:
        existing = read_orders()
        existing_ids = {o["order_id"] for o in existing}
        added = [o for o in new_orders if o["order_id"] not in existing_ids]
        if added:
            write_orders(existing + added)
        return added

def _log_webhook(event: str, payload: dict, orders: list[dict]):
    entry = {
        "ts":     datetime.now().isoformat(),
        "event":  event,
        "orders": [o["order_id"] for o in orders],
        "raw":    payload,
    }
    with open(WEBHOOK_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

def _print_new_order_banner(order: dict):
    print(f"\n{'━'*54}")
    print(f"  🛒 新規注文受信！  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'━'*54}")
    print(generate_supplier_memo(order))

class _WebhookHandler(http.server.BaseHTTPRequestHandler):

    secret: str = ""  # cmd_webhook_start がセット

    def log_message(self, fmt, *args):  # デフォルトのアクセスログを抑制
        pass

    def do_GET(self):
        """死活確認エンドポイント"""
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"BASE webhook receiver OK")

    def do_POST(self):
        length  = int(self.headers.get("Content-Length", 0))
        body    = self.rfile.read(length)
        sig     = self.headers.get("X-Base-Hmac-Sha256", "")

        if not _verify_signature(body, sig, self.secret):
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"Signature mismatch")
            print("⚠️  署名検証失敗 — 不正リクエストを拒否しました")
            return

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Invalid JSON")
            return

        # 注文イベントのみ処理（キャンセル等は無視）
        event = payload.get("event", "order")
        if "order" not in event and "order_item" not in payload:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ignored")
            return

        new_orders = _parse_base_payload(payload)
        added      = _append_orders_safe(new_orders)
        _log_webhook(event, payload, new_orders)

        if added:
            for o in added:
                _print_new_order_banner(o)
        else:
            print(f"⚠️  受信済み注文ID — スキップ: {[o['order_id'] for o in new_orders]}")

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")
