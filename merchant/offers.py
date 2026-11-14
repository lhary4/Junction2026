"""Lookup: the products that match a query, each with its price, its stock and whether it can be ordered.

Informative and never signed: an agent compares offers here, then asks POST /checkouts for the quote that commits.
Search is local. Price and availability are asked from Valio for a shortlist only, the SHORTLIST best name matches,
in one call to each API: Valio forbids pricing the whole catalog and does not publish its rate limits.
Sorted: orderable first, then the offers whose counted stock covers the amount, then the cheapest per litre or kilo.
"""

from datetime import datetime

from common import clock
from contract.models import Claim, Offer, OfferQuantity, OffersRequest, OffersResponse, QuoteRequest
from merchant import catalog as catalog_module
from merchant import quotes, valio_api, valio_client
from merchant.catalog import HELSINKI, Catalog
from merchant.units import UnitError, to_sales_units

SHORTLIST = 100  # products priced per lookup: a tenth of what one Valio call accepts


class OffersError(ValueError):
    """The lookup cannot be answered. The message is safe to show the agent."""

    status_code = 422  # something in the request has to change


class OffersUnavailable(OffersError):
    """Valio could not be asked for prices and stock. Nothing is wrong with the request: it can be sent again."""

    status_code = 503


def find_offers(request: OffersRequest, catalog: Catalog | None = None) -> OffersResponse:
    catalog = catalog or catalog_module.for_delivery(request.delivery_date)
    matched = catalog.matches(request.q)
    shortlist = matched[:SHORTLIST]
    try:
        answers = valio_client.fetch(shortlist, request.delivery_date)
    except valio_client.ReplayError as e:
        raise OffersError(str(e)) from e
    except valio_api.ValioUnavailable as e:
        raise OffersUnavailable(str(e)) from e
    # A quote builder with no needs: only its rules for "can be ordered" and for the stock claim are used,
    # so the lookup and the signed quote can never disagree on them.
    no_needs = QuoteRequest.model_construct(customer="lookup", delivery_date=request.delivery_date, needs=[])
    rules = quotes._Builder(no_needs, catalog, answers, clock.now().astimezone(HELSINKI))
    offers = sorted((_offer(rules, product_id, request) for product_id in shortlist), key=_rank)
    shown = offers[: request.limit]
    return OffersResponse(
        query=request.q,
        delivery_date=request.delivery_date,
        amount=request.amount,
        unit=request.unit,
        as_of=answers.as_of,
        matched=len(matched),
        priced=len(shortlist),
        count=len(shown),
        offers=shown,
    )


def _offer(rules: quotes._Builder, product_id: str, request: OffersRequest) -> Offer:
    answers = rules.answers
    availability = answers.availability.get(product_id) or {}
    price = answers.prices.get(product_id) or {}
    schedule = availability.get("scheduleLines") or [{}]
    card = rules.catalog.card(product_id)
    found, reason = rules._offer(product_id, answers)
    to_order = None
    if found and request.amount:
        try:
            to_order = _to_order(found, request)
        except UnitError:
            reason = "unit_mismatch"  # litres asked for a product sold by the kilo, or the other way round
    return Offer(
        product=card,
        orderable=not reason,
        reason=reason or None,
        logistic_model=availability.get("logisticModel"),
        price=_money(price, "catalogPrice", "eur_minor_per_sales_unit", answers.as_of),
        comparison_price=_money(price, "comparisonPrice", "eur_minor_per_comparison_unit", answers.as_of),
        comparison_unit=price.get("comparisonUnit"),
        # A product that cannot be ordered states no stock: `reason` says why.
        stock=rules._stock_claim(found) if found else _unknown(card.sales_unit, answers.as_of),
        # The date is a promise (delivery reliability says how often it holds), the cut-off is Valio's own rule.
        available_date=_when(schedule[0].get("availableDate"), "date", "declared", answers.as_of),
        closing_time=_when(_iso(availability.get("closingTime")), "datetime", "measured", answers.as_of),
        to_order=to_order,
    )


def _to_order(found: quotes.Offer, request: OffersRequest) -> OfferQuantity:
    conversion = to_sales_units(request.amount, request.unit, found.card.size_per_sales_unit, found.price)
    return OfferQuantity(
        quantity=conversion.quantity,
        base_quantity=conversion.base_quantity,
        base_unit=request.unit,
        total_minor=conversion.quantity * found.unit_price_minor,
        how=conversion.how,
        stock_covers=None if found.stock is None else found.stock >= conversion.quantity,
    )


def _rank(offer: Offer) -> tuple:
    short = offer.to_order is not None and offer.to_order.stock_covers is False
    price = offer.comparison_price.value
    return (not offer.orderable, short, price is None, price or 0, offer.product.id)


def _money(price: dict, key: str, unit: str, as_of: datetime) -> Claim:
    value = None if price.get("error") else (price.get(key) or {}).get("value")
    if value is None:
        return _unknown(unit, as_of)
    return Claim(value=round(value * 100), unit=unit, source="aimo_price_api", as_of=as_of, certainty="measured")


def _when(value: str | None, unit: str, certainty: str, as_of: datetime) -> Claim:
    if not value:
        return _unknown(unit, as_of)
    return Claim(value=value, unit=unit, source="aimo_availability_api", as_of=as_of, certainty=certainty)


def _iso(valio_time: str | None) -> str | None:
    """Valio writes +0200, the contract writes +02:00, Helsinki time."""
    closing = quotes._time(valio_time)
    return closing.isoformat() if closing else None


def _unknown(unit: str, as_of: datetime) -> Claim:
    return Claim(unit=unit, source="none", as_of=as_of, certainty="unknown")
