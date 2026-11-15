"""Tests for customer-specific MHD/overstock prospect, signed quote parity, and harness shelf-life guardrail."""

from datetime import date, datetime

from fastapi.testclient import TestClient

from contract.models import Need, QuoteRequest, RuleResult
from harness.policy import load_policy
from harness.rules import evaluate
from merchant.app import app as merchant_app
from merchant.prospect import build_prospect
from merchant.quotes import build_quote

DELIVERY = date(2026, 11, 19)
NOW = datetime.fromisoformat("2026-11-14T13:15:04+02:00")
SIG_PASS = RuleResult(rule_id="quote-signature", outcome="pass", message="OK", evidence={"kid": "test"})


def test_prospect_differs_by_customer_tier_and_cuisine():
    client = TestClient(merchant_app)
    bistro = client.get("/prospect", params={"customer": "ravintola-demo", "delivery_date": DELIVERY.isoformat()}).json()
    hotel = client.get("/prospect", params={"customer": "hotel-nordic-chain", "delivery_date": DELIVERY.isoformat()}).json()
    pizzeria = client.get("/prospect", params={"customer": "trattoria-napoli", "delivery_date": DELIVERY.isoformat()}).json()

    bistro_by_id = {i["product"]["id"]: i for i in bistro["items"]}
    hotel_by_id = {i["product"]["id"]: i for i in hotel["items"]}

    assert bistro["contract_discount_pct"] == 0
    assert hotel["contract_discount_pct"] == 12
    assert hotel_by_id["475742"]["contract_price_minor"] < bistro_by_id["475742"]["contract_price_minor"]
    assert hotel_by_id["475742"]["promo_price_minor"] < bistro_by_id["475742"]["promo_price_minor"]

    # Pizzeria prioritizes cheese (475742), Nordic bistro prioritizes fresh dill herbs (460395)
    assert pizzeria["items"][0]["product"]["id"] == "475742"
    assert bistro["items"][0]["product"]["id"] == "460395"

    demo = client.get("/prospect", params={"customer": "demo-restaurant-helsinki", "delivery_date": DELIVERY.isoformat()}).json()
    assert demo["customer_name"] == "Demo Restaurant Helsinki"
    assert demo["contract_discount_pct"] == 5


def test_signed_quote_matches_prospect_price_and_normal_orders_unchanged():
    prospect = build_prospect(customer="hotel-nordic-chain", delivery_date=DELIVERY)
    cheese = next(i for i in prospect.items if i.product.id == "475742")

    promo_quote = build_quote(
        QuoteRequest(
            customer="hotel-nordic-chain",
            delivery_date=DELIVERY,
            needs=[Need(product_id="475742", amount=5.0, unit="KG", claim_promo=True)],
        )
    )
    line_item = promo_quote.line_items[0]
    claims = promo_quote.aimo.lines[line_item.id]
    assert line_item.item.price == cheese.promo_price_minor
    assert claims.base_unit_price_minor == cheese.contract_price_minor
    assert claims.promo_discount_pct == cheese.discount_pct
    assert claims.shelf_life_days == cheese.shelf_life_days

    normal_quote = build_quote(
        QuoteRequest(
            customer="hotel-nordic-chain",
            delivery_date=DELIVERY,
            needs=[Need(product_id="475742", amount=5.0, unit="KG", claim_promo=False)],
        )
    )
    normal_claims = normal_quote.aimo.lines[normal_quote.line_items[0].id]
    assert normal_quote.line_items[0].item.price > cheese.promo_price_minor
    assert normal_claims.shelf_life_days is None


def test_harness_shelf_life_window_flags_short_lots_for_human_signoff():
    policy = load_policy()

    short_quote = build_quote(
        QuoteRequest(
            customer="ravintola-demo",
            delivery_date=DELIVERY,
            needs=[Need(product_id="460395", amount=1.0, unit="KG", claim_promo=True)],
        )
    )
    short_verdict = evaluate(policy, short_quote, NOW, SIG_PASS)
    shelf_rules = [r for r in short_verdict.rules if r.rule_id == "shelf-life-window"]
    assert len(shelf_rules) == 1
    assert shelf_rules[0].outcome == "human"
    assert short_verdict.decision == "human"

    safe_quote = build_quote(
        QuoteRequest(
            customer="ravintola-demo",
            delivery_date=DELIVERY,
            needs=[Need(product_id="476890", amount=2.0, unit="KG", claim_promo=True)],
        )
    )
    safe_verdict = evaluate(policy, safe_quote, NOW, SIG_PASS)
    safe_rules = [r for r in safe_verdict.rules if r.rule_id == "shelf-life-window"]
    assert len(safe_rules) == 1
    assert safe_rules[0].outcome == "pass"
    assert safe_verdict.decision == "auto"


def test_driver_forwards_claim_promo_to_gateway_quote():
    from dataclasses import replace

    from scenarios.run import Driver

    gw_client = TestClient(merchant_app)
    posted_bodies: list[dict] = []

    class _CapturingGateway:
        def post(self, path: str, json: dict):
            posted_bodies.append(json)
            return gw_client.post(path, json=json)

    drv = Driver(gateway=_CapturingGateway())
    scenario = drv.scenarios["normal-order"]
    needs = [Need(product_id=pid, amount=amt, unit=unit) for pid, amt, unit in scenario.needs] + [
        Need(product_id="476890", amount=2.0, unit="KG", claim_promo=True)
    ]
    replaced = replace(
        scenario,
        needs=tuple((n.product_id, n.amount, n.unit) for n in needs),
        promo_products=frozenset(n.product_id for n in needs if n.claim_promo),
    )
    checkout = drv._quote(replaced, replaced.needs)
    assert any(n.get("claim_promo") is True and n["product_id"] == "476890" for n in posted_bodies[0]["needs"])
    promo_line = next(li for li in checkout.checkout.line_items if li.item.id == "476890")
    assert checkout.checkout.aimo.lines[promo_line.id].promo_discount_pct == 30
