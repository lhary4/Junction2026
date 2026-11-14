"""A QuoteRequest becomes a signed AimoCheckout: the gateway states every fact, the agent decides none.

For each need: price and availability of the product, converted into sales units. When stock is short, the line
takes what there is and a shortfall says what is missing. Then up to three alternatives are ranked, one per tier:
  best    same category, same allergens
  better  same category, other allergens
  good    a related category (plant-based drinks for milk drinks)
Valio's own listed substitutes come first in a tier, then the cheapest per litre or kilo. A substitute is only
offered if it arrives on time, covers the whole shortfall, has complete allergen data, and keeps every free-from
promise of the original (lactose free stays lactose free). The best one is chosen, unless the buyer named another
with `substitute_with`, or turned alternatives off.
"""

import math
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from common import clock
from contract.ap2 import Item, LineItem, Link, Merchant, Status, Total
from contract.models import (
    AimoCheckout,
    AimoExtension,
    Alternative,
    Claim,
    LineClaims,
    Need,
    ProductCard,
    QuoteRequest,
    Shortfall,
    SubstituteFor,
)
from merchant import catalog as catalog_module
from merchant import valio_client
from merchant.catalog import HELSINKI, Catalog, lactose_free
from merchant.units import UnitError, to_sales_units
from trust.keys import MERCHANT_ID

MERCHANT = Merchant(id=MERCHANT_ID, name="Valio Aimo")
TERMS = Link(type="terms_of_service", url="https://example.com/tos")
MAX_VALIDITY = timedelta(hours=24)
PLENTY = 9_999_999_999  # what the mock answers for most Stock products: available, count not given
RELATED_CATEGORIES = {"10400": ("10402",), "10402": ("10400",)}  # milk drinks and plant-based drinks
TIERS = ("best", "better", "good")


class QuoteError(ValueError):
    """The request cannot become a quote. The message is safe to show the agent."""


@dataclass(frozen=True)
class Offer:
    """One product Valio can deliver, with everything a line needs."""

    card: ProductCard
    availability: dict
    price: dict
    stock: float | None  # sales units, None when Valio does not give a count
    available_date: date
    closing_time: datetime | None

    @property
    def unit_price_minor(self) -> int:
        return round(self.price["catalogPrice"]["value"] * 100)

    @property
    def comparison_price_minor(self) -> int:
        return round(self.price["comparisonPrice"]["value"] * 100)


def build_quote(request: QuoteRequest, catalog: Catalog | None = None) -> AimoCheckout:
    catalog = catalog or catalog_module.load()
    now = clock.now().astimezone(HELSINKI)
    known = [n.product_id for n in request.needs if catalog.raw(n.product_id)]
    try:
        answers = valio_client.fetch(known, request.delivery_date)
    except valio_client.ReplayError as e:
        raise QuoteError(str(e)) from e
    builder = _Builder(request, catalog, answers, now)
    for need in request.needs:
        builder.add(need)
    return builder.checkout()


class _Builder:
    def __init__(self, request: QuoteRequest, catalog: Catalog, answers: valio_client.Answers, now: datetime):
        self.request, self.catalog, self.answers, self.now = request, catalog, answers, now
        self.line_items: list[LineItem] = []
        self.lines: dict[str, LineClaims] = {}
        self.shortfalls: list[Shortfall] = []
        self.alternatives: list[Alternative] = []
        self.closings: list[datetime] = []

    def add(self, need: Need):
        if not self.catalog.raw(need.product_id):
            self._shortfall(need, 0.0, "not_found")
            return
        offer, reason = self._offer(need.product_id, self.answers)
        if offer is None:
            self._shortfall(need, 0.0, reason)
            self._cover(need, need.amount)
            return
        try:
            conversion = to_sales_units(need.amount, need.unit, offer.card.size_per_sales_unit, offer.price)
        except UnitError as e:
            raise QuoteError(f"{need.product_id}: {e}") from e
        quantity = conversion.quantity if offer.stock is None else min(conversion.quantity, math.floor(offer.stock))
        if quantity > 0:
            self._line(offer, quantity, round(quantity * conversion.size, 3), need.unit)
        covered = quantity * conversion.size
        if covered < need.amount - 1e-9:
            self._shortfall(need, covered, "partial_stock" if quantity else "out_of_stock")
            self._cover(need, round(need.amount - covered, 3))

    def checkout(self) -> AimoCheckout:
        if not self.line_items:
            missing = ", ".join(f"{s.product_id} ({s.reason})" for s in self.shortfalls)
            raise QuoteError(f"nothing can be quoted: {missing}")
        total = sum(item.totals[-1].amount for item in self.line_items)
        closing = min(self.closings) if self.closings else None
        expires = min([self.now + MAX_VALIDITY] + ([closing] if closing else []))
        dates = [line.available_date for line in self.lines.values() if line.available_date]
        return AimoCheckout(
            id=f"chk_{uuid.uuid4().hex[:8]}",
            merchant=MERCHANT,
            status=Status.ready_for_complete,
            currency="EUR",
            line_items=self.line_items,
            totals=_totals(total),
            links=[TERMS],
            expires_at=expires,
            aimo=AimoExtension(
                customer=self.request.customer,
                issued_at=self.now,
                requested=self.request.needs,
                requested_delivery_date=self.request.delivery_date,
                delivery_date=max(dates, default=self.request.delivery_date),
                closing_time=closing,
                lines=self.lines,
                shortfalls=self.shortfalls,
                alternatives=self.alternatives,
            ),
        )

    # ---------- one product ----------

    def _offer(self, product_id: str, answers: valio_client.Answers) -> tuple[Offer | None, str]:
        availability, price = answers.availability.get(product_id), answers.prices.get(product_id)
        if not availability or not price or price.get("error") or not price.get("catalogPrice"):
            return None, "not_found"
        schedule = availability.get("scheduleLines") or []
        if availability.get("salesBlock") or not schedule or any(s.get("salesBlock") for s in schedule):
            return None, "out_of_stock"
        if schedule[0]["availableAmount"] <= 0:
            return None, "out_of_stock"
        closing = _time(availability.get("closingTime"))
        if closing and closing < self.now:
            return None, "late_delivery"
        amount = schedule[0]["availableAmount"]
        stock = amount if availability.get("logisticModel") == "Stock" and amount < PLENTY else None
        offer = Offer(
            card=self.catalog.card(product_id),
            availability=availability,
            price=price,
            stock=stock,
            available_date=date.fromisoformat(schedule[0]["availableDate"]),
            closing_time=closing,
        )
        return offer, ""

    def _line(self, offer: Offer, quantity: int, base_quantity: float, unit: str, replaces: ProductCard | None = None):
        line_id = f"li-{len(self.line_items) + 1}"
        amount = quantity * offer.unit_price_minor
        self.line_items.append(
            LineItem(
                id=line_id,
                item=Item(id=offer.card.id, title=offer.card.name, price=offer.unit_price_minor),
                quantity=quantity,
                totals=_totals(amount),
            )
        )
        card = offer.card
        self.lines[line_id] = LineClaims(
            product_id=card.id,
            category=card.category,
            sales_unit=card.sales_unit,
            base_quantity=base_quantity,
            base_unit=unit,
            comparison_price_minor=offer.comparison_price_minor,
            comparison_unit=offer.price["comparisonUnit"],
            substitute_for=SubstituteFor(
                product_id=replaces.id, name=replaces.name, category=replaces.category, allergens=replaces.allergens
            )
            if replaces
            else None,
            logistic_model=offer.availability["logisticModel"],
            available_date=offer.available_date,
            closing_time=offer.closing_time,
            stock=self._stock_claim(offer),
            price=Claim(
                value=offer.unit_price_minor,
                unit="eur_minor_per_sales_unit",
                source="aimo_price_api",
                as_of=self.answers.as_of,
                certainty="measured",
            ),
            origin=card.origin,
            allergens=card.allergens,
            delivery_reliability=card.delivery_reliability,
            carbon_footprint=card.carbon_footprint,
            labels=card.labels,
        )
        if offer.closing_time:
            self.closings.append(offer.closing_time)

    def _stock_claim(self, offer: Offer) -> Claim:
        unit, as_of = offer.card.sales_unit, self.answers.as_of
        if offer.availability["logisticModel"] == "Terminal":
            return Claim(unit=unit, source="supplier_warehouse", as_of=as_of, certainty="unknown")
        if offer.stock is None:  # Valio says it can deliver but gives no count
            return Claim(value="not_given", unit=unit, source="aimo_stock_count", as_of=as_of, certainty="declared")
        return Claim(value=offer.stock, unit=unit, source="aimo_stock_count", as_of=as_of, certainty="measured")

    def _shortfall(self, need: Need, covered: float, reason: str):
        self.shortfalls.append(
            Shortfall(
                product_id=need.product_id,
                requested_base_quantity=need.amount,
                available_base_quantity=round(covered, 3),
                missing_base_quantity=round(need.amount - covered, 3),
                base_unit=need.unit,
                reason=reason,
            )
        )

    # ---------- alternatives ----------

    def _cover(self, need: Need, missing: float):
        """Rank alternatives for what is missing, then add the chosen one as a substitute line."""
        if need.unit == "ST" or not self.catalog.raw(need.product_id):
            return  # sales units of two products are not comparable
        original = self.catalog.card(need.product_id)
        options = self._rank(original, missing, need.unit)
        shown = [ranked[0] for ranked in options.values() if ranked]  # the first of each tier
        if need.substitute_with and need.substitute_with not in {offer.card.id for _, offer, _ in shown}:
            asked = [o for ranked in options.values() for o in ranked if o[1].card.id == need.substitute_with]
            if not asked:
                offered = ", ".join(offer.card.id for _, offer, _ in shown) or "none"
                raise QuoteError(f"{need.substitute_with} cannot replace {need.product_id} (offered: {offered})")
            shown.append(asked[0])
        best = shown[0][1].card.id if shown and shown[0][0] == "best" else None
        chosen_id = need.substitute_with or (best if self.request.allow_alternatives else None)
        for tier, offer, why in shown:
            chosen = offer.card.id == chosen_id
            self.alternatives.append(
                Alternative(
                    for_product_id=original.id,
                    product_id=offer.card.id,
                    tier=tier,
                    comparison_price_minor=offer.comparison_price_minor,
                    comparison_unit=offer.price["comparisonUnit"],
                    why=why,
                    chosen=chosen,
                )
            )
            if chosen:
                conversion = to_sales_units(missing, need.unit, offer.card.size_per_sales_unit, offer.price)
                self._line(offer, conversion.quantity, conversion.base_quantity, need.unit, replaces=original)

    def _rank(self, original: ProductCard, missing: float, unit: str) -> dict[str, list[tuple[str, Offer, str]]]:
        """Every acceptable substitute, by tier, best first in each tier."""
        listed = self.catalog.listed_substitutes(original.id)
        related = RELATED_CATEGORIES.get(original.category, ())
        candidates = [
            pid
            for pid, product in self.catalog.products.items()
            if pid != original.id
            and pid not in {n.product_id for n in self.request.needs}
            and (product["category"] == original.category or product["category"] in related or pid in listed)
        ]
        answers = valio_client.fetch(candidates, self.request.delivery_date)
        by_tier: dict[str, list[tuple[tuple, Offer, str]]] = {tier: [] for tier in TIERS}
        for pid in candidates:
            offer, _ = self._offer(pid, answers)
            if offer is None or not self._acceptable(original, offer, missing, unit):
                continue
            tier, why = _tier(original, offer.card, pid in listed)
            by_tier[tier].append(((pid not in listed, offer.comparison_price_minor, pid), offer, why))
        return {
            tier: [(tier, o, why) for _, o, why in sorted(found, key=lambda f: f[0])] for tier, found in by_tier.items()
        }

    def _acceptable(self, original: ProductCard, offer: Offer, missing: float, unit: str) -> bool:
        card = offer.card
        if offer.available_date > self.request.delivery_date or offer.price.get("comparisonUnit") != unit:
            return False
        if card.allergens.data != "complete" or set(original.allergens.free_from) & set(card.allergens.contains):
            return False
        if lactose_free(original) and not lactose_free(card):
            return False
        try:
            needed = to_sales_units(missing, unit, card.size_per_sales_unit, offer.price).quantity
        except UnitError:
            return False
        return offer.stock is None or offer.stock >= needed


def _tier(original: ProductCard, candidate: ProductCard, listed: bool) -> tuple[str, str]:
    same_allergens = original.allergens.contains == candidate.allergens.contains
    source = ", listed as a substitute in the catalog" if listed else ""
    if candidate.category == original.category and same_allergens:
        return "best", f"same category, same declared allergens{source}"
    contains = ", ".join(candidate.allergens.contains) or "nothing"
    if candidate.category == original.category:
        return "better", f"same category, but contains {contains} instead of {', '.join(original.allergens.contains)}"
    return "good", f"related category {candidate.category}, contains {contains}{source}"


def _totals(amount: int) -> list[Total]:
    return [Total(type="subtotal", amount=amount), Total(type="total", amount=amount)]


def _time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value).astimezone(HELSINKI) if value else None
