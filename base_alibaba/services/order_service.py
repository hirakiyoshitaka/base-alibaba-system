"""Order persistence and supplier memo generation."""

from datetime import datetime, timedelta

from base_alibaba.config import SHIPPING_WARN_DAYS
from base_alibaba.storage.csv_store import read_orders, write_orders


def _deadline_str(order_date_str: str) -> str:
    return (datetime.strptime(order_date_str, "%Y-%m-%d")
            + timedelta(days=SHIPPING_WARN_DAYS)).strftime("%Y-%m-%d")

def generate_supplier_memo(o: dict) -> str:
    deadline = _deadline_str(o["order_date"])
    return f"""
╔══════════════ サプライヤー発注メモ ══════════════╗
  注文ID     : {o['order_id']}
  注文日     : {o['order_date']}
  ─────────────────────────────────────────────
  商品名     : {o['product_name']}
  アリババURL: {o['alibaba_url']}
  数量       : {o['quantity']} 個
  仕入価格   : {o['purchase_price_cny']} 元
  ─────────────────────────────────────────────
  送付先氏名 : {o['buyer_name']}
  送付先住所 : {o['buyer_address']}
  ─────────────────────────────────────────────
  ⚠️  配送期限（14日以内）: {deadline}
╚══════════════════════════════════════════════╝
"""
