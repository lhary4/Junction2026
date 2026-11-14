"""The carbon footprint of an order, and at most two greener products for its recurring lines.

POST /footprint takes the lines a kitchen is about to order, in its own units, and answers:
- for each line, its weight in kilos times the footprint of its product group (data/carbon-footprint.csv, in kg CO2e
  per kg). Both are estimates: the answer says so, and it is never part of the signed quote.
- the total, over the lines whose footprint is known. A line with no footprint is listed in `unknown`, never counted
  as zero.
- greener alternatives, from a short list of pairs Valio checked in a kitchen (ECO_PAIRS). A pair is only offered
  when the rules below hold on today's data, so a pair that stops being greener, or safe, disappears by itself.

How often the buyer's agent asks is the buyer's choice. The answer suggests once a week (REVIEW_EVERY_DAYS): a menu
changes slowly, and a chef asked about the same swap every day stops reading.
"""

from dataclasses import dataclass

from contract.models import EcoAlternative, FootprintRequest, FootprintResponse, LineFootprint, Need, ProductCard
from merchant import catalog as catalog_module
from merchant.catalog import Catalog, lactose_free

MAX_ALTERNATIVES = 2  # a chef reads one or two suggestions, not a list
MIN_SAVING = 0.25  # below a quarter less CO2e, the change is not worth asking a chef about
REVIEW_EVERY_DAYS = 7
METHOD = (
    "Weight x the average footprint of the product group (kg CO2e per kg). "
    "One litre counts as one kilo. Estimates for comparison, not a measured footprint."
)


@dataclass(frozen=True)
class EcoPair:
    original: str
    alternative: str
    why: str


# Pairs that do the same job in the dish, checked in a kitchen. The rules in `_offer` still decide each time.
ECO_PAIRS = (
    EcoPair(
        original="463437",  # Valio Eila butter 500 g, salted, lactose free
        alternative="461904",  # Sunnuntai lactose-free margarine for baking 500 g
        why="Same 500 g block, lactose free, made for cooking and baking: it melts and browns like butter in the "
        "mash, the reindeer and the crumble. The mash tastes a little less of butter.",
    ),
)


class FootprintError(ValueError):
    """A product the gateway does not know. The message is safe to show the agent."""

    status_code = 422


def footprint(request: FootprintRequest, catalog: Catalog | None = None) -> FootprintResponse:
    catalog = catalog or catalog_module.load()
    unknown_ids = [need.product_id for need in request.needs if catalog.raw(need.product_id) is None]
    if unknown_ids:
        raise FootprintError(f"unknown product ids: {', '.join(unknown_ids)}")
    lines = [_line(catalog.card(need.product_id), need) for need in request.needs]
    in_order = {need.product_id for need in request.needs}
    offers = [
        offer
        for need, line in zip(request.needs, lines)
        if (offer := _offer(catalog, need, line, in_order)) is not None
    ]
    offers.sort(key=lambda offer: -offer.saving_kg_co2e)
    return FootprintResponse(
        as_of=catalog.as_of,
        method=METHOD,
        total_kg_co2e=round(sum(line.kg_co2e for line in lines if line.kg_co2e is not None), 1),
        unknown=[line.product_id for line in lines if line.kg_co2e is None],
        lines=lines,
        review_every_days=REVIEW_EVERY_DAYS,
        alternatives=offers[:MAX_ALTERNATIVES],
    )


def kilos(card: ProductCard, amount: float, unit: str) -> float | None:
    """The weight of `amount` of this product. Sales units are weighed with the pack size of the product file."""
    if unit == "KG":
        return amount
    if unit == "L":
        return amount  # one litre counts as one kilo: dairy is within a few percent of it
    size = card.size_per_sales_unit
    if size.value and size.unit in ("KG", "L"):
        return amount * size.value
    return None


def _line(card: ProductCard, need: Need) -> LineFootprint:
    kg = kilos(card, need.amount, need.unit)
    factor = card.carbon_footprint
    known = kg is not None and isinstance(factor.value, (int, float))
    return LineFootprint(
        product_id=card.id,
        name=card.name,
        amount=need.amount,
        unit=need.unit,
        kg=None if kg is None else round(kg, 3),
        factor=factor,
        kg_co2e=round(kg * factor.value, 2) if known else None,
    )


def _offer(catalog: Catalog, need: Need, line: LineFootprint, in_order: set[str]) -> EcoAlternative | None:
    """The listed alternative of this line, when every rule holds on today's data. Otherwise nothing."""
    pair = next((pair for pair in ECO_PAIRS if pair.original == need.product_id), None)
    if pair is None or pair.alternative in in_order or catalog.raw(pair.alternative) is None:
        return None
    if line.kg is None or line.kg_co2e is None:
        return None
    original, alternative = catalog.card(need.product_id), catalog.card(pair.alternative)
    factor = alternative.carbon_footprint.value
    if not isinstance(factor, (int, float)):
        return None  # unknown is never read as low
    if not safe_swap(original, alternative):
        return None
    after = round(line.kg * factor, 2)
    saving = round(line.kg_co2e - after, 2)
    share = saving / line.kg_co2e if line.kg_co2e else 0.0
    if share < MIN_SAVING:
        return None
    return EcoAlternative(
        product_id=original.id,
        name=original.name,
        amount=need.amount,
        unit=need.unit,
        alternative=alternative,
        kg_co2e_before=line.kg_co2e,
        kg_co2e_after=after,
        saving_kg_co2e=saving,
        saving_share=round(share, 3),
        why=pair.why,
    )


def safe_swap(original: ProductCard, alternative: ProductCard) -> bool:
    """The alternative adds no allergen and keeps a lactose-free promise. Missing allergen data is never safe."""
    if alternative.allergens.data != "complete":
        return False
    if not set(alternative.allergens.contains) <= set(original.allergens.contains):
        return False
    return lactose_free(alternative) or not lactose_free(original)
