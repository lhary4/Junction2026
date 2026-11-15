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
from merchant import valio_api, valio_client
from merchant.catalog import HELSINKI, Catalog, lactose_free
from merchant.prospect import promo_for_checkout
from merchant.units import UnitError, to_sales_units
from trust.keys import MERCHANT_ID

MERCHANT = Merchant(id=MERCHANT_ID, name="Valio Aimo")
TERMS = Link(type="terms_of_service", url="https://example.com/tos")
MAX_VALIDITY = timedelta(hours=24)
PLENTY = 9_999_999_999  # what the mock answers for most Stock products: available, count not given
RELATED_CATEGORIES = {"10400": ("10402",), "10402": ("10400",)}  # milk drinks and plant-based drinks
TIERS = ("best", "better", "good")
MIN_NAME_WORD = 3  # shorter words ("l", "kg", "ca") say nothing about what a product is


class QuoteError(ValueError):
    """The request cannot become a quote. The message is safe to show the agent."""

    status_code = 422  # something in the request has to change


class QuoteUnavailable(QuoteError):
    """Valio could not be asked for prices and stock. Nothing is wrong with the request: it can be sent again."""

    status_code = 503


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
        return self._comparison()[0]

    @property
    def comparison_unit(self) -> str:
        return self._comparison()[1]

    def _comparison(self) -> tuple[int, str]:
        """The price per litre or kilo, and that unit. Valio leaves it out for some products (caster sugar 460325):
        then it is the price divided by the size in the product file, or failing that the price of one sales unit."""
        given = (self.price.get("comparisonPrice") or {}).get("value")
        if given and self.price.get("comparisonUnit"):
            return round(given * 100), self.price["comparisonUnit"]
        size = self.card.size_per_sales_unit
        if size.value and size.unit:
            return round(self.unit_price_minor / size.value), size.unit
        return self.unit_price_minor, self.card.sales_unit


def build_quote(request: QuoteRequest, catalog: Catalog | None = None) -> AimoCheckout:
    catalog = catalog or catalog_module.for_delivery(request.delivery_date)
    now = clock.now().astimezone(HELSINKI)
    known = [n.product_id for n in request.needs if catalog.raw(n.product_id)]
    try:
        answers = valio_client.fetch(known, request.delivery_date)
        builder = _Builder(request, catalog, answers, now)
        for need in request.needs:
            builder.add(need)  # ranking substitutes asks Valio again
    except valio_client.ReplayError as e:
        raise QuoteError(str(e)) from e
    except valio_api.ValioUnavailable as e:
        raise QuoteUnavailable(str(e)) from e
    return builder.checkout()


class _Builder:
    def __init__(self, request: QuoteRequest, catalog: Catalog, answers: valio_client.Answers, now: datetime):
        self.request, self.catalog, self.answers, self.now = request, catalog, answers, now
        self.line_items: list[LineItem] = []
        self.lines: dict[str, LineClaims] = {}
        self.shortfalls: list[Shortfall] = []
        self.alternatives: list[Alternative] = []
        self.closings: list[datetime] = []
        self.taken: dict[str, int] = {}  # sales units already on a line of this quote, by product id

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
        left = self._left(offer)
        quantity = conversion.quantity if left is None else min(conversion.quantity, math.floor(left))
        promo = (
            promo_for_checkout(
                self.request.customer,
                offer.card.id,
                offer.unit_price_minor,
                offer.comparison_price_minor,
            )
            if need.claim_promo
            else None
        )
        if quantity > 0:
            self._line(offer, quantity, round(quantity * conversion.size, 3), need.unit, promo=promo)
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
        # Valio's availableDate is the earliest day a product can come, not the day it comes: available on the 16th,
        # asked for the 19th, it is delivered on the 19th. Only a product that cannot come before pushes the date later.
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
                delivery_date=max([self.request.delivery_date, *dates]),
                closing_time=closing,
                lines=self.lines,
                shortfalls=self.shortfalls,
                alternatives=self.alternatives,
            ),
        )

    # ---------- one product ----------

    def _offer(self, product_id: str, answers: valio_client.Answers) -> tuple[Offer | None, str]:
        availability, price = answers.availability.get(product_id), answers.prices.get(product_id)
        cat_price = (price or {}).get("catalogPrice") or {}
        if not availability or not price or price.get("error") or cat_price.get("value") is None:
            return None, "not_found"
        schedule = availability.get("scheduleLines") or []
        if availability.get("salesBlock") or not schedule or any(s.get("salesBlock") for s in schedule):
            return None, "out_of_stock"
        if schedule[0]["availableAmount"] <= 0:
            return None, "out_of_stock"
        closing = _time(availability.get("closingTime"))
        if closing and closing <= self.now:
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

    def _line(
        self,
        offer: Offer,
        quantity: int,
        base_quantity: float,
        unit: str,
        replaces: ProductCard | None = None,
        promo: dict[str, int] | None = None,
    ):
        line_id = f"li-{len(self.line_items) + 1}"
        unit_price = promo["unit_price_minor"] if promo else offer.unit_price_minor
        comp_price = promo["comparison_price_minor"] if promo else offer.comparison_price_minor
        amount = quantity * unit_price
        self.line_items.append(
            LineItem(
                id=line_id,
                item=Item(id=offer.card.id, title=offer.card.name, price=unit_price),
                quantity=quantity,
                totals=_totals(amount),
            )
        )
        card = offer.card
        self.lines[line_id] = LineClaims(
            product_id=card.id,
            category=card.category,
            brand=card.brand,
            sales_unit=card.sales_unit,
            base_quantity=base_quantity,
            base_unit=unit,
            size_per_sales_unit=card.size_per_sales_unit,
            temperature_condition=card.temperature_condition,
            comparison_price_minor=comp_price,
            comparison_unit=offer.comparison_unit,
            substitute_for=SubstituteFor(
                product_id=replaces.id,
                name=replaces.name,
                category=replaces.category,
                allergens=replaces.allergens,
                brand=replaces.brand,
                sales_unit=replaces.sales_unit,
                base_unit=replaces.base_unit,
                size_per_sales_unit=replaces.size_per_sales_unit,
                temperature_condition=replaces.temperature_condition,
                nutritional_claims=replaces.nutritional_claims,
                labels=replaces.labels,
                origin=replaces.origin,
            )
            if replaces
            else None,
            logistic_model=offer.availability["logisticModel"],
            available_date=offer.available_date,
            closing_time=offer.closing_time,
            stock=self._stock_claim(offer),
            price=Claim(
                value=unit_price,
                unit="eur_minor_per_sales_unit",
                source="aimo_price_api",
                as_of=self.answers.as_of,
                certainty="measured",
            ),
            origin=card.origin,
            allergens=card.allergens,
            delivery_reliability=card.delivery_reliability,
            carbon_footprint=card.carbon_footprint,
            nutritional_claims=card.nutritional_claims,
            labels=card.labels,
            shelf_life_days=promo["shelf_life_days"] if promo else None,
            promo_discount_pct=promo["promo_discount_pct"] if promo else None,
            base_unit_price_minor=promo["base_unit_price_minor"] if promo else None,
        )
        if offer.closing_time:
            self.closings.append(offer.closing_time)
        self.taken[card.id] = self.taken.get(card.id, 0) + quantity

    def _left(self, offer: Offer) -> float | None:
        """Sales units still free once the lines already in this quote are served. None: Valio gives no count."""
        return None if offer.stock is None else offer.stock - self.taken.get(offer.card.id, 0)

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
            if need.substitute_with:
                raise QuoteError(f"{need.substitute_with} cannot replace {need.product_id} (offered: none)")
            return  # sales units of two products are not comparable
        original = self.catalog.card(need.product_id)
        options = self._rank(original, missing, need.unit)
        shown = [ranked[0] for ranked in options.values() if ranked]  # the first of each tier
        if need.substitute_with and need.substitute_with not in {offer.card.id for _, offer, _, _ in shown}:
            asked = [o for ranked in options.values() for o in ranked if o[1].card.id == need.substitute_with]
            if not asked:
                offered = ", ".join(offer.card.id for _, offer, _, _ in shown) or "none"
                raise QuoteError(f"{need.substitute_with} cannot replace {need.product_id} (offered: {offered})")
            shown.append(asked[0])
        best = shown[0][1].card.id if shown and shown[0][0] == "best" else None
        chosen_id = need.substitute_with or (best if self.request.allow_alternatives else None)
        for tier, offer, why, is_listed in shown:
            chosen = offer.card.id == chosen_id
            self.alternatives.append(
                Alternative(
                    for_product_id=original.id,
                    product_id=offer.card.id,
                    tier=tier,
                    comparison_price_minor=offer.comparison_price_minor,
                    comparison_unit=offer.comparison_unit,
                    why=why,
                    chosen=chosen,
                    catalog_listed=is_listed,
                )
            )
            if chosen:
                conversion = to_sales_units(missing, need.unit, offer.card.size_per_sales_unit, offer.price)
                self._line(offer, conversion.quantity, conversion.base_quantity, need.unit, replaces=original)

    def _rank(self, original: ProductCard, missing: float, unit: str) -> dict[str, list[tuple[str, Offer, str, bool]]]:
        """Every acceptable substitute, by tier, best first in each tier."""
        listed = self.catalog.listed_substitutes(original.id)
        related = RELATED_CATEGORIES.get(original.category, ())
        candidates = [
            pid
            for pid, product in self.catalog.products.items()
            if pid != original.id
            and not catalog_module._deleted(product)
            and pid not in {n.product_id for n in self.request.needs}
            and (product["category"] == original.category or product["category"] in related or pid in listed)
        ]
        answers = valio_client.fetch(candidates, self.request.delivery_date)
        by_tier: dict[str, list[tuple[tuple, Offer, str, bool]]] = {tier: [] for tier in TIERS}
        for pid in candidates:
            offer, _ = self._offer(pid, answers)
            if offer is None or not self._acceptable(original, offer, missing, unit):
                continue
            is_listed = pid in listed
            tier, why = _tier(original, offer.card, is_listed)
            # Valio's own suggestions first, then the closest name, then the cheapest per litre or kilo.
            order = (not is_listed, -_closeness(original.name, offer.card.name), offer.comparison_price_minor, pid)
            by_tier[tier].append((order, offer, why, is_listed))
        return {
            tier: [(tier, o, why, is_listed) for _, o, why, is_listed in sorted(found, key=lambda f: f[0])]
            for tier, found in by_tier.items()
        }

    def _acceptable(self, original: ProductCard, offer: Offer, missing: float, unit: str) -> bool:
        card = offer.card
        if offer.available_date > self.request.delivery_date or offer.comparison_unit != unit:
            return False
        if card.allergens.data != "complete" or set(original.allergens.free_from) & set(card.allergens.contains):
            return False
        if lactose_free(original) and not lactose_free(card):
            return False
        try:
            needed = to_sales_units(missing, unit, card.size_per_sales_unit, offer.price).quantity
        except UnitError:
            return False
        left = self._left(offer)
        return left is None or left >= needed


def _tier(original: ProductCard, candidate: ProductCard, listed: bool) -> tuple[str, str]:
    same_allergens = original.allergens.contains == candidate.allergens.contains
    source = ", listed as a substitute in the catalog" if listed else ""
    if candidate.category == original.category and same_allergens:
        return "best", f"same category, same declared allergens{source}"
    contains = ", ".join(candidate.allergens.contains) or "nothing"
    if candidate.category == original.category:
        return "better", f"same category, but contains {contains} instead of {', '.join(original.allergens.contains)}"
    return "good", f"related category {candidate.category}, contains {contains}{source}"


def _closeness(original: str, candidate: str) -> int:
    """How much two product names say the same thing: the words of each that the other one has.

    The cheapest product of a category is often another product altogether: for a squeaky cheese it was a cheddar
    cream, for a lingonberry jam an apple filling. A word may sit inside a longer one, so "lingonberry" and "jam"
    both count against "lingonberryjam". Pack sizes ("500g", "3kg") and words of one or two letters do not count.
    """
    ours, theirs = _name_words(original), _name_words(candidate)
    shared = lambda word, others: any(word in other or other in word for other in others)
    return sum(shared(word, theirs) for word in ours) + sum(shared(word, ours) for word in theirs)


def _name_words(name: str) -> set[str]:
    return {w for w in Catalog.words(name) if len(w) >= MIN_NAME_WORD and not any(c.isdigit() for c in w)}


def summary(checkout: AimoCheckout) -> str:
    """One readable line for the audit log, e.g. '1000 ST of 464306, 1010.00 EUR excl. tax'."""
    lines = " and ".join(
        f"{line.quantity} {checkout.aimo.lines[line.id].sales_unit} of {line.item.id}" for line in checkout.line_items
    )
    return f"{lines}, {checkout.total_minor() / 100:.2f} {checkout.currency} excl. tax"


def _totals(amount: int) -> list[Total]:
    return [Total(type="subtotal", amount=amount), Total(type="total", amount=amount)]


def _time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value).astimezone(HELSINKI) if value else None
