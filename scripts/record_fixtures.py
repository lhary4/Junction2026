"""Record real Valio Aimo answers for replay mode, while the Monday cut-off is still open.

Run: uv run python scripts/record_fixtures.py
Needs the data files (scripts/fetch_data.py) and VALIO_AIMO_API_KEY. Writes contract/fixtures/valio/:
products.json (trimmed records, one per line), availability.json and price.json (the raw API answers),
delivery-reliability.csv and carbon-footprint.csv (the matching rows), request.json and frozen_now.txt.
Then checks the facts the demo script depends on, and exits with an error if one fails.
"""

import csv
import io
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from merchant import valio_api

OUT = ROOT / "contract" / "fixtures" / "valio"
REQUESTED_DATE = "2026-11-16"  # the Monday of the demo
CATEGORIES = ("10400", "10402")  # lactose-free milks, plant-based drinks
DEMO_PRODUCTS = ("463380", "464201", "464306", "464320", "469363")  # the products in contract/examples/
# What search and quotes read. Marketing texts, media links and instructions are dropped to stay under 1 MB.
SYNKKA_KEPT = ("gtin", "countriesOfOrigin", "names", "brand", "classifications", "keyIngredients", "ingredients")
MAX_BYTES = 1_000_000
HELSINKI = ZoneInfo("Europe/Helsinki")


def shortlist(products: dict[str, dict]) -> list[str]:
    ids = {p["id"] for p in products.values() if p["category"] in CATEGORIES and str(p.get("deleted")) != "True"}
    ids.update(DEMO_PRODUCTS)
    for demo in DEMO_PRODUCTS:
        ids.update(s["substituteProduct"] for s in products[demo].get("substitutions") or [])
    return sorted(ids)


def trim(product: dict) -> dict:
    synkka = product.get("synkkaData") or {}
    return {**product, "synkkaData": {k: synkka[k] for k in SYNKKA_KEPT if k in synkka}}


def matching_rows(path: Path, ids: set[str]) -> str:
    rows = list(csv.reader(io.StringIO(path.read_text(encoding="utf-8-sig"))))
    out = io.StringIO()
    csv.writer(out, lineterminator="\n").writerows([rows[0]] + [r for r in rows[1:] if r and r[0] in ids])
    return out.getvalue()


def demo_problems(availability: dict) -> list[str]:
    """The facts docs/demo-script.md depends on. An empty list means the demo still works on these answers."""
    by_id = {a["productId"]: a for a in availability["products"]}
    problems = []
    milk = by_id.get("464306") or {}
    amount = sum(line["availableAmount"] for line in milk.get("scheduleLines") or [])
    closing = milk.get("closingTime")
    if milk.get("logisticModel") != "Stock":
        problems.append(f"464306 is {milk.get('logisticModel')}, not Stock")
    if amount < 2000:
        problems.append(f"464306 has {amount} units, the demo needs at least 2000")
    if not closing or datetime.fromisoformat(closing).astimezone(HELSINKI).strftime("%a %H:%M") != "Sun 17:00":
        problems.append(f"464306 cut-off is {closing}, the demo needs Sunday 17:00 Helsinki time")
    arla = by_id.get("469363") or {}
    arla_amount = sum(line["availableAmount"] for line in arla.get("scheduleLines") or [])
    if arla_amount >= 600:
        problems.append(f"469363 has {arla_amount} units, the demo needs fewer than 600")
    return problems


def write(name: str, text: str):
    (OUT / name).write_text(text, encoding="utf-8")


def main():
    data = valio_api.data_dir()
    products = {p["id"]: p for p in json.loads((data / "products.json").read_bytes())}
    ids = shortlist(products)
    recorded_at = datetime.now(HELSINKI).replace(microsecond=0)
    print(f"recording {len(ids)} products for {REQUESTED_DATE} at {recorded_at.isoformat()}")
    availability = valio_api.availability(ids, REQUESTED_DATE)
    price = valio_api.price(ids, REQUESTED_DATE)

    OUT.mkdir(parents=True, exist_ok=True)
    write("products.json", "[\n" + ",\n".join(json.dumps(trim(products[i]), ensure_ascii=False) for i in ids) + "\n]\n")
    write("availability.json", json.dumps(availability, indent=1, ensure_ascii=False) + "\n")
    write("price.json", json.dumps(price, indent=1, ensure_ascii=False) + "\n")
    write("delivery-reliability.csv", matching_rows(data / "delivery-reliability.csv", set(ids)))
    write("carbon-footprint.csv", matching_rows(data / "carbon-footprint.csv", set(ids)))
    write("request.json", json.dumps({"customer": "demo", "requestedDate": REQUESTED_DATE, "products": ids}) + "\n")
    write("frozen_now.txt", recorded_at.isoformat() + "\n")

    size = sum(f.stat().st_size for f in OUT.iterdir())
    print(f"wrote {OUT.relative_to(ROOT)}: {size / 1e6:.2f} MB")
    problems = demo_problems(availability)
    if size > MAX_BYTES:
        problems.append(f"fixtures are {size} bytes, the limit is {MAX_BYTES}")
    for problem in problems:
        print(f"DEMO CHECK FAILED: {problem}")
    if problems:
        sys.exit(1)
    print("demo checks passed")


if __name__ == "__main__":
    main()
