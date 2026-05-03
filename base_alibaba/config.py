"""Application constants and CSV field definitions."""

BASE_FEE_RATE = 0.036
BASE_FEE_FIXED = 40
SHIPPING_WARN_DAYS = 14
RATE_CACHE_TTL = 3600

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

PRODUCT_FIELDS = [
    "id", "name", "alibaba_url", "purchase_price_cny",
    "sell_price_jpy", "intl_shipping_jpy", "tariff_rate",
    "profit_jpy", "profit_rate", "stock_status", "notes",
]

ORDER_FIELDS = [
    "order_id", "order_date", "buyer_name", "buyer_address",
    "product_id", "product_name", "quantity",
    "sell_price_jpy", "alibaba_url", "purchase_price_cny",
    "status", "tracking_number", "notes",
]
