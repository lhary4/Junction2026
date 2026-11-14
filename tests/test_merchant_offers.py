"""The gateway's lookup in replay mode: the search words, then prices and availability for the brief's sentence.

The clock is frozen at the recording time with AIMO_FROZEN_NOW, so no test reads the real time. The recorded
cut-off is Sunday 15/11 at 17:00: past it, every offer turns into a late delivery (one test moves the clock there).
"""

import unicodedata
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient

from contract.models import OffersRequest, OffersResponse
from merchant import catalog, offers, valio_api, valio_client
from merchant.app import app
from merchant.offers import OffersError, find_offers

FROZEN = "2026-11-14T13:29:07+02:00"  # contract/fixtures/valio/frozen_now.txt
MONDAY = "2026-11-16"
BRIEF = {"q": "lactose-free milk", "delivery_date": MONDAY, "amount": 1000, "unit": "L"}


@pytest.fixture(autouse=True)
def replay(monkeypatch):
    monkeypatch.setenv("VALIO_MODE", "replay")
    monkeypatch.setenv("AIMO_FROZEN_NOW", FROZEN)


def lookup(**params) -> OffersResponse:
    return find_offers(OffersRequest(**{"limit": 50} | params))


def by_id(response: OffersResponse) -> dict:
    return {offer.product.id: offer for offer in response.offers}


# ---------- Search words ----------


def test_hyphens_punctuation_and_case_do_not_count():
    found = catalog.load().matches("lactose free milk")
    # 34 milk drinks of the first recording, and one cheese of the restaurant's ("... cheese from cow's milk").
    assert len(found) == 35 and len(catalog.for_delivery(date(2026, 11, 16)).matches("lactose free milk")) == 34
    for query in ("lactose-free milk", "Lactose-Free MILK!", "milk, lactose free"):
        assert catalog.load().matches(query) == found
    assert "469386" in found  # "5 x Arla Lactose- and fatfree milkdrink 1 L Suomi ESL"


def test_finnish_letters_are_kept():
    whole_milks = catalog.load().matches("täysmaito")
    assert "464073" in whole_milks  # "Valio täysmaito 1 l laktoositon UHT"
    assert catalog.load().matches("TÄYSMAITO") == whole_milks
    assert catalog.load().matches(unicodedata.normalize("NFD", "täysmaito")) == whole_milks  # typed as a + dots
    assert catalog.load().matches("taysmaito") == []  # ä is a letter of its own, not an accented a


def test_whole_words_rank_before_parts_of_words():
    found = catalog.load().matches("oat")
    assert found.index("464320") < found.index("468319")  # "Oatly iKaffe Oat drink 1L" before "Oatly iKaffe 0,5L"


def test_every_category_is_kept():
    found = catalog.load().matches("drink")
    assert {catalog.load().raw(pid)["category"] for pid in found} == {"10400", "10402"}  # milk and plant-based drinks


def test_an_empty_query_matches_nothing():
    assert catalog.load().matches(" - ") == []


# ---------- The brief: "1,000 litres of lactose-free milk by Monday" ----------


def test_the_cheapest_orderable_milk_comes_first():
    found = lookup(**BRIEF)
    first = found.offers[0]
    assert first.product.id == "464306" and first.orderable and first.reason is None
    assert (first.comparison_price.value, first.comparison_unit) == (101, "L")
    assert (first.to_order.quantity, first.to_order.total_minor) == (1000, 101000)
    assert (found.matched, found.priced, found.count) == (34, 34, 34)
    assert found.binding is False and found.as_of == datetime.fromisoformat(FROZEN)


def test_every_fact_states_its_source_and_certainty():
    first = lookup(**BRIEF).offers[0]
    said = lambda claim: (claim.value, claim.source, claim.certainty)
    assert said(first.price) == (101, "aimo_price_api", "measured")
    assert said(first.stock) == ("not_given", "aimo_stock_count", "declared")  # the mock's 9999999999
    assert said(first.available_date) == (MONDAY, "aimo_availability_api", "declared")
    assert said(first.closing_time) == ("2026-11-15T17:00:00+02:00", "aimo_availability_api", "measured")
    assert first.closing_time.as_of == datetime.fromisoformat(FROZEN)
    assert first.product.carbon_footprint.certainty == "estimated"


def test_orderable_first_then_enough_stock_then_cheapest():
    shown = lookup(**BRIEF).offers
    orderable = [offer for offer in shown if offer.orderable]
    assert shown[: len(orderable)] == orderable and 0 < len(orderable) < len(shown)
    enough = [offer for offer in orderable if offer.to_order.stock_covers is not False]
    assert orderable[: len(enough)] == enough
    for group in (enough, orderable[len(enough) :], shown[len(orderable) :]):
        prices = [offer.comparison_price.value for offer in group]
        assert prices == sorted(prices)


def test_counted_stock_below_the_amount_is_said():
    arla = by_id(lookup(**BRIEF))["469363"]
    assert arla.orderable and (arla.stock.value, arla.stock.certainty) == (384, "measured")
    assert arla.to_order.quantity == 1000 and arla.to_order.stock_covers is False
    assert by_id(lookup(**BRIEF | {"amount": 300}))["469363"].to_order.stock_covers is True


def test_a_terminal_product_past_its_cut_off_is_not_orderable():
    novobox = by_id(lookup(**BRIEF))["463038"]
    assert (novobox.orderable, novobox.reason, novobox.logistic_model) == (False, "late_delivery", "Terminal")
    assert novobox.closing_time.value == "2026-11-12T15:00:00+02:00"
    assert novobox.comparison_price.value == 157  # still priced: the agent can say what it would have cost
    assert novobox.stock.certainty == "unknown" and novobox.to_order is None


def test_a_product_valio_cannot_deliver_is_out_of_stock():
    half_litre = by_id(lookup(**BRIEF))["464440"]  # no schedule line in the availability answer
    assert (half_litre.orderable, half_litre.reason) == (False, "out_of_stock")
    assert half_litre.available_date.certainty == "unknown" and half_litre.closing_time.value is None


def test_kilos_asked_for_a_product_sold_by_the_litre():
    milk = by_id(lookup(**BRIEF | {"unit": "KG"}))["464306"]
    assert (milk.orderable, milk.reason, milk.comparison_unit) == (False, "unit_mismatch", "L")
    assert milk.to_order is None and milk.price.value == 101


def test_sales_units_can_be_asked_directly():
    cartons = by_id(lookup(**BRIEF | {"amount": 12, "unit": "ST"}))["463038"]  # past its cut-off: no quantity
    milk = by_id(lookup(**BRIEF | {"amount": 12, "unit": "ST"}))["464306"]
    assert cartons.to_order is None and (milk.to_order.quantity, milk.to_order.total_minor) == (12, 1212)


def test_without_an_amount_there_is_nothing_to_order():
    found = lookup(q="lactose-free milk", delivery_date=MONDAY, limit=5)
    assert found.count == 5 and found.matched == 34
    assert found.offers[0].product.id == "464306" and all(offer.to_order is None for offer in found.offers)


def test_no_match_is_an_empty_list():
    found = lookup(q="caviar of the moon", delivery_date=MONDAY)
    assert (found.matched, found.priced, found.count, found.offers) == (0, 0, 0, [])


def test_another_date_is_refused_in_replay():
    with pytest.raises(OffersError, match="only has answers for delivery on 2026-11-16"):
        lookup(**BRIEF | {"delivery_date": "2026-11-17"})


def test_after_the_cut_off_nothing_is_orderable(monkeypatch):
    monkeypatch.setenv("AIMO_FROZEN_NOW", "2026-11-15T17:00:01+02:00")
    assert {offer.reason for offer in lookup(**BRIEF).offers} == {"late_delivery", "out_of_stock"}


# ---------- What Valio is asked ----------


def test_valio_is_only_asked_about_the_shortlist(monkeypatch):
    asked = []
    fetch = valio_client.fetch
    monkeypatch.setattr(offers, "SHORTLIST", 3)
    monkeypatch.setattr(valio_client, "fetch", lambda ids, day: asked.append(list(ids)) or fetch(ids, day))
    found = lookup(**BRIEF)
    assert asked == [catalog.load().matches("lactose-free milk")[:3]]  # one call, the three closest names
    assert (found.matched, found.priced, found.count) == (34, 3, 3)


def test_a_product_valio_does_not_price_is_not_found(monkeypatch):
    fetch = valio_client.fetch

    def without_a_price(ids, day):
        answers = fetch(ids, day)
        return valio_client.Answers(answers.availability, answers.prices | {"464306": {"error": True}}, answers.as_of)

    monkeypatch.setattr(valio_client, "fetch", without_a_price)
    found = lookup(**BRIEF)
    milk = by_id(found)["464306"]
    assert (milk.orderable, milk.reason) == (False, "not_found")
    assert milk.price.certainty == "unknown" and milk.price.value is None and milk.price.source == "none"
    assert found.offers[-1] == milk  # no price to compare: last


# ---------- HTTP ----------


def test_route_answers_the_brief():
    response = TestClient(app).get("/offers", params=BRIEF | {"limit": 5})
    found = OffersResponse.model_validate(response.json())
    assert response.status_code == 200 and found.count == len(found.offers) == 5
    assert found.offers[0].product.id == "464306" and found.offers[0].to_order.total_minor == 101000
    assert response.json()["binding"] is False


def test_route_refuses_with_a_readable_reason():
    client = TestClient(app)
    other_date = client.get("/offers", params=BRIEF | {"delivery_date": "2026-11-17"})
    assert other_date.status_code == 422
    assert other_date.json()["detail"] == "replay mode only has answers for delivery on 2026-11-16 or 2026-11-19"
    no_unit = client.get("/offers", params={"q": "milk", "delivery_date": MONDAY, "amount": 5})
    assert no_unit.status_code == 422 and "amount and unit go together" in no_unit.text
    assert client.get("/offers", params={"q": "milk"}).status_code == 422  # no delivery date
    assert client.get("/offers", params=BRIEF | {"colour": "blue"}).status_code == 422  # unknown parameter


def test_route_says_when_valio_does_not_answer(monkeypatch):
    def down(_ids, _day):
        raise valio_api.ValioUnavailable("Valio API POST /price: HTTP 500")

    monkeypatch.setattr(valio_client, "fetch", down)
    response = TestClient(app).get("/offers", params=BRIEF)
    assert response.status_code == 503 and response.json()["detail"] == "Valio API POST /price: HTTP 500"
