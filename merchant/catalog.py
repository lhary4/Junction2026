"""The product catalog as ProductCards: the product file joined with delivery reliability and carbon footprint.

Live mode reads the full files in AIMO_DATA_DIR. Replay mode reads the recorded subset in contract/fixtures/valio/.
Search is local, never through the API: every name word must match, and only the most common category is kept.
"""

import csv
import io
import json
import os
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from functools import cache
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from contract.models import AllergenInfo, Claim, PackSize, ProductCard, SizePerSalesUnit
from merchant import valio_api

ROOT = Path(__file__).resolve().parent.parent
REPLAY_DIR = ROOT / "contract" / "fixtures" / "valio"
HELSINKI = ZoneInfo("Europe/Helsinki")
NAME_SIZES = {"L": {"ml": 0.001, "cl": 0.01, "dl": 0.1, "l": 1.0}, "KG": {"g": 0.001, "kg": 1.0}}  # "5 dl" in a name
LACTOSE_FREE_CLAIM = "FREE_FROM_LACTOSE"


def mode() -> Literal["live", "replay"]:
    value = os.environ.get("VALIO_MODE", "replay")
    if value not in ("live", "replay"):
        raise ValueError(f"VALIO_MODE must be live or replay, got {value!r}")
    return value


@dataclass(frozen=True)
class Catalog:
    products: dict[str, dict]  # raw records from the product file, by id
    reliability: dict[str, float]
    carbon: dict[str, float]
    as_of: datetime  # when the files were taken: their download time, or the recording time in replay

    def raw(self, product_id: str) -> dict | None:
        return self.products.get(product_id)

    def card(self, product_id: str) -> ProductCard:
        product = self.products[product_id]
        return ProductCard(
            id=product["id"],
            name=name(product),
            category=product["category"],
            vendor=product.get("vendorName"),
            brand=_synkka(product).get("brand") or None,
            sales_unit=product["salesUnit"],
            base_unit=product["baseUnit"],
            size_per_sales_unit=size_per_sales_unit(product),
            pack_sizes=[
                PackSize(unit_id=u["unitId"], size_in_base_units=round(u["sizeInBaseUnits"]))
                for u in product.get("units") or []
                if u["unitId"] != product["baseUnit"]
            ],
            temperature_condition=product.get("temperatureCondition"),
            allergens=allergens(product),
            nutritional_claims=_ids(product, "nutritionalClaim"),
            labels=[label for label in _ids(product, "packagingMarkedLabel") if not label.endswith("Temperature")],
            origin=self.origin(product),
            delivery_reliability=self.reliability_claim(product_id),
            carbon_footprint=self.carbon_claim(product_id),
            catalog_substitutes=[s["substituteProduct"] for s in product.get("substitutions") or []],
        )

    def search(self, query: str, limit: int) -> list[ProductCard]:
        """Products whose English or Finnish name has every word of the query, in the most common category,
        closest names first (fewest extra words)."""
        terms = query.lower().split()
        matches = []
        for product in self.products.values():
            hits = [n.lower() for n in names(product).values() if terms and all(t in n.lower() for t in terms)]
            if hits and not _deleted(product):
                extra = min(sum(not any(t in word for t in terms) for word in hit.split()) for hit in hits)
                matches.append((extra, product["id"], product["category"]))
        if not matches:
            return []
        top = Counter(category for _, _, category in matches).most_common(1)[0][0]
        ranked = sorted((extra, pid) for extra, pid, category in matches if category == top)
        return [self.card(pid) for _, pid in ranked[:limit]]

    def listed_substitutes(self, product_id: str) -> set[str]:
        """Valio's own suggestions, both ways: what this product lists, and what lists this product."""
        own = {s["substituteProduct"] for s in self.products[product_id].get("substitutions") or []}
        reverse = {
            p["id"]
            for p in self.products.values()
            if any(s["substituteProduct"] == product_id for s in p.get("substitutions") or [])
        }
        return (own | reverse) & set(self.products)

    def origin(self, product: dict) -> Claim:
        country = product.get("countryOfOrigin")
        if not country:
            return Claim(unit="country", source="none", as_of=self.as_of, certainty="unknown")
        return Claim(value=country.upper(), unit="country", source="gs1_synkka", as_of=self.as_of, certainty="declared")

    def reliability_claim(self, product_id: str) -> Claim:
        value = self.reliability.get(product_id)
        if value is None:
            return Claim(unit="share_delivered", source="none", as_of=self.as_of, certainty="unknown")
        return Claim(
            value=value, unit="share_delivered", source="aimo_delivery_history", as_of=self.as_of, certainty="measured"
        )

    def carbon_claim(self, product_id: str) -> Claim:
        value = self.carbon.get(product_id)
        if value is None:
            return Claim(unit="kg_co2e_per_kg", source="none", as_of=self.as_of, certainty="unknown")
        return Claim(
            value=value, unit="kg_co2e_per_kg", source="product_group_average", as_of=self.as_of, certainty="estimated"
        )


@cache
def load(which: Literal["live", "replay"] | None = None) -> Catalog:
    which = which or mode()
    folder = valio_api.data_dir() if which == "live" else REPLAY_DIR
    products = json.loads((folder / "products.json").read_bytes())
    if which == "live":
        as_of = datetime.fromtimestamp((folder / "products.json").stat().st_mtime, HELSINKI).replace(microsecond=0)
    else:
        as_of = datetime.fromisoformat((REPLAY_DIR / "frozen_now.txt").read_text(encoding="utf-8").strip())
    return Catalog(
        products={p["id"]: p for p in products},
        reliability=_table(folder / "delivery-reliability.csv"),
        carbon=_table(folder / "carbon-footprint.csv"),
        as_of=as_of,
    )


def name(product: dict) -> str:
    found = names(product)
    return found.get("en") or found.get("fi") or product["id"]


def names(product: dict) -> dict[str, str]:
    return {n["language"]: n["value"] for n in _synkka(product).get("names") or [] if n["language"] in ("en", "fi")}


def allergens(product: dict) -> AllergenInfo:
    """GS1 codes. Both lists empty means the data is missing, which never means 'free from'."""
    values = [v for key in ("allergen", "nonAllergen") for v in _classification(product, key)]
    contains = sorted({v["id"] for v in values if v.get("unit") == "CONTAINS"})
    free_from = sorted({v["id"] for v in values if v.get("unit") == "FREE_FROM"})
    return AllergenInfo(contains=contains, free_from=free_from, data="complete" if values else "missing")


def lactose_free(card: ProductCard) -> bool:
    """Declared lactose free, or no milk at all in complete allergen data (lactose only comes from milk)."""
    info = card.allergens
    declared = LACTOSE_FREE_CLAIM in card.nutritional_claims or "ML" in info.free_from
    no_milk = info.data == "complete" and not {"AM", "ML"} & set(info.contains)
    return declared or no_milk


def size_per_sales_unit(product: dict) -> SizePerSalesUnit:
    """Litres or kilos in one sales unit, from the product file alone. Quotes cross-check it with the price API.

    When the base unit is a piece, the size is read in the English name: "5 dl", "100x2 cl", "2,5dlx12". A pack
    count written next to the size is applied, unless one of the product's units already has that count: for
    "12x375g" sold by the box with 12 boxes to a carton, one box is 375 g.
    """
    units = {u["unitId"]: u["sizeInBaseUnits"] for u in product.get("units") or []}
    per_sales_unit = units.get(product["salesUnit"])
    if product["baseUnit"] in NAME_SIZES and per_sales_unit:
        return SizePerSalesUnit(
            value=per_sales_unit,
            unit=product["baseUnit"],
            how=f"{per_sales_unit:g} {product['baseUnit']} per {product['salesUnit']} in the product file",
        )
    name = names(product).get("en", "")
    for unit, sizes in NAME_SIZES.items():
        match = re.search(_name_size_pattern(sizes), name, re.IGNORECASE)
        if match and per_sales_unit:
            count = int(match["before"] or match["after"] or 1)
            if count in units.values():
                count = 1  # the units table already counts these packs
            size = count * float(match["number"].replace(",", ".")) * sizes[match["unit"].lower()] * per_sales_unit
            written = name[match.start("number") : match.end("unit")]
            packs = f"{count} x {written}" if count > 1 else written
            how = f"pack size in the name ({packs}) x {per_sales_unit:g} {product['baseUnit']}"
            return SizePerSalesUnit(value=round(size, 3), unit=unit, how=how)
    return SizePerSalesUnit(how="no pack size in the name")


def _name_size_pattern(sizes: dict[str, float]) -> str:
    """A size in a name, with the pack count written right before it ("100x2 cl") or right after it ("2,5dlx12").

    The unit may be glued to an "x12", but not to another letter or digit ("2 layers" is not 2 litres). A number
    after the "x" that is itself a measure ("2gx15mm") is not a pack count.
    """
    unit = "|".join(sizes)
    before = r"(?:(?<![\d.,])(?P<before>\d+)\s*x\s*)?"
    after = r"(?:\s*x\s*(?P<after>\d+)(?![\d.,]|\s*(?:mm|cm|m|ml|cl|dl|l|g|kg)\b))?"
    return rf"{before}(?P<number>\d+(?:[.,]\d+)?)\s*(?P<unit>{unit})(?=x\s*\d|[^a-z\d]|$){after}"


def _synkka(product: dict) -> dict:
    return product.get("synkkaData") or {}


def _classification(product: dict, key: str) -> list[dict]:
    for c in _synkka(product).get("classifications") or []:
        if c["name"] == key:
            return c.get("values") or []
    return []


def _ids(product: dict, key: str) -> list[str]:
    return [v["id"] for v in _classification(product, key) if v.get("id")]


def _deleted(product: dict) -> bool:
    return str(product.get("deleted")).lower() == "true"


def _table(path: Path) -> dict[str, float]:
    rows = list(csv.reader(io.StringIO(path.read_text(encoding="utf-8-sig"))))
    return {r[0]: float(r[1]) for r in rows[1:] if len(r) > 1 and r[1]}
