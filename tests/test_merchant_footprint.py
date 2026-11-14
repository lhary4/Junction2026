"""POST /footprint: the estimated carbon footprint of an order, and the greener alternatives (merchant/footprint.py).

Runs on the replay recordings: the butter and its margarine are both in the restaurant recording of 19/11.
"""

import pytest
from fastapi.testclient import TestClient

from contract.models import FootprintRequest, FootprintResponse
from merchant import catalog, footprint
from merchant.app import app

BUTTER, MARGARINE, CREAM, CRISPBREAD = "463437", "461904", "464194", "467958"


@pytest.fixture(autouse=True)
def replay(monkeypatch):
    monkeypatch.setenv("VALIO_MODE", "replay")
    catalog.load.cache_clear()
    yield
    catalog.load.cache_clear()


def ask(*needs) -> FootprintResponse:
    request = FootprintRequest(needs=[{"product_id": p, "amount": a, "unit": u} for p, a, u in needs])
    return footprint.footprint(request)


def test_weight_times_group_average_with_the_total():
    answer = ask((BUTTER, 6.45, "KG"), (CREAM, 3.75, "L"))
    butter, cream = answer.lines
    assert butter.kg == 6.45 and butter.factor.certainty == "estimated"
    assert butter.kg_co2e == round(6.45 * butter.factor.value, 2)
    assert cream.kg == 3.75  # one litre counts as one kilo
    assert answer.total_kg_co2e == round(butter.kg_co2e + cream.kg_co2e, 1)
    assert answer.binding is False and answer.review_every_days == 7


def test_sales_units_are_weighed_with_the_pack_size():
    (line,) = ask((CRISPBREAD, 6, "ST")).lines
    assert line.kg == pytest.approx(1.8)  # six packs of 300 g


def test_butter_gets_the_margarine_with_the_saving():
    (offer,) = ask((BUTTER, 6.45, "KG")).alternatives
    assert offer.alternative.id == MARGARINE
    assert offer.kg_co2e_after < offer.kg_co2e_before
    assert offer.saving_share >= footprint.MIN_SAVING
    assert catalog.lactose_free(offer.alternative)


def test_no_alternative_when_it_is_already_in_the_order():
    assert ask((BUTTER, 6.45, "KG"), (MARGARINE, 1, "KG")).alternatives == []


def test_an_alternative_that_adds_an_allergen_is_not_offered():
    cards = catalog.load()
    butter, margarine = cards.card(BUTTER), cards.card(MARGARINE)
    with_sesame = margarine.model_copy(
        update={"allergens": margarine.allergens.model_copy(update={"contains": ["AS"]})}
    )
    assert footprint.safe_swap(butter, margarine)
    assert not footprint.safe_swap(butter, with_sesame)
    missing = margarine.model_copy(update={"allergens": margarine.allergens.model_copy(update={"data": "missing"})})
    assert not footprint.safe_swap(butter, missing)


def test_the_route_refuses_an_unknown_product():
    client = TestClient(app)
    answer = client.post("/footprint", json={"needs": [{"product_id": "000000", "amount": 1, "unit": "KG"}]})
    assert answer.status_code == 422
    ok = client.post("/footprint", json={"needs": [{"product_id": BUTTER, "amount": 6.45, "unit": "KG"}]})
    assert ok.status_code == 200 and ok.json()["alternatives"][0]["alternative"]["id"] == MARGARINE
