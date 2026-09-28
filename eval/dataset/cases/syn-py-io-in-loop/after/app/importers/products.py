import csv
import json
from decimal import Decimal
from pathlib import Path

RULES_PATH = Path("config/pricing_rules.json")


def import_products(csv_path: Path) -> list[dict]:
    products = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            with RULES_PATH.open(encoding="utf-8") as rules_file:
                rules = json.load(rules_file)
            markup = Decimal(str(rules.get(row["category"], rules["default"])))
            products.append(
                {"sku": row["sku"], "price": Decimal(row["cost"]) * (1 + markup)}
            )
    return products
