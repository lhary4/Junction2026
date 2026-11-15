"""Customer-specific Food-Waste & Overstock Prospect (Valio Aimo side).

Matches Valio Aimo's short-shelf-life and overstock warehouse lots against each
customer's contract pricing tier (purchasing volume) and culinary profile.
Prices computed here are enforced identically by `merchant/quotes.py` when a
checkout line claims a promotion (`Need.claim_promo = True`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from contract.models import BuyerUnit, ProspectItem, ProspectResponse
from merchant import catalog as catalog_module
from merchant import valio_client
from merchant.catalog import Catalog


@dataclass(frozen=True)
class CustomerProfile:
    customer_id: str
    name: str
    tier: str
    contract_discount_pct: int  # customer-specific contract discount off Valio catalog price
    interests: tuple[str, ...]
    cuisine_label: str


@dataclass(frozen=True)
class ProspectLot:
    lot_id: str
    product_id: str
    reason: str  # "short_shelf_life" | "overstock"
    shelf_life_days: int
    available_sales_units: int
    discount_pct: int
    tags: tuple[str, ...]
    portion_qty: float  # kg/L/ST per kitchen portion
    portion_label: str


CUSTOMERS: dict[str, CustomerProfile] = {
    "demo-restaurant-helsinki": CustomerProfile(
        customer_id="demo-restaurant-helsinki",
        name="Demo Restaurant Helsinki",
        tier="Partner Bistro (-5%)",
        contract_discount_pct=5,
        interests=("nordic_dairy", "herbs", "root_veg", "dairy"),
        cuisine_label="Modern Finnish bistro",
    ),
    "ravintola-demo": CustomerProfile(
        customer_id="ravintola-demo",
        name="Ravintola Demo",
        tier="Standard Bistro",
        contract_discount_pct=0,
        interests=("herbs", "nordic_dairy", "root_veg", "berries"),
        cuisine_label="Nordic seasonal bistro",
    ),
    "hotel-nordic-chain": CustomerProfile(
        customer_id="hotel-nordic-chain",
        name="Nordic Hotel Group",
        tier="Volume Contract (-12%)",
        contract_discount_pct=12,
        interests=("dairy", "bakery", "cheese", "nordic_dairy"),
        cuisine_label="High-volume hotel & banquet",
    ),
    "trattoria-napoli": CustomerProfile(
        customer_id="trattoria-napoli",
        name="Trattoria Napoli",
        tier="Partner Bistro (-5%)",
        contract_discount_pct=5,
        interests=("cheese", "cream", "italian", "dairy"),
        cuisine_label="Pizzeria & pasta kitchen",
    ),
}

PROSPECT_LOTS: tuple[ProspectLot, ...] = (
    ProspectLot(
        lot_id="lot-queso-8d",
        product_id="475742",
        reason="short_shelf_life",
        shelf_life_days=8,
        available_sales_units=36,  # 36 x 1 kg = 36 kg
        discount_pct=35,
        tags=("cheese", "italian", "dairy", "nordic_dairy"),
        portion_qty=0.16,
        portion_label="melted cheese / pizza / gratin portions",
    ),
    ProspectLot(
        lot_id="lot-dill-3d",
        product_id="460395",
        reason="short_shelf_life",
        shelf_life_days=3,
        available_sales_units=50,  # 50 x 0.1 kg = 5 kg fresh dill
        discount_pct=40,
        tags=("herbs", "nordic_dairy"),
        portion_qty=0.02,
        portion_label="salmon / potato / bistro garnish portions",
    ),
    ProspectLot(
        lot_id="lot-smetana-6d",
        product_id="476890",
        reason="short_shelf_life",
        shelf_life_days=6,
        available_sales_units=12,  # 12 x 2 kg = 24 kg
        discount_pct=30,
        tags=("nordic_dairy", "dairy", "seafood"),
        portion_qty=0.04,
        portion_label="bistro starter / sauce portions",
    ),
    ProspectLot(
        lot_id="lot-cream-10d",
        product_id="464194",
        reason="overstock",
        shelf_life_days=10,
        available_sales_units=24,  # 24 x 1 L = 24 L
        discount_pct=25,
        tags=("dairy", "cream", "bakery", "italian", "nordic_dairy"),
        portion_qty=0.05,
        portion_label="sauce / dessert portions",
    ),
    ProspectLot(
        lot_id="lot-cheddar-7d",
        product_id="474404",
        reason="short_shelf_life",
        shelf_life_days=7,
        available_sales_units=10,  # 10 x 1.5 kg = 15 kg
        discount_pct=32,
        tags=("cheese", "italian"),
        portion_qty=0.08,
        portion_label="gratin / loaded dish portions",
    ),
    ProspectLot(
        lot_id="lot-beetroot-14d",
        product_id="460837",
        reason="overstock",
        shelf_life_days=14,
        available_sales_units=30,  # 30 kg
        discount_pct=25,
        tags=("root_veg", "nordic_dairy"),
        portion_qty=0.12,
        portion_label="roasted root veg / soup portions",
    ),
)

LOTS_BY_PRODUCT: dict[str, ProspectLot] = {lot.product_id: lot for lot in PROSPECT_LOTS}


def customer_profile(customer: str) -> CustomerProfile:
    key = customer.strip().lower()
    if key in CUSTOMERS:
        return CUSTOMERS[key]
    return CustomerProfile(
        customer_id=customer,
        name=customer,
        tier="Standard",
        contract_discount_pct=0,
        interests=("nordic_dairy", "dairy", "cheese"),
        cuisine_label="General foodservice",
    )


def apply_customer_and_promo_price(
    catalog_price_minor: int,
    customer: str,
    discount_pct: int = 0,
) -> tuple[int, int]:
    """Return (contract_base_minor, promo_minor) for a customer."""
    profile = customer_profile(customer)
    contract_minor = round(catalog_price_minor * (100 - profile.contract_discount_pct) / 100)
    promo_minor = round(contract_minor * (100 - discount_pct) / 100)
    return contract_minor, promo_minor


def promo_for_checkout(
    customer: str,
    product_id: str,
    catalog_price_minor: int,
    comparison_price_minor: int,
) -> dict[str, int] | None:
    """Return signed quote overrides when a checkout line claims an active prospect lot."""
    lot = LOTS_BY_PRODUCT.get(product_id)
    if lot is None:
        return None
    contract_minor, promo_minor = apply_customer_and_promo_price(catalog_price_minor, customer, lot.discount_pct)
    _, comp_promo_minor = apply_customer_and_promo_price(comparison_price_minor, customer, lot.discount_pct)
    return {
        "base_unit_price_minor": contract_minor,
        "unit_price_minor": promo_minor,
        "comparison_price_minor": comp_promo_minor,
        "promo_discount_pct": lot.discount_pct,
        "shelf_life_days": lot.shelf_life_days,
    }


def _unit_and_qty(card, sales_units: int) -> tuple[float, BuyerUnit]:
    if card.size_per_sales_unit and card.size_per_sales_unit.unit in ("KG", "L"):
        return round(sales_units * card.size_per_sales_unit.value, 2), card.size_per_sales_unit.unit
    unit: BuyerUnit = card.base_unit if card.base_unit in ("KG", "L", "ST") else "ST"
    return float(sales_units), unit


def build_prospect(
    customer: str = "ravintola-demo",
    delivery_date: date = date(2026, 11, 19),
    catalog: Catalog | None = None,
) -> ProspectResponse:
    """Build a customer-specific prospect of discounted MHD & overstock lots."""
    profile = customer_profile(customer)
    catalog = catalog or catalog_module.for_delivery(delivery_date)
    lot_pids = [lot.product_id for lot in PROSPECT_LOTS if catalog.raw(lot.product_id)]
    answers = valio_client.fetch(lot_pids, delivery_date)

    items: list[ProspectItem] = []
    for lot in PROSPECT_LOTS:
        if not catalog.raw(lot.product_id):
            continue
        price = answers.prices.get(lot.product_id) or {}
        avail = answers.availability.get(lot.product_id) or {}
        cat_val = None if price.get("error") else (price.get("catalogPrice") or {}).get("value")
        if cat_val is None or avail.get("salesBlock"):
            continue
        card = catalog.card(lot.product_id)
        catalog_minor = round(float(cat_val) * 100)
        contract_minor, promo_minor = apply_customer_and_promo_price(catalog_minor, customer, lot.discount_pct)
        comp_val = (price.get("comparisonPrice") or {}).get("value")
        comp_promo_minor = None
        if comp_val is not None:
            _, comp_promo_minor = apply_customer_and_promo_price(round(float(comp_val) * 100), customer, lot.discount_pct)

        avail_qty, base_unit = _unit_and_qty(card, lot.available_sales_units)
        portions = max(1, round(avail_qty / lot.portion_qty))
        overlap = [tag for tag in lot.tags if tag in profile.interests]
        urgency = max(0.0, (15 - lot.shelf_life_days) * 0.6)
        score = round(len(overlap) * 10.0 + lot.discount_pct * 0.25 + urgency, 1)

        reasons: list[str] = []
        if overlap:
            reasons.append(f"Fits {profile.cuisine_label} ({', '.join(overlap[:2])})")
        if lot.reason == "short_shelf_life":
            reasons.append(f"{lot.shelf_life_days}-day shelf life — save from waste")
        else:
            reasons.append("Central warehouse overstock")
        if profile.contract_discount_pct > 0:
            reasons.append(f"Includes your -{profile.contract_discount_pct}% contract tier")

        items.append(
            ProspectItem(
                lot_id=lot.lot_id,
                product=card,
                reason=lot.reason,
                shelf_life_days=lot.shelf_life_days,
                available_sales_units=lot.available_sales_units,
                available_base_quantity=avail_qty,
                base_unit=base_unit,
                contract_price_minor=contract_minor,
                promo_price_minor=promo_minor,
                discount_pct=lot.discount_pct,
                savings_per_unit_minor=max(0, contract_minor - promo_minor),
                comparison_promo_minor=comp_promo_minor,
                comparison_unit=price.get("comparisonUnit"),
                estimated_portions=portions,
                portion_hint=f"~{portions} {lot.portion_label}",
                relevance_score=score,
                match_reasons=reasons,
            )
        )

    items.sort(key=lambda item: (-item.relevance_score, item.shelf_life_days, item.product.id))
    return ProspectResponse(
        customer=profile.customer_id,
        customer_name=profile.name,
        customer_tier=profile.tier,
        contract_discount_pct=profile.contract_discount_pct,
        delivery_date=delivery_date,
        as_of=answers.as_of,
        items=items,
    )
