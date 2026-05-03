"""Product persistence and business helpers."""

from base_alibaba.storage.csv_store import read_products, write_products


def next_product_id(products: list[dict]) -> str:
    return str(max((int(p["id"]) for p in products), default=0) + 1)
