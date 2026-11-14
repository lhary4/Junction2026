"""The gateway, part 1, in replay mode: search cards and signed quotes for the demo acts, on the recorded answers."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from contract.models import CheckoutResponse, QuoteRequest, SearchResponse
from merchant import catalog
from merchant.app import app
from merchant.quotes import QuoteError, build_quote
from merchant.units import to_sales_units
from trust.checkout import verify_checkout
from trust.keys import public_jwks

FROZEN = "2026-11-14T13:29:07+02:00"  # contract/fixtures/valio/frozen_now.txt
MONDAY = "2026-11-16"


@pytest.fixture(autouse=True)
def replay(monkeypatch, tmp_path):
    monkeypatch.setenv("VALIO_MODE", "replay")
    monkeypatch.setenv("AIMO_FROZEN_NOW", FROZEN)
    monkeypatch.setenv("AIMO_STATE_DIR", str(tmp_path))


def quote(product_id, amount, unit="L", **extra):
    need = {"product_id": product_id, "amount": amount, "unit": unit} | extra
    return build_quote(QuoteRequest(customer="demo-hotel-chain", delivery_date=MONDAY, needs=[need]))


# ---------- Search ----------


def test_search_returns_cards_with_reliability_and_carbon():
    cards = catalog.load().search("lactose free milk", 50)
    assert cards and {c.category for c in cards} == {"10400"}
    milk = next(c for c in cards if c.id == "464306")
    assert milk.carbon_footprint.certainty == "estimated" and milk.carbon_footprint.value is not None
    assert milk.delivery_reliability.source in ("aimo_delivery_history", "none")
    assert milk.allergens.contains == ["AM"] and milk.allergens.data == "complete"
    assert milk.size_per_sales_unit.value == 1.0 and milk.size_per_sales_unit.unit == "L"
    assert not [label for label in milk.labels if label.endswith("Temperature")]
    assert set(milk.catalog_substitutes) == {"465039", "464398", "469363", "464201"}


def test_search_with_no_match_is_empty():
    assert catalog.load().search("caviar of the moon", 10) == []


# ---------- Units ----------


def test_novobox_litres_become_whole_sales_units():
    card = catalog.load().card("465039")
    price = {"catalogPrice": {"value": 6.86}, "comparisonPrice": {"value": 1.37}, "comparisonUnit": "L"}
    conversion = to_sales_units(1000, "L", card.size_per_sales_unit, price)
    assert (conversion.quantity, conversion.size) == (200, 5.0)


# ---------- Quotes for the demo acts ----------


def test_act1_one_line_within_the_limit():
    checkout = quote("464306", 1000)
    line = checkout.aimo.lines["li-1"]
    assert checkout.total_minor() == 101000 and checkout.line_items[0].quantity == 1000
    assert line.stock.certainty == "declared" and line.stock.value == "not_given"  # the mock's 9999999999
    assert line.price.as_of == datetime.fromisoformat(FROZEN)
    assert checkout.expires_at == datetime.fromisoformat("2026-11-15T13:29:07+02:00")  # 24 h, before the cut-off
    assert checkout.aimo.shortfalls == [] and checkout.aimo.alternatives == []


def test_act2_above_the_limit_is_still_one_quote():
    assert quote("464306", 2000).total_minor() == 202000


def test_act3_partial_stock_takes_the_best_substitute():
    checkout = quote("469363", 600)
    first, second = checkout.aimo.lines["li-1"], checkout.aimo.lines["li-2"]
    assert (checkout.line_items[0].quantity, first.stock.value, first.stock.certainty) == (384, 384, "measured")
    assert (
        checkout.aimo.shortfalls[0].missing_base_quantity == 216
        and checkout.aimo.shortfalls[0].reason == "partial_stock"
    )
    assert second.substitute_for.product_id == "469363" and second.base_quantity == 216
    assert second.allergens.contains == first.allergens.contains and second.category == first.category
    tiers = {a.tier: a for a in checkout.aimo.alternatives}
    assert tiers["best"].chosen and tiers["best"].product_id == second.product_id
    assert "good" in tiers and not tiers["good"].chosen


def test_act3_the_buyer_can_name_the_oat_drink():
    checkout = quote("469363", 600, substitute_with="464320")
    oat = checkout.aimo.lines["li-2"]
    assert oat.product_id == "464320" and oat.substitute_for.product_id == "469363"
    assert set(oat.allergens.contains) == {"AW", "GO"}
    assert checkout.total_minor() == 384 * 248 + 216 * 178


def test_a_substitute_that_was_not_offered_is_refused():
    with pytest.raises(QuoteError, match="cannot replace"):
        quote("469363", 600, substitute_with="463290")  # regular milk: not lactose free


def test_alternatives_off_leaves_the_shortfall_uncovered():
    request = QuoteRequest(
        customer="demo",
        delivery_date=MONDAY,
        needs=[{"product_id": "469363", "amount": 600, "unit": "L"}],
        allow_alternatives=False,
    )
    checkout = build_quote(request)
    assert len(checkout.line_items) == 1 and not any(a.chosen for a in checkout.aimo.alternatives)


def test_no_substitute_breaks_the_lactose_free_promise():
    checkout = quote("469363", 600)
    for alternative in checkout.aimo.alternatives:
        assert catalog.lactose_free(catalog.load().card(alternative.product_id))


def test_terminal_product_with_a_past_cut_off_is_a_late_delivery():
    checkout = quote("465039", 100)  # cut-off was 12/11: nothing of it, all of it from a substitute
    assert checkout.aimo.shortfalls[0].reason == "late_delivery"
    assert checkout.aimo.lines["li-1"].substitute_for.product_id == "465039"


def test_unknown_product_and_other_dates_are_refused():
    with pytest.raises(QuoteError, match="not_found"):
        quote("000000", 10)
    with pytest.raises(QuoteError, match="only has answers for delivery on 2026-11-16"):
        build_quote(
            QuoteRequest(
                customer="demo", delivery_date="2026-11-17", needs=[{"product_id": "464306", "amount": 1, "unit": "L"}]
            )
        )


# ---------- HTTP ----------


def test_routes_search_quote_fetch_and_verify():
    client = TestClient(app)
    found = SearchResponse.model_validate(client.get("/products/search", params={"q": "lactose free milk"}).json())
    assert found.count == len(found.products) > 0

    body = {
        "customer": "demo-hotel-chain",
        "delivery_date": MONDAY,
        "needs": [{"product_id": "464306", "amount": 1000, "unit": "L"}],
    }
    created = CheckoutResponse.model_validate(client.post("/checkouts", json=body).json())
    jwks = client.get("/.well-known/jwks.json").json()
    assert jwks == public_jwks()
    verified = verify_checkout(created.checkout_jwt, jwks, datetime.fromisoformat(FROZEN))
    assert verified.id == created.checkout_id and verified.total_minor() == 101000

    again = CheckoutResponse.model_validate(client.get(f"/checkouts/{created.checkout_id}").json())
    assert again.checkout_jwt == created.checkout_jwt
    assert client.get("/checkouts/chk_nope").status_code == 404
    assert client.post("/checkouts", json=body | {"delivery_date": "2026-11-17"}).status_code == 422


def test_cross_origin_from_localhost_is_allowed():
    response = TestClient(app).get("/.well-known/jwks.json", headers={"Origin": "http://localhost:5173"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
