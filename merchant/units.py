"""What the buyer asked for (litres, kilos or sales units) into whole sales units, rounded up.

Two sources for the size of one sales unit: the product file (ProductCard.size_per_sales_unit) and the price API
(catalog price / comparison price, e.g. 31.31 EUR / 1.57 EUR per L = 19.94 L, rounded by the API).
The product file wins when both agree within 2 %, otherwise we trust the price, because Valio invoices on it.
"""

import math
from dataclasses import dataclass

from contract.models import SizePerSalesUnit

AGREEMENT = 0.02
EPSILON = 1e-9  # 1000 / 1.0 must give 1000 units, not 1001


class UnitError(ValueError):
    """The amount cannot be converted for this product, for example litres for a product sold by the kilo."""


@dataclass(frozen=True)
class Conversion:
    quantity: int  # sales units to order
    size: float  # buyer units in one sales unit
    how: str

    @property
    def base_quantity(self) -> float:
        return round(self.quantity * self.size, 3)


def size_for(unit: str, card_size: SizePerSalesUnit, price: dict | None) -> tuple[float, str]:
    """Buyer units in one sales unit, and how we know. `price` is the product's answer from /api/price."""
    if unit == "ST":
        return 1.0, "ordered in sales units"
    by_file = card_size.value if card_size.unit == unit and card_size.value else None
    by_price = None
    if price and price.get("comparisonUnit") == unit and (price.get("comparisonPrice") or {}).get("value"):
        by_price = price["catalogPrice"]["value"] / price["comparisonPrice"]["value"]
    if by_file and by_price:
        if abs(by_file - by_price) <= AGREEMENT * by_price:
            return by_file, f"{card_size.how}, confirmed by the price per {unit}"
        return round(by_price, 3), f"price / price per {unit} = {by_price:.3f}, the product file says {by_file:g}"
    if by_file:
        return by_file, card_size.how
    if by_price:
        return round(by_price, 3), f"price / price per {unit} = {by_price:.3f}"
    raise UnitError(f"no size in {unit} for this product")


def to_sales_units(amount: float, unit: str, card_size: SizePerSalesUnit, price: dict | None) -> Conversion:
    size, how = size_for(unit, card_size, price)
    return Conversion(quantity=math.ceil(amount / size - EPSILON), size=size, how=how)
