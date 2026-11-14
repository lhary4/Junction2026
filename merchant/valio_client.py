"""Price and availability for a shortlist: live from the Valio APIs, or replayed from contract/fixtures/valio/.

VALIO_MODE=live or replay (default replay). Replay only knows the recorded products and the recorded delivery date.
"""

import json
from dataclasses import dataclass
from datetime import date, datetime
from functools import cache

from common import clock
from merchant import valio_api
from merchant.catalog import REPLAY_DIR, mode


class ReplayError(ValueError):
    """Replay mode was asked for something that was not recorded."""


@dataclass(frozen=True)
class Answers:
    availability: dict[str, dict]  # by product id, the raw /api/availability entry
    prices: dict[str, dict]  # by product id, the raw /api/price entry
    as_of: datetime  # when Valio gave these answers


def fetch(product_ids: list[str], requested_date: date) -> Answers:
    ids = sorted(set(product_ids))
    if not ids:
        return Answers({}, {}, clock.now())
    if mode() == "replay":
        return _replay(ids, requested_date)
    as_of = clock.now()
    availability, prices = {}, {}
    for start in range(0, len(ids), valio_api.MAX_PRODUCTS_PER_CALL):
        chunk = ids[start : start + valio_api.MAX_PRODUCTS_PER_CALL]
        availability |= _by_id(valio_api.availability(chunk, requested_date.isoformat()))
        prices |= _by_id(valio_api.price(chunk, requested_date.isoformat()))
    return Answers(availability, prices, as_of)


def _replay(ids: list[str], requested_date: date) -> Answers:
    recorded = _recorded()
    if requested_date.isoformat() != recorded["date"]:
        raise ReplayError(f"replay mode only has answers for delivery on {recorded['date']}")
    pick = lambda answers: {i: answers[i] for i in ids if i in answers}
    return Answers(pick(recorded["availability"]), pick(recorded["prices"]), recorded["as_of"])


@cache
def _recorded() -> dict:
    read = lambda name: json.loads((REPLAY_DIR / name).read_text(encoding="utf-8"))
    return {
        "date": read("request.json")["requestedDate"],
        "availability": _by_id(read("availability.json")),
        "prices": _by_id(read("price.json")),
        "as_of": datetime.fromisoformat((REPLAY_DIR / "frozen_now.txt").read_text(encoding="utf-8").strip()),
    }


def _by_id(answer: dict) -> dict[str, dict]:
    return {entry["productId"]: entry for entry in answer["products"]}
