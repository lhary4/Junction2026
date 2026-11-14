"""Record real Valio Aimo answers for replay mode, while the Monday cut-off is still open.

Run: uv run python scripts/record_fixtures.py                the first recording: the milk case, delivery on 16/11
     uv run python scripts/record_fixtures.py restaurant     the restaurant's menu, delivery on 19/11
     uv run python scripts/record_fixtures.py restaurant-add  adds the greener alternatives to that recording

Needs the data files (scripts/fetch_data.py) and VALIO_AIMO_API_KEY. The first recording writes
contract/fixtures/valio/: products.json (trimmed records, one per line), availability.json and price.json (the raw API
answers), delivery-reliability.csv and carbon-footprint.csv (the matching rows), request.json and frozen_now.txt.
Then it checks the facts the demo script depends on, and exits with an error if one fails.

The restaurant recording is a second one, for another delivery date. It goes in its own sub-folder, named after that
date, with the same files (recorded_at.txt in place of frozen_now.txt): the first recording is not touched, because
the tests and the frozen clock of replay mode stand on it. Replay mode reads both (merchant/catalog.py).
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
from merchant.footprint import ECO_PAIRS

OUT = ROOT / "contract" / "fixtures" / "valio"
REQUESTED_DATE = "2026-11-16"  # the Monday of the demo
CATEGORIES = ("10400", "10402")  # lactose-free milks, plant-based drinks
DEMO_PRODUCTS = ("463380", "464201", "464306", "464320", "469363")  # the products in contract/examples/
# What search and quotes read. Marketing texts, media links and instructions are dropped to stay under 1 MB.
SYNKKA_KEPT = ("gtin", "countriesOfOrigin", "names", "brand", "classifications", "keyIngredients", "ingredients")
MAX_BYTES = 1_000_000
HELSINKI = ZoneInfo("Europe/Helsinki")

RESTAURANT_CASE = ROOT / "scenarios" / "restaurant-case" / "order.json"
# The menu products the demo replaces. Every product of their category is recorded with them, so that replay mode
# ranks the same candidates as live mode did.
SUBSTITUTED = ("474880",)  # the squeaky cheese of the dessert


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


def restaurant_shortlist(products: dict[str, dict]) -> tuple[str, list[str]]:
    """The delivery date the restaurant asks for, and what to record: its menu, and the candidates to replace a product."""
    case = json.loads(RESTAURANT_CASE.read_text(encoding="utf-8"))
    ids = {line["product"]["product_id"] for line in case["lines"]}
    for replaced in SUBSTITUTED:
        category = products[replaced]["category"]
        ids.update(p["id"] for p in products.values() if p["category"] == category and str(p.get("deleted")) != "True")
        ids.update(s["substituteProduct"] for s in products[replaced].get("substitutions") or [])
    ids.update(pair.alternative for pair in ECO_PAIRS)
    return case["requested_delivery_date"], sorted(ids & set(products))


def add_to_restaurant(new_ids: list[str]):
    """Add a few products to the restaurant recording without asking Valio again about the others.

    The products already recorded keep their answers, so the recorded demo runs stay true. Used for the greener
    alternatives of merchant/footprint.py.
    """
    data = valio_api.data_dir()
    products = {p["id"]: p for p in json.loads((data / "products.json").read_bytes())}
    requested_date = json.loads(RESTAURANT_CASE.read_text(encoding="utf-8"))["requested_delivery_date"]
    out = OUT / requested_date
    request = json.loads((out / "request.json").read_text(encoding="utf-8"))
    new_ids = sorted(set(new_ids) - set(request["products"]))
    if not new_ids:
        print("nothing to add: every product is already recorded")
        return
    print(f"adding {', '.join(new_ids)} to {out.relative_to(ROOT)}")
    availability = valio_api.availability(new_ids, requested_date)
    price = valio_api.price(new_ids, requested_date)

    ids = sorted(set(request["products"]) | set(new_ids))
    recorded = {p["id"]: p for p in json.loads((out / "products.json").read_bytes())}
    recorded |= {i: trim(products[i]) for i in new_ids}
    old_availability = json.loads((out / "availability.json").read_text(encoding="utf-8"))
    old_availability["products"] += availability["products"]
    old_price = json.loads((out / "price.json").read_text(encoding="utf-8"))
    old_price["products"] += price["products"]
    records = ",\n".join(json.dumps(recorded[i], ensure_ascii=False) for i in ids)
    files = {
        "products.json": f"[\n{records}\n]\n",
        "availability.json": json.dumps(old_availability, indent=1, ensure_ascii=False) + "\n",
        "price.json": json.dumps(old_price, indent=1, ensure_ascii=False) + "\n",
        "delivery-reliability.csv": matching_rows(data / "delivery-reliability.csv", set(ids)),
        "carbon-footprint.csv": matching_rows(data / "carbon-footprint.csv", set(ids)),
        "request.json": json.dumps({**request, "products": ids}) + "\n",
    }
    for name, text in files.items():
        (out / name).write_text(text, encoding="utf-8")
    print("added. Run uv run pytest")


def record_restaurant():
    """The second recording. It never writes outside its own sub-folder."""
    data = valio_api.data_dir()
    products = {p["id"]: p for p in json.loads((data / "products.json").read_bytes())}
    requested_date, ids = restaurant_shortlist(products)
    recorded_at = datetime.now(HELSINKI).replace(microsecond=0)
    print(f"recording {len(ids)} products for {requested_date} at {recorded_at.isoformat()}")
    availability = valio_api.availability(ids, requested_date)
    price = valio_api.price(ids, requested_date)

    out = OUT / requested_date
    out.mkdir(parents=True, exist_ok=True)
    records = ",\n".join(json.dumps(trim(products[i]), ensure_ascii=False) for i in ids)
    files = {
        "products.json": f"[\n{records}\n]\n",
        "availability.json": json.dumps(availability, indent=1, ensure_ascii=False) + "\n",
        "price.json": json.dumps(price, indent=1, ensure_ascii=False) + "\n",
        "delivery-reliability.csv": matching_rows(data / "delivery-reliability.csv", set(ids)),
        "carbon-footprint.csv": matching_rows(data / "carbon-footprint.csv", set(ids)),
        "request.json": json.dumps({"customer": "demo", "requestedDate": requested_date, "products": ids}) + "\n",
        "recorded_at.txt": recorded_at.isoformat() + "\n",
    }
    for name, text in files.items():
        (out / name).write_text(text, encoding="utf-8")

    size = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file())
    print(f"wrote {out.relative_to(ROOT)}: all recordings together are {size / 1e6:.2f} MB")
    if size > MAX_BYTES:
        print(f"DEMO CHECK FAILED: fixtures are {size} bytes, the limit is {MAX_BYTES}")
        sys.exit(1)
    print("recorded. The demo facts are checked by the tests: run uv run pytest")


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
    if sys.argv[1:] == ["restaurant"]:
        record_restaurant()
    elif sys.argv[1:2] == ["restaurant-add"]:
        add_to_restaurant(sys.argv[2:] or [pair.alternative for pair in ECO_PAIRS])
    else:
        main()
