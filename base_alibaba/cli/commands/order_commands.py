"""CLI commands for order management."""

from datetime import datetime, timedelta

from base_alibaba.config import SHIPPING_WARN_DAYS
from base_alibaba.services.order_service import generate_supplier_memo, read_orders, write_orders
from base_alibaba.services.product_service import read_products
from base_alibaba.storage.paths import ORDERS_CSV


def cmd_order_add(_args):
    products = read_products()
    orders   = read_orders()
    auto_id  = f"ORD-{datetime.now().strftime('%Y%m%d')}-{len(orders)+1:03d}"

    print("\n─── 注文追加 ───")
    order_id     = input(f"BASE注文ID [{auto_id}]: ").strip() or auto_id
    order_date   = input(f"注文日 [{datetime.now().strftime('%Y-%m-%d')}]: ").strip() \
                   or datetime.now().strftime("%Y-%m-%d")
    buyer_name   = input("購入者名: ")
    buyer_address = input("配送先住所（日本語OK）: ")

    matched = None
    if products:
        print("\n登録済み商品:")
        for p in products:
            print(f"  [{p['id']}] {p['name']}")
        pid = input("商品ID（手動入力する場合は空欄）: ").strip()
        matched = next((p for p in products if p["id"] == pid), None)

    if matched:
        product_id        = matched["id"]
        product_name      = matched["name"]
        alibaba_url       = matched["alibaba_url"]
        purchase_price_cny = matched["purchase_price_cny"]
        sell_price_jpy    = matched["sell_price_jpy"]
    else:
        product_id        = ""
        product_name      = input("商品名: ")
        alibaba_url       = input("アリババURL: ")
        purchase_price_cny = input("仕入れ価格（元）: ")
        sell_price_jpy    = input("販売価格（円）: ")

    quantity = input("数量 [1]: ").strip() or "1"
    notes    = input("メモ: ")

    order = {
        "order_id": order_id,
        "order_date": order_date,
        "buyer_name": buyer_name,
        "buyer_address": buyer_address,
        "product_id": product_id,
        "product_name": product_name,
        "quantity": quantity,
        "sell_price_jpy": sell_price_jpy,
        "alibaba_url": alibaba_url,
        "purchase_price_cny": purchase_price_cny,
        "status": "pending",
        "tracking_number": "",
        "notes": notes,
    }
    orders.append(order)
    write_orders(orders)
    print(f"\n✅ 注文 {order_id} を追加しました。")
    print(generate_supplier_memo(order))

def cmd_order_list(_args):
    orders = read_orders()
    if not orders:
        print("注文が登録されていません。  →  python tool.py order add")
        return
    today = datetime.now()
    print(f"\n{'注文ID':<22}  {'注文日':<12}  {'購入者':<14}  {'商品名':<20}  {'状態':<10}  期限")
    print("─" * 95)
    for o in orders:
        order_dt = datetime.strptime(o["order_date"], "%Y-%m-%d")
        deadline = order_dt + timedelta(days=SHIPPING_WARN_DAYS)
        days_left = (deadline - today).days
        if o["status"] == "shipped":
            warn = "✅ 発送済"
        elif days_left < 0:
            warn = f"🚨超過{abs(days_left)}日"
        elif days_left <= 3:
            warn = f"⚠️ 残{days_left}日"
        else:
            warn = deadline.strftime("%m/%d")
        print(f"{o['order_id']:<22}  {o['order_date']:<12}  {o['buyer_name'][:14]:<14}  "
              f"{o['product_name'][:20]:<20}  {o['status']:<10}  {warn}")
    print(f"\n合計: {len(orders)} 件  |  CSV: {ORDERS_CSV}")

def cmd_order_check(_args):
    orders = read_orders()
    today  = datetime.now()
    warns  = []
    for o in orders:
        if o["status"] in ("shipped", "delivered", "cancelled"):
            continue
        dt       = datetime.strptime(o["order_date"], "%Y-%m-%d")
        deadline = dt + timedelta(days=SHIPPING_WARN_DAYS)
        days_left = (deadline - today).days
        if days_left <= 3:
            warns.append((o, days_left))

    if not warns:
        print("✅ 配送遅延の懸念がある注文はありません。")
        return
    print(f"\n⚠️  要対応の注文 {len(warns)} 件")
    print("─" * 60)
    for o, days in sorted(warns, key=lambda x: x[1]):
        label = f"🚨 {abs(days)}日超過" if days < 0 else f"⚠️  残 {days} 日"
        print(f"  {label}  {o['order_id']}  {o['buyer_name']}  「{o['product_name']}」")
        print(f"          アリババURL: {o['alibaba_url']}")

def cmd_order_update(args):
    orders = read_orders()
    for o in orders:
        if o["order_id"] == args.order_id:
            if args.status:
                o["status"] = args.status
            if args.tracking:
                o["tracking_number"] = args.tracking
            write_orders(orders)
            print(f"✅ 注文 {args.order_id} を更新しました"
                  f"  ステータス: {o['status']}"
                  f"  追跡番号: {o['tracking_number'] or '（未設定）'}")
            return
    print(f"注文 {args.order_id} が見つかりません。")

def cmd_order_memo(args):
    orders = read_orders()
    for o in orders:
        if o["order_id"] == args.order_id:
            print(generate_supplier_memo(o))
            return
    print(f"注文 {args.order_id} が見つかりません。")
