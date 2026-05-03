"""CLI command for profit calculation."""

from base_alibaba.services.profit_service import calc_profit
from base_alibaba.services.rate_service import get_cny_jpy_rate


def cmd_profit(args):
    rate = get_cny_jpy_rate()

    use_interactive = args.interactive or (args.purchase is None or args.sell is None)
    if use_interactive:
        print("\n─── 利益計算ツール（対話式）───")
        purchase_cny      = float(input("仕入れ価格（元）: "))
        sell_jpy          = float(input("販売価格  （円）: "))
        intl_shipping_jpy = float(input("国際送料  （円）[0]: ").strip() or "0")
        tariff_rate       = float(input("関税率    （%） [0]: ").strip() or "0") / 100
    else:
        purchase_cny      = args.purchase
        sell_jpy          = args.sell
        intl_shipping_jpy = args.shipping or 0.0
        tariff_rate       = (args.tariff or 0.0) / 100

    r = calc_profit(purchase_cny, sell_jpy, intl_shipping_jpy, tariff_rate, rate)
    flag = "✅ 黒字" if r["profit"] > 0 else "❌ 赤字"

    print(f"""
┌─────────────────── 利益計算結果 ───────────────────┐
│  仕入れ価格（円換算）  ¥{r['purchase_jpy']:>10,.0f}
│  関税                  ¥{r['tariff_jpy']:>10,.0f}
│  国際送料              ¥{intl_shipping_jpy:>10,.0f}
│  BASE手数料            ¥{r['base_fee']:>10,.0f}
│  ──────────────────────────────────────────────
│  合計コスト            ¥{r['total_cost']:>10,.0f}
│  販売価格              ¥{sell_jpy:>10,.0f}
│  ──────────────────────────────────────────────
│  粗利                  ¥{r['profit']:>10,.0f}  {flag}
│  利益率                {r['profit_rate']:>10.1f}%
│  損益分岐点            ¥{r['bep']:>10,.0f}
└────────────────────────────────────────────────────┘
""")
