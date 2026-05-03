"""CSV storage helpers for products and orders."""

import csv
import threading

from base_alibaba.config import ORDER_FIELDS, PRODUCT_FIELDS
from base_alibaba.storage.paths import DATA_DIR, ORDERS_CSV, PRODUCTS_CSV

CSV_LOCK = threading.Lock()


def init_data_dir():
    DATA_DIR.mkdir(exist_ok=True)
    for path, fields in [(PRODUCTS_CSV, PRODUCT_FIELDS), (ORDERS_CSV, ORDER_FIELDS)]:
        if not path.exists():
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                csv.DictWriter(f, fieldnames=fields).writeheader()


def read_products() -> list[dict]:
    if not PRODUCTS_CSV.exists():
        return []
    with open(PRODUCTS_CSV, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_products(products: list[dict]):
    with open(PRODUCTS_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=PRODUCT_FIELDS)
        w.writeheader()
        w.writerows(products)


def read_orders() -> list[dict]:
    if not ORDERS_CSV.exists():
        return []
    with open(ORDERS_CSV, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_orders(orders: list[dict]):
    with open(ORDERS_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=ORDER_FIELDS)
        w.writeheader()
        w.writerows(orders)
