"""The gateway when things go wrong: a stale clock, Valio's API down, one stock shared by two lines, odd pack names."""

from datetime import datetime

import pytest
import requests
from fastapi.testclient import TestClient

from contract.models import QuoteRequest
from merchant import catalog, valio_api
from merchant.app import app
from merchant.quotes import QuoteError, QuoteUnavailable, build_quote

RECORDED = "2026-11-14T13:29:07+02:00"  # contract/fixtures/valio/frozen_now.txt
MONDAY = "2026-11-16"
ARLA, ARLA_STOCK, VALIO = "469363", 384, "464306"  # the act 3 product, its recorded stock, its best substitute


@pytest.fixture(autouse=True)
def replay(monkeypatch, tmp_path):
    monkeypatch.setenv("VALIO_MODE", "replay")
    monkeypatch.delenv("AIMO_FROZEN_NOW", raising=False)
    monkeypatch.setenv("AIMO_STATE_DIR", str(tmp_path))


def quote(*needs):
    """Each need is (product id, litres) or (product id, litres, the substitute to use)."""
    keys = ("product_id", "amount", "substitute_with")
    needs = [dict(zip(keys, need)) | {"unit": "L"} for need in needs]
    return build_quote(QuoteRequest(customer="demo-hotel-chain", delivery_date=MONDAY, needs=needs))


def body(product_id=VALIO, amount=1000):
    need = {"product_id": product_id, "amount": amount, "unit": "L"}
    return {"customer": "demo-hotel-chain", "delivery_date": MONDAY, "needs": [need]}


# ---------- Clock ----------


def test_replay_quotes_at_the_recorded_time_whatever_the_real_time():
    checkout = quote((VALIO, 1000))
    assert checkout.aimo.issued_at == datetime.fromisoformat(RECORDED)
    assert checkout.expires_at == datetime.fromisoformat("2026-11-15T13:29:07+02:00")


def test_a_clock_set_after_the_cut_off_still_refuses(monkeypatch):
    monkeypatch.setenv("AIMO_FROZEN_NOW", "2026-11-15T18:00:00+02:00")  # one hour after the Sunday 17:00 cut-off
    with pytest.raises(QuoteError, match="late_delivery"):
        quote((VALIO, 1000))


# ---------- Valio's API does not answer (live mode) ----------


class Answer:
    def __init__(self, status_code=200, payload=None):
        self.status_code, self.payload = status_code, payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)

    def json(self):
        if self.payload is None:
            raise requests.JSONDecodeError("not JSON", "", 0)
        return self.payload


def live(monkeypatch, answer):
    """Live mode on the recorded catalog, with the network replaced by `answer` (an Answer, or an error to raise)."""

    def request(*_args, **_kwargs):
        if isinstance(answer, Exception):
            raise answer
        return answer

    recorded = catalog.load("replay")
    monkeypatch.setenv("VALIO_MODE", "live")
    monkeypatch.setenv("VALIO_AIMO_API_KEY", "test-key")
    monkeypatch.setattr(catalog, "load", lambda which=None: recorded)
    monkeypatch.setattr(valio_api.requests, "request", request)


@pytest.mark.parametrize(
    ("answer", "words"),
    [
        (requests.Timeout(), "no answer within 30 seconds"),
        (requests.ConnectionError(), "not reachable (ConnectionError)"),
        (Answer(429), "HTTP 429"),
        (Answer(500), "HTTP 500"),
        (Answer(200), "not JSON"),
    ],
)
def test_valio_api_failure_is_a_503_with_a_readable_cause(monkeypatch, answer, words):
    live(monkeypatch, answer)
    response = TestClient(app).post("/checkouts", json=body())
    assert response.status_code == 503
    assert words in response.json()["detail"] and "test-key" not in response.text


def test_missing_api_key_is_a_503_that_says_so(monkeypatch):
    live(monkeypatch, Answer(200, {"products": []}))
    monkeypatch.delenv("VALIO_AIMO_API_KEY")
    monkeypatch.setattr(valio_api, "_from_env_file", lambda _name: None)
    response = TestClient(app).post("/checkouts", json=body())
    assert response.status_code == 503 and "VALIO_AIMO_API_KEY is not set" in response.json()["detail"]


def test_a_request_valio_cannot_serve_stays_a_422():
    assert TestClient(app).post("/checkouts", json=body("000000")).status_code == 422
    with pytest.raises(QuoteError) as refused:
        quote(("000000", 10))
    assert not isinstance(refused.value, QuoteUnavailable)


# ---------- One stock, several lines ----------


def test_the_same_product_twice_never_sells_more_than_the_stock():
    checkout = quote((ARLA, 300), (ARLA, 300))
    arla = [line for line in checkout.line_items if line.item.id == ARLA]
    assert sum(line.quantity for line in arla) == ARLA_STOCK
    assert [s.missing_base_quantity for s in checkout.aimo.shortfalls] == [216]
    substitute = checkout.aimo.lines[checkout.line_items[-1].id]
    assert substitute.substitute_for.product_id == ARLA and substitute.base_quantity == 216


def test_stock_used_up_by_an_earlier_line_is_out_of_stock_for_the_next():
    checkout = quote((ARLA, 384), (ARLA, 100))
    assert [line.quantity for line in checkout.line_items if line.item.id == ARLA] == [ARLA_STOCK]
    assert checkout.aimo.shortfalls[0].reason == "out_of_stock"
    assert checkout.aimo.shortfalls[0].available_base_quantity == 0


def test_a_substitute_is_not_promised_twice_beyond_its_stock():
    """463380 has 698 units: enough to cover one shortfall of 400 L, not two."""
    cafe = "463380"
    first, second = (ARLA, 784, cafe), ("462775", 451, cafe)  # 384 and 51 in stock: 400 L missing each
    alone = quote(first)
    assert (alone.line_items[-1].item.id, alone.line_items[-1].quantity) == (cafe, 400)
    with pytest.raises(QuoteError, match=f"{cafe} cannot replace 462775"):
        quote(first, second)


# ---------- Pack sizes written in a name ----------


def product(name, sales_unit, base_unit, **units):
    """A minimal product record: `units` gives the size of each unit in base units, as the product file does."""
    return {
        "salesUnit": sales_unit,
        "baseUnit": base_unit,
        "units": [{"unitId": unit, "sizeInBaseUnits": size} for unit, size in units.items()],
        "synkkaData": {"names": [{"language": "en", "value": name}]},
    }


@pytest.mark.parametrize(
    ("record", "size", "unit"),
    [
        (product("Portion milk 100x2 cl lactose free", "KI", "KI", KI=1, PAL=114), 2.0, "L"),  # the case is the 100
        (product("Protein Oat Drink Choco 2,5dlx12", "KI", "ST", KI=12, ST=1), 3.0, "L"),  # 12 is the carton: once
        (product("Corn Flakes 12x375g", "ST", "ST", KI=12, ST=1), 0.375, "KG"),  # sold by the box, 12 to a carton
        (product("Yoghurt 4x125 g blueberry", "KI", "PAK", KI=6, PAK=1), 3.0, "KG"),  # 6 packs of 4 pots
        (product("Chicken cutlet 60 g x 90 / 5,4 kg", "KI", "KI", KI=1), 5.4, "KG"),  # the name gives the total too
        (product("Whole milk drink 1 L UHT", "ST", "ST", KI=12, ST=1), 1.0, "L"),
        (product("Cleaning tablets 2gx15mm 60pc", "PRK", "PRK", PRK=1), 0.002, "KG"),  # 15 mm is not a pack count
        (product("Sponge cake 2 layers", "ST", "ST", ST=1), None, None),
    ],
)
def test_pack_size_is_read_from_the_name_with_its_pack_count(record, size, unit):
    found = catalog.size_per_sales_unit(record)
    assert (found.value, found.unit) == (size, unit), found.how


def test_recorded_cards_agree_with_the_price_per_litre():
    """The three recorded products whose name carries a pack count now match catalog price / price per litre."""
    cards = catalog.load("replay")
    assert cards.card("463203").size_per_sales_unit.value == 2.0  # 15.09 EUR / 7.55 EUR per L
    assert cards.card("474686").size_per_sales_unit.value == 3.0
    assert cards.card("474929").size_per_sales_unit.value == 3.0


def test_quote_builder_guards_closing_at_now_and_st_substitute_with():
    from datetime import date, datetime
    from zoneinfo import ZoneInfo

    from contract.models import Need, QuoteRequest
    from merchant import quotes, valio_client

    now = datetime(2026, 11, 14, 13, 15, tzinfo=ZoneInfo("Europe/Helsinki"))
    req = QuoteRequest(
        customer="demo",
        delivery_date=date(2026, 11, 16),
        needs=[Need(product_id="469363", amount=2, unit="L")],
    )
    cards = catalog.load("replay")

    # closingTime == now should be rejected as late_delivery
    answers_at_cutoff = valio_client.Answers(
        availability={"469363": {"logisticModel": "Stock", "scheduleLines": [{"availableAmount": 10, "availableDate": "2026-11-16"}], "closingTime": now.isoformat()}},
        prices={"469363": {"catalogPrice": {"value": 2.48}, "comparisonPrice": {"value": 2.48}, "comparisonUnit": "L"}},
        as_of=now,
    )
    builder = quotes._Builder(req, cards, answers_at_cutoff, now)
    offer_cutoff, reason_cutoff = builder._offer("469363", answers_at_cutoff)
    assert offer_cutoff is None and reason_cutoff == "late_delivery"

    # substitute_with on unit == "ST" must raise QuoteError instead of being silently ignored
    req_st = QuoteRequest(
        customer="demo",
        delivery_date=date(2026, 11, 16),
        needs=[Need(product_id="469363", amount=2, unit="ST", substitute_with="464201")],
    )
    builder_st = quotes._Builder(req_st, cards, answers_at_cutoff, now)
    with pytest.raises(quotes.QuoteError, match="cannot replace"):
        builder_st._cover(req_st.needs[0], 2.0)
