"""CLI command for exchange rate display."""

from base_alibaba.services.rate_service import get_cny_jpy_rate


def cmd_rate(args):
    rate = get_cny_jpy_rate(force_refresh=args.refresh)
    print(f"\n💱 CNY/JPY: 1元 = {rate:.4f}円\n")
    print(f"  {'元':>6}  →  {'円':>10}")
    print("  " + "─" * 22)
    for cny in [10, 30, 50, 100, 200, 500, 1000, 3000]:
        print(f"  {cny:>6}元  →  ¥{cny * rate:>9,.0f}")
