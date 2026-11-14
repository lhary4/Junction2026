"""Write scenarios/pairs.todo.csv: 30 original and substitute pairs for Colette to label (ok, ask, no).

Run: uv run python scripts/make_pairs.py (reads contract/fixtures/valio/ only, no API call).
Léon sets the judge's thresholds from the labels. For each of the three originals: Valio's own listed substitutes
first, then the same-category products closest in price per litre, then the three closest plant-based drinks.
"""

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VALIO = ROOT / "contract" / "fixtures" / "valio"
OUT = ROOT / "scenarios" / "pairs.todo.csv"
ORIGINALS = ("464306", "469363", "463380")  # Valio Eila 1 l (acts 1 and 3), Arla 1 L (act 3), Arla Café 1 L
PER_ORIGINAL, PLANT_PER_ORIGINAL = 10, 3
PLANT_CATEGORY = "10402"
COLUMNS = [
    "original_id",
    "original_name",
    "candidate_id",
    "candidate_name",
    "candidate_contains",
    "same_category",
    "label",
]


def name(product: dict) -> str:
    names = {n["language"]: n["value"] for n in product["synkkaData"].get("names") or []}
    return names.get("en") or names.get("fi") or product["id"]


def contains(product: dict) -> str:
    """GS1 codes the product contains, space separated, or 'unknown' when it has no allergen data at all."""
    values = [
        v
        for c in product["synkkaData"].get("classifications") or []
        if c["name"] in ("allergen", "nonAllergen")
        for v in c.get("values") or []
    ]
    if not values:
        return "unknown"
    return " ".join(sorted(v["id"] for v in values if v.get("unit") == "CONTAINS")) or "none"


def candidates(original: dict, products: dict, per_litre: dict) -> list[str]:
    def by_price(ids):
        target = per_litre.get(original["id"], 0)
        return sorted(ids, key=lambda i: (abs(per_litre.get(i, 1e9) - target), i))

    listed = [s["substituteProduct"] for s in original.get("substitutions") or [] if s["substituteProduct"] in products]
    others = [i for i in products if i != original["id"] and i not in listed]
    same = by_price(i for i in others if products[i]["category"] == original["category"])
    plant = by_price(i for i in others if products[i]["category"] == PLANT_CATEGORY)
    picked = (listed + same)[: PER_ORIGINAL - PLANT_PER_ORIGINAL]
    return picked + plant[:PLANT_PER_ORIGINAL]


def main():
    products = {p["id"]: p for p in json.loads((VALIO / "products.json").read_text(encoding="utf-8"))}
    per_litre = {
        p["productId"]: p["comparisonPrice"]["value"]
        for p in json.loads((VALIO / "price.json").read_text(encoding="utf-8"))["products"]
        if p.get("comparisonPrice")
    }
    rows = []
    for original_id in ORIGINALS:
        original = products[original_id]
        for candidate_id in candidates(original, products, per_litre):
            candidate = products[candidate_id]
            same_category = str(candidate["category"] == original["category"]).lower()
            rows.append(
                [original_id, name(original), candidate_id, name(candidate), contains(candidate), same_category, ""]
            )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as file:
        csv.writer(file, lineterminator="\n").writerows([COLUMNS] + rows)
    print(f"wrote {OUT.relative_to(ROOT)}: {len(rows)} pairs")


if __name__ == "__main__":
    main()
