"""The gateway's memory: every quote it signed and every order it accepted, as JSON files under state/merchant/.

`state/` is ignored by git. The signed token is kept as issued: the order check compares mandates against exactly
what Valio signed.
"""

import os
import re
import uuid
from pathlib import Path

from pydantic import BaseModel

from contract.models import CheckoutResponse, Order

ROOT = Path(__file__).resolve().parent.parent
SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
CHECKOUTS, ORDERS = "checkouts", "orders"


def state_dir() -> Path:
    return Path(os.environ.get("AIMO_STATE_DIR") or ROOT / "state") / "merchant"


def save_checkout(response: CheckoutResponse) -> None:
    _save(CHECKOUTS, response.checkout_id, response)


def load_checkout(checkout_id: str) -> CheckoutResponse | None:
    return _load(CHECKOUTS, checkout_id, CheckoutResponse)


def save_order(order: Order) -> None:
    _save(ORDERS, order.order_id, order)


def load_order(order_id: str) -> Order | None:
    return _load(ORDERS, order_id, Order)


def order_for_checkout(checkout_id: str) -> Order | None:
    """The order a quote already led to, if any. A scan is enough: a demo run holds a handful of orders."""
    for path in sorted((state_dir() / ORDERS).glob("*.json")):
        order = Order.model_validate_json(path.read_text(encoding="utf-8"))
        if order.checkout_id == checkout_id:
            return order
    return None


def _save(folder: str, identifier: str, record: BaseModel) -> None:
    path = state_dir() / folder / f"{identifier}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    tmp.write_text(record.model_dump_json(exclude_none=True), encoding="utf-8")
    tmp.replace(path)


def _load[Record: BaseModel](folder: str, identifier: str, model: type[Record]) -> Record | None:
    """None for an unknown id, and for one that is not a plain id (it comes from the URL, it must not walk folders)."""
    if not SAFE_ID.match(identifier):
        return None
    path = state_dir() / folder / f"{identifier}.json"
    return model.model_validate_json(path.read_text(encoding="utf-8")) if path.exists() else None
