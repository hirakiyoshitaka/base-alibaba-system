"""対話式商品一括登録スクリプト。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from base_alibaba.services.profit_service import calc_profit
from base_alibaba.services.product_service import next_product_id, read_products, write_products
from base_alibaba.services.rate_service import get_cny_jpy_rate


def ask(prompt, default=""):
    val = input(prompt).strip()
    return val if val else default


def register_one(rate, products):
    print("\n" + "─" * 40)
    name = ask("商品名: ")
    if not name:
        return False

    url           = ask("1688 URL (なければEnter): ")
    purchase_cny  = float(ask("仕入れ価格（元）: ", "0"))
    sell_jpy      = float(ask("販売価格（円）: ", "0"))
    intl_shipping = float(ask("国際送料（円）[0]: ", "0"))
    tariff_rate   = float(ask("関税率（%）[0]: ", "0")) / 100
    stock         = ask("在庫ステータス [available]: ", "available")
    notes         = ask("メモ (なければEnter): ")

    r = calc_profit(purchase_cny, sell_jpy, intl_shipping, tariff_rate, rate)
    new_id = next_product_id(products)
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
    print(f"✅ #{new_id}「{name}」を追加　利益 ¥{r['profit']:,.0f} / {r['profit_rate']:.1f}%")
    return True


def main():
    print("=== 商品一括登録 ===")
    print("1商品ずつ入力します。商品名を空欄にすると終了します。\n")

    rate = get_cny_jpy_rate()
    print(f"現在レート: 1元 = {rate:.2f}円\n")

    products = read_products()
    count = 0

    while True:
        ok = register_one(rate, products)
        if not ok:
            break
        count += 1
        again = ask("\n続けて登録しますか？ [y/N]: ", "n")
        if again.lower() != "y":
            break

    print(f"\n登録完了: {count}件追加しました。")


if __name__ == "__main__":
    main()
