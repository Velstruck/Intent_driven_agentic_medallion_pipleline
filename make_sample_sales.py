"""Generate dirty retail sample data described by project_builder.md."""
import csv
import random
from datetime import date, timedelta
from pathlib import Path

random.seed(42)
products = list(csv.DictReader(Path("raw_files/products.csv").open(encoding="utf-8")))
stores = [row["store_id"] for row in csv.DictReader(Path("raw_files/stores.csv").open(encoding="utf-8"))]
categories = {"Electronics": ["Electronics", "ELECTRONICS", "Elec.", "Electronic"], "Apparel": ["Apparel", "apparel", "Clothing"], "Sports": ["Sports", "sports", "SPORTS", "Sport", "Sporting Goods"], "Home & Kitchen": ["Home & Kitchen", "HOME & KITCHEN", "home & kitchen", "Home"], "Beauty": ["Beauty", "BEAUTY", "beauty", "Cosmetics"]}
segments = {"Loyal": ["Loyal", "LOYAL", "loyal", "Lyl"], "Premium": ["Premium", "PREMIUM", "premium", "Prem"], "Standard": ["Standard", "STANDARD", "standard", "Std"], "Budget": ["Budget", "BUDGET", "budget", "Bgt"]}
payments = ["Credit Card", "Apple Pay", "PayPal", "Debit Card"]
start = date(2024, 1, 1)
rows = []
for index in range(176):
    product = random.choice(products)
    day = start + timedelta(days=random.randint(0, 89))
    quantity = random.randint(1, 8)
    price = round(float(product["standard_price"]) * random.uniform(0.92, 1.08), 2)
    rows.append([f"TXN{10000 + index}", day.isoformat() if random.random() < 0.65 else day.strftime("%m/%d/%Y"), random.choice(stores), product["product_id"], product["product_name"], random.choice(categories[product["category"]]), quantity, price, round(quantity * price, 2), random.choice(random.choice(list(segments.values()))), random.choice(payments)])
for index in range(10):
    product = random.choice(products)
    day = start + timedelta(days=random.randint(0, 89))
    quantity = -random.randint(1, 3)
    price = round(float(product["standard_price"]) * random.uniform(0.92, 1.08), 2)
    rows.append([f"RET{10000 + index}", day.isoformat(), random.choice(stores), product["product_id"], product["product_name"], product["category"], quantity, price, round(quantity * price, 2), random.choice(random.choice(list(segments.values()))), random.choice(payments)])
for index in random.sample(range(len(rows)), 5):
    rows[index][2] = ""
for index in random.sample(range(len(rows)), 6):
    rows.append(list(rows[index]))
random.shuffle(rows)
with Path("raw_files/sales_data.csv").open("w", newline="", encoding="utf-8") as handle:
    writer = csv.writer(handle)
    writer.writerow(["transaction_id", "transaction_date", "store_id", "product_id", "product_name", "category", "quantity", "unit_price", "total_amount", "customer_segment", "payment_method"])
    writer.writerows(rows)
print(f"wrote {len(rows)} rows")
