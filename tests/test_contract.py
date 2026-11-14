"""Every example in contract/examples/ validates with its model. If this fails, the code and the examples disagree."""

import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from contract.ap2 import Checkout
from contract.models import (
    AimoCheckout,
    ApprovalRequest,
    AuditEvent,
    Authorization,
    AuthorizationStatus,
    BuyerPolicy,
    Claim,
    DemoState,
    FootprintResponse,
    Offer,
    OffersRequest,
    OffersResponse,
    Order,
    ProductCard,
    QuoteRequest,
    Verdict,
)

EXAMPLES = Path(__file__).resolve().parent.parent / "contract" / "examples"
CHECKOUTS = ["checkout.act1.json", "checkout.act2.json", "checkout.act3.json"]
DEMO_STATES = [
    "demo-state.idle.json",
    "demo-state.normal-order.json",
    "demo-state.substitution.pending.json",
    "demo-state.substitution.approved.json",
    "demo-state.attack.json",
    "demo-state.normal-order.greener.json",
]

SINGLE = {
    "approval-request.pending.json": ApprovalRequest,
    "authorization.json": Authorization,
    "offers.act1.json": OffersResponse,
    "footprint.normal-order.json": FootprintResponse,
    "footprint.normal-order.greener.json": FootprintResponse,
    "order.json": Order,
    "policy.demo.json": BuyerPolicy,
    "quote-request.json": QuoteRequest,
    "verdict.auto.json": Verdict,
    "verdict.deny.json": Verdict,
    "verdict.human.spend.json": Verdict,
    "verdict.human.substitution.json": Verdict,
    **{name: AimoCheckout for name in CHECKOUTS},
    **{name: DemoState for name in DEMO_STATES},
}
SHAPES = {
    "product-cards.json": list[ProductCard],
    "authorization-status.json": dict[str, AuthorizationStatus],
    "audit-events.json": dict[str, list[AuditEvent]],
}


def load(name):
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def test_every_example_has_a_model():
    assert sorted(p.name for p in EXAMPLES.glob("*.json")) == sorted(SINGLE | SHAPES)


@pytest.mark.parametrize("name", sorted(SINGLE))
def test_example_validates(name):
    SINGLE[name].model_validate(load(name))


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_example_collection_validates(name):
    TypeAdapter(SHAPES[name]).validate_python(load(name))


@pytest.mark.parametrize("name", CHECKOUTS)
def test_checkout_is_also_a_plain_sdk_checkout(name):
    data = load(name)
    sdk = Checkout.model_validate(data)
    ours = AimoCheckout.model_validate(data)
    assert {line.id for line in sdk.line_items} == set(ours.aimo.lines)


@pytest.mark.parametrize("name", CHECKOUTS)
def test_checkout_survives_a_json_round_trip(name):
    """What the gateway signs (dumped without nulls) must validate again on the harness side."""
    ours = AimoCheckout.model_validate(load(name))
    again = AimoCheckout.model_validate(ours.model_dump(mode="json", exclude_none=True))
    assert again == ours


def test_aimo_lines_must_match_line_items():
    data = load("checkout.act1.json")
    data["aimo"]["lines"]["li-2"] = data["aimo"]["lines"].pop("li-1")
    with pytest.raises(ValidationError, match="must match line item ids"):
        AimoCheckout.model_validate(data)


def test_unknown_field_is_refused():
    data = load("verdict.auto.json") | {"decison": "auto"}
    with pytest.raises(ValidationError, match="decison"):
        Verdict.model_validate(data)


def test_unknown_claim_has_no_value():
    claim = {"value": 0.9, "unit": "share_delivered", "source": "none", "as_of": "2026-11-14T11:21:00+02:00"}
    with pytest.raises(ValidationError, match="certainty is 'unknown'"):
        Claim.model_validate(claim | {"certainty": "unknown"})


def test_an_offer_that_cannot_be_ordered_says_why():
    offer = load("offers.act1.json")["offers"][0]
    Offer.model_validate(offer | {"orderable": False, "reason": "late_delivery"})
    with pytest.raises(ValidationError, match="reason must be null exactly when orderable is true"):
        Offer.model_validate(offer | {"orderable": False})
    with pytest.raises(ValidationError, match="reason must be null exactly when orderable is true"):
        Offer.model_validate(offer | {"reason": "out_of_stock"})


def test_a_lookup_amount_comes_with_its_unit():
    lookup = {"q": "lactose-free milk", "delivery_date": "2026-11-16"}
    assert OffersRequest.model_validate(lookup).limit == 10
    OffersRequest.model_validate(lookup | {"amount": 1000, "unit": "L"})
    for half in ({"amount": 1000}, {"unit": "L"}):
        with pytest.raises(ValidationError, match="amount and unit go together"):
            OffersRequest.model_validate(lookup | half)


@pytest.mark.parametrize("name", DEMO_STATES)
def test_demo_state_tells_one_story(name):
    """Every piece of a demo state is about the quote on screen, and the trail agrees with the scenario's status."""
    state = DemoState.model_validate(load(name))
    assert DemoState.model_validate(state.model_dump(mode="json", exclude_none=True)) == state
    assert state.kitchen.customer == "demo-restaurant-helsinki"

    pieces = [state.verdict, state.authorization, state.approval, state.order]
    events = state.audit.buyer + state.audit.merchant
    for piece in [p for p in pieces if p] + events:
        assert state.quote and piece.checkout_id == state.quote.id
    if state.request:
        assert state.quote and state.quote.aimo.customer == state.kitchen.customer
        assert [(n.product_id, n.amount, n.unit) for n in state.quote.aimo.requested] == [
            (line.product_id, line.amount, line.unit) for line in state.request.lines
        ]

    steps = {step.key: step for step in state.steps}
    status = state.scenario.status
    if status == "idle":
        assert not state.request and not state.quote and {s.status for s in state.steps} == {"pending"}
    if status == "done":
        assert state.order and {s.status for s in state.steps} == {"done"}
        assert steps["signed_quote"].proof == state.order.checkout_hash
        assert steps["closed_mandates"].proof == state.order.mandate_reference
        assert steps["closed_mandates"].signer == ("manager" if state.order.signed_by == "human" else "agent")
    if status == "waiting_for_human":
        assert state.approval and state.approval.status == "pending" and not state.order
        assert (steps["closed_mandates"].signer, steps["closed_mandates"].status) == ("manager", "waiting")
        assert steps["signed_receipt"].status == "pending"
    if status == "refused":
        assert not state.order and steps["merchant_verifies"].status == "refused"
        assert state.attacks and all(a.status == "refused" and a.problems for a in state.attacks)


def test_demo_state_keeps_the_seven_steps_and_a_known_scenario():
    state = load("demo-state.normal-order.json")
    with pytest.raises(ValidationError, match="seven steps of the AP2 trail"):
        DemoState.model_validate(state | {"steps": state["steps"][:-1]})
    with pytest.raises(ValidationError, match="is not in scenarios"):
        DemoState.model_validate(state | {"scenario": state["scenario"] | {"id": "milk"}})
    with pytest.raises(ValidationError, match="status is 'idle'"):
        DemoState.model_validate(state | {"scenario": state["scenario"] | {"status": "idle"}})
