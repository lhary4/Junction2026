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
    Order,
    ProductCard,
    QuoteRequest,
    Verdict,
)

EXAMPLES = Path(__file__).resolve().parent.parent / "contract" / "examples"
CHECKOUTS = ["checkout.act1.json", "checkout.act2.json", "checkout.act3.json"]

SINGLE = {
    "approval-request.pending.json": ApprovalRequest,
    "authorization.json": Authorization,
    "order.json": Order,
    "policy.demo.json": BuyerPolicy,
    "quote-request.json": QuoteRequest,
    "verdict.auto.json": Verdict,
    "verdict.deny.json": Verdict,
    "verdict.human.spend.json": Verdict,
    "verdict.human.substitution.json": Verdict,
    **{name: AimoCheckout for name in CHECKOUTS},
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
