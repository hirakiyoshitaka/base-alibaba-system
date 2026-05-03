"""CLI commands for product management."""

import sys

from base_alibaba.services.profit_service import calc_profit
from base_alibaba.services.product_service import next_product_id, read_products, write_products
from base_alibaba.services.rate_service import get_cny_jpy_rate
from base_alibaba.storage.paths import PRODUCTS_CSV


def cmd_product_add(args):
    rate     = get_cny_jpy_rate()
    products = read_products()
    new_id   = next_product_id(products)

    # 引数が揃っていれば非対話モード、不足していれば対話で補完
    # stdin が TTY でない（! 実行など）場合はデフォルト値をそのまま使う
    interactive = sys.stdin.isatty()
    def _ask(prompt, arg_val, default=""):
        if arg_val is not None:
            return str(arg_val)
        if not interactive:
            return default
        val = input(prompt).strip()
        return val or default

    print("\n─── 商品追加 ───")
    name          = _ask("商品名: ",              getattr(args, "name",     None))
    url           = _ask("アリババURL: ",          getattr(args, "url",      None))
    purchase_cny  = float(_ask("仕入れ価格（元）: ", getattr(args, "price",    None), "0"))
    sell_jpy      = float(_ask("販売価格  （円）: ", getattr(args, "sell",     None), "0"))
    intl_shipping = float(_ask("国際送料  （円）[0]: ", getattr(args, "shipping", None), "0"))
    tariff_rate   = float(_ask("関税率    （%） [0]: ", getattr(args, "tariff",   None), "0")) / 100
    stock         = _ask("在庫ステータス [available]: ", getattr(args, "stock",    None), "available")
    notes         = _ask("メモ: ",                getattr(args, "notes",    None), "")

    r = calc_profit(purchase_cny, sell_jpy, intl_shipping, tariff_rate, rate)
    products.append({
        "id": new_id,
        "name": name,
        "alibaba_url": url,
        "purchase_price_cny": purchase_cny,
        "sell_price_jpy": sell_jpy,
        "intl_shipping_jpy": intl_shipping,
        "tariff_rate": tariff_rate,
        "profit_jpy": round(r["profit"]),
        "profit_rate": round(r["profit_rate"], 1),
        "stock_status": stock,
        "notes": notes,
    })
    write_products(products)
    print(f"✅ 商品 #{new_id}「{name}」を追加しました"
          f"（利益 ¥{r['profit']:,.0f} / {r['profit_rate']:.1f}%）")

def cmd_product_list(_args):
    products = read_products()
    if not products:
        print("商品が登録されていません。  →  python tool.py product add")
        return
    print(f"\n{'ID':>4}  {'商品名':<24}  {'仕入(元)':>8}  {'販売(円)':>8}  "
          f"{'利益(円)':>8}  {'利益率':>6}  在庫")
    print("─" * 80)
    for p in products:
        flag = "✅" if float(p["profit_jpy"]) > 0 else "❌"
        print(f"{p['id']:>4}  {p['name'][:24]:<24}  "
              f"{float(p['purchase_price_cny']):>8.2f}  "
              f"¥{int(float(p['sell_price_jpy'])):>7,}  "
              f"¥{int(float(p['profit_jpy'])):>7,}  "
              f"{p['profit_rate']:>5}%  {p['stock_status']} {flag}")
    print(f"\n合計: {len(products)} 商品  |  CSV: {PRODUCTS_CSV}")

def cmd_product_delete(args):
    products = read_products()
    before   = len(products)
    products = [p for p in products if p["id"] != str(args.id)]
    if len(products) == before:
        print(f"ID {args.id} の商品が見つかりません。")
        return
    write_products(products)
    print(f"✅ 商品 #{args.id} を削除しました。")
