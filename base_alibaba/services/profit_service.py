"""Profit calculation service."""

from base_alibaba.config import BASE_FEE_FIXED, BASE_FEE_RATE


def calc_profit(purchase_cny: float, sell_jpy: float,
                intl_shipping_jpy: float, tariff_rate: float,
                rate: float) -> dict:
    purchase_jpy = purchase_cny * rate
    tariff_jpy   = purchase_jpy * tariff_rate
    base_fee     = sell_jpy * BASE_FEE_RATE + BASE_FEE_FIXED
    total_cost   = purchase_jpy + tariff_jpy + intl_shipping_jpy + base_fee
    profit       = sell_jpy - total_cost
    profit_rate  = (profit / sell_jpy * 100) if sell_jpy > 0 else 0
    # 損益分岐点: sell*(1-0.036) = cost_without_base_fee + 40
    bep = (purchase_jpy + tariff_jpy + intl_shipping_jpy + BASE_FEE_FIXED) / (1 - BASE_FEE_RATE)
    return dict(
        purchase_jpy=purchase_jpy,
        tariff_jpy=tariff_jpy,
        base_fee=base_fee,
        total_cost=total_cost,
        profit=profit,
        profit_rate=profit_rate,
        bep=bep,
    )
