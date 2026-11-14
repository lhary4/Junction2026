"""The trust library: quotes, mandates and receipts behave as the gateway and the harness expect.

The mandate cases follow spikes/ap2/: one happy path and the attacks from the demo script, on our own functions.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from jwcrypto.jwk import JWK

from common import clock
from contract.ap2 import Amount, Merchant, PaymentInstrument, PaymentMandate
from contract.models import AimoCheckout, Authorization, BuyerPolicy
from trust import TrustError
from trust.checkout import checkout_hash, read_checkout, sign_checkout, verify_checkout
from trust.keys import private_key, public_jwk, public_jwks
from trust.mandates import (
    OpenMandates,
    _client,
    close_as_agent,
    close_as_human,
    issue_open_mandates,
    verify_mandates,
)
from trust.receipts import sign_receipt, verify_receipt

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "contract" / "examples"
FIXTURES = ROOT / "contract" / "fixtures"
NOW = datetime.fromisoformat("2026-11-14T13:15:00+02:00")  # act 1's issued_at

MANAGER, AGENT, MERCHANT = private_key("manager"), private_key("agent"), private_key("merchant")
ATTACKER = JWK.generate(kty="EC", crv="P-256", kid="merchant")  # same kid as Valio's, different key
MANAGER_PUB = public_jwk("manager")


def example(name):
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def quote(act=1, key=MERCHANT, **changes) -> str:
    checkout = AimoCheckout.model_validate(example(f"checkout.act{act}.json"))
    return sign_checkout(checkout.model_copy(update=changes), key)


def policy(**changes) -> BuyerPolicy:
    return BuyerPolicy.model_validate(example("policy.demo.json") | changes)


@pytest.fixture(scope="module")
def open_mandates() -> OpenMandates:
    return issue_open_mandates(policy(), MANAGER, public_jwk("agent"))


def refused(check, words):
    assert not check.ok and check.signed_by is None
    assert words in " ".join(check.problems), check.problems


# ---------- The quote ----------


def test_valid_quote_verifies_and_round_trips():
    jwt = quote()
    assert verify_checkout(jwt, public_jwks(), NOW) == AimoCheckout.model_validate(example("checkout.act1.json"))


def test_quote_signed_with_another_key_is_refused():
    with pytest.raises(TrustError) as error:
        verify_checkout(quote(key=ATTACKER), public_jwks(), NOW)
    assert error.value.rule == "quote-signature"


def test_quote_with_unknown_key_id_is_refused():
    with pytest.raises(TrustError, match="no single ES256 key"):
        verify_checkout(quote(), {"keys": []}, NOW)


def read(name):
    return (FIXTURES / name).read_text(encoding="utf-8").strip()


def test_fixtures_valid_tampered_expired():
    assert verify_checkout(read("checkout.valid.jwt"), public_jwks(), NOW).id == "chk_act1_demo"
    with pytest.raises(TrustError) as tampered:
        verify_checkout(read("checkout.tampered.jwt"), public_jwks(), NOW)
    assert tampered.value.rule == "quote-signature"
    with pytest.raises(TrustError) as expired:
        verify_checkout(read("checkout.expired.jwt"), public_jwks(), NOW)
    assert expired.value.rule == "quote-not-expired"


def test_public_jwks_has_no_private_part():
    assert [set(k) for k in public_jwks()["keys"]] == [{"kty", "kid", "crv", "x", "y"}]


# ---------- Agent signs, inside the open mandates (spike cases 1 to 10) ----------


def test_1_inside_the_mandate_is_accepted(open_mandates):
    jwt = quote(1)
    check = verify_mandates(close_as_agent(open_mandates, AGENT, jwt), jwt, MANAGER_PUB)
    assert check.ok and check.signed_by == "agent" and check.problems == []
    assert check.reference
    # What the payment mandate allows, for the gateway's sandbox payment: the amount, and the cap the manager signed.
    checkout = read_checkout(jwt)
    assert (check.facts.amount_minor, check.facts.currency) == (checkout.total_minor(), "EUR")
    assert check.facts.cap_minor == policy().autonomous_limit_minor >= checkout.total_minor()
    assert check.facts.instrument == f"invoice-account:{checkout.aimo.customer}"


def test_2_tampered_quote_is_refused(open_mandates):
    jwt = quote(1)
    header, _, signature = jwt.split(".")
    forged = read("checkout.tampered.jwt").split(".")[1]
    tampered = f"{header}.{forged}.{signature}"
    with pytest.raises(TrustError):
        verify_checkout(tampered, public_jwks(), NOW)
    refused(
        verify_mandates(close_as_agent(open_mandates, AGENT, jwt), tampered, MANAGER_PUB),
        "does not match the quote Valio Aimo signed",
    )


def test_3_merchant_not_in_the_mandate_is_refused(open_mandates):
    jwt = quote(1, merchant=Merchant(id="fake-wholesaler", name="Fake Wholesaler"))
    refused(
        verify_mandates(close_as_agent(open_mandates, AGENT, jwt), jwt, MANAGER_PUB),
        "is not a merchant the agent is allowed to order from",
    )


def test_4_open_mandate_forged_by_someone_else_is_refused():
    forged = issue_open_mandates(policy(), ATTACKER, public_jwk("agent"))
    jwt = quote(1)
    refused(
        verify_mandates(close_as_agent(forged, AGENT, jwt), jwt, MANAGER_PUB),
        "A signature on the mandate does not verify",
    )


def test_5_another_agent_using_our_mandate_is_refused(open_mandates):
    jwt = quote(1)
    refused(
        verify_mandates(close_as_agent(open_mandates, ATTACKER, jwt), jwt, MANAGER_PUB),
        "A signature on the mandate does not verify",
    )


def test_6_authorization_replayed_on_another_quote_is_refused(open_mandates):
    act1, act3 = quote(1), quote(3)
    refused(
        verify_mandates(close_as_agent(open_mandates, AGENT, act1), act3, MANAGER_PUB),
        "signed for another quote (chk_act1_demo), not for this one (chk_act3_demo)",
    )


def test_7_authorization_replayed_on_a_new_quote_with_the_same_id_is_refused(open_mandates):
    first, second = quote(1), quote(1)  # same content, new signature: a different token, so a different hash
    refused(
        verify_mandates(close_as_agent(open_mandates, AGENT, first), second, MANAGER_PUB),
        "does not match the quote Valio Aimo signed",
    )


def test_8_expired_open_mandate_is_refused():
    stale = issue_open_mandates(policy(valid_until="2026-11-01T00:00:00+02:00"), MANAGER, public_jwk("agent"))
    jwt = quote(1)
    refused(verify_mandates(close_as_agent(stale, AGENT, jwt), jwt, MANAGER_PUB), "expired")


def test_9_above_the_spend_cap_is_refused_for_the_agent(open_mandates):
    jwt = quote(2)  # 2 020 EUR against a 1 500 EUR cap
    refused(
        verify_mandates(close_as_agent(open_mandates, AGENT, jwt), jwt, MANAGER_PUB),
        "EUR 2,020.00, is above the EUR 1,500.00 the agent may sign alone",
    )


def test_10_payment_smaller_than_the_quote_is_refused(open_mandates):
    jwt = quote(2)
    honest = close_as_agent(open_mandates, AGENT, jwt)
    small = PaymentMandate(
        transaction_id=checkout_hash(jwt),
        payee=Merchant(id="valio-aimo", name="Valio Aimo"),
        payment_amount=Amount(amount=100, currency="EUR"),
        payment_instrument=PaymentInstrument(id="invoice-account:demo-hotel-chain", type="invoice"),
    )
    lying = _client.present(
        holder_key=AGENT, mandate_token=open_mandates.payment, payloads=[small], aud="valio-aimo", nonce="chk_act2_demo"
    )
    authorization = honest.model_copy(update={"payment_mandate": lying})
    refused(verify_mandates(authorization, jwt, MANAGER_PUB), "is for EUR 1.00, the quote's total is EUR 2,020.00")


def test_11_agent_chain_claiming_a_human_signed_it_is_refused(open_mandates):
    jwt = quote(1)
    authorization = close_as_agent(open_mandates, AGENT, jwt).model_copy(update={"signed_by": "human"})
    refused(
        verify_mandates(authorization, jwt, MANAGER_PUB),
        "says a human signed it, but the mandates are signed by the agent",
    )


# ---------- Human signs this exact quote (spike 2: above the cap) ----------


def test_12_human_signed_order_above_the_cap_is_accepted():
    jwt = quote(2)
    check = verify_mandates(close_as_human(MANAGER, jwt), jwt, MANAGER_PUB)
    assert check.ok and check.signed_by == "human"
    assert check.facts.cap_minor is None  # the manager signs this exact order: no cap applies
    assert check.facts.amount_minor == read_checkout(jwt).total_minor() > policy().autonomous_limit_minor


def test_13_human_form_signed_with_the_agent_key_is_refused():
    jwt = quote(2)
    refused(verify_mandates(close_as_human(AGENT, jwt), jwt, MANAGER_PUB), "A signature on the mandate does not verify")


def test_14_human_approval_reused_for_another_quote_is_refused():
    act1, act2 = quote(1), quote(2)
    refused(verify_mandates(close_as_human(MANAGER, act1), act2, MANAGER_PUB), "another quote")


def test_mixed_forms_are_refused(open_mandates):
    jwt = quote(1)
    agent, human = close_as_agent(open_mandates, AGENT, jwt), close_as_human(MANAGER, jwt)
    mixed = Authorization(
        signed_by="agent", checkout_mandate=agent.checkout_mandate, payment_mandate=human.payment_mandate
    )
    refused(verify_mandates(mixed, jwt, MANAGER_PUB), "one is signed by the agent, the other by a human")


def test_recorded_open_mandates_work_with_the_demo_agent_key():
    recorded = OpenMandates.model_validate_json(read("open_mandates.json"))
    jwt = quote(1)
    assert verify_mandates(close_as_agent(recorded, AGENT, jwt), jwt, MANAGER_PUB).ok


# ---------- Receipt ----------


def test_receipt_round_trip_uses_the_frozen_clock(monkeypatch, open_mandates):
    monkeypatch.setenv("AIMO_FROZEN_NOW", NOW.isoformat())
    jwt = quote(1)
    check = verify_mandates(close_as_agent(open_mandates, AGENT, jwt), jwt, MANAGER_PUB)
    receipt = verify_receipt(sign_receipt("ord_test", check.reference, MERCHANT), public_jwks())
    assert receipt == {
        "status": "Success",
        "iss": "valio-aimo",
        "iat": int(NOW.timestamp()),
        "reference": check.reference,
        "order_id": "ord_test",
    }


def test_receipt_signed_by_someone_else_is_refused():
    with pytest.raises(TrustError):
        verify_receipt(sign_receipt("ord_test", "ref", ATTACKER), public_jwks())


# ---------- Clock ----------


def test_clock_is_real_in_live_mode_recorded_in_replay_and_frozen_on_demand(monkeypatch):
    recorded = datetime.fromisoformat(read("valio/frozen_now.txt").strip())
    monkeypatch.delenv("AIMO_FROZEN_NOW", raising=False)
    monkeypatch.setenv("VALIO_MODE", "live")
    assert abs(clock.now() - datetime.now(UTC)) < timedelta(seconds=5)
    monkeypatch.setenv("VALIO_MODE", "replay")
    assert clock.now() == recorded
    monkeypatch.delenv("VALIO_MODE")
    assert clock.now() == recorded  # replay is the default mode
    monkeypatch.setenv("AIMO_FROZEN_NOW", "2026-11-14T13:15:00+02:00")
    assert clock.now() == NOW  # an explicit time wins over the recording
    monkeypatch.setenv("AIMO_FROZEN_NOW", "2026-11-14T13:15:00")
    with pytest.raises(ValueError, match="UTC offset"):
        clock.now()


def test_malformed_jwt_header_and_payload_raise_trust_error():
    import base64

    from jwcrypto.jws import JWS

    from contract.models import Receipt
    from trust.keys import verify

    non_obj_header = base64.urlsafe_b64encode(b"[]").decode().rstrip("=")
    with pytest.raises(TrustError, match="malformed JWT header"):
        verify(f"{non_obj_header}.e30.sig", public_jwks())

    jws = JWS(b"not-json")
    jws.add_signature(MERCHANT, alg="ES256", protected=json.dumps({"alg": "ES256", "typ": "JWT", "kid": MERCHANT.get("kid")}))
    with pytest.raises(TrustError, match="bad signature"):
        verify(jws.serialize(compact=True), public_jwks())

    err_receipt = Receipt.model_validate({
        "status": "Error",
        "iss": "valio-aimo",
        "iat": int(NOW.timestamp()),
        "reference": "ref",
        "error": "expired",
        "error_description": "quote expired",
    })
    assert err_receipt.status == "Error"


def test_checkout_without_expiry_is_rejected_and_missing_total_raises_value_error():
    from contract.models import AimoCheckout
    from trust.checkout import sign_checkout, verify_checkout

    example_path = FIXTURES.parent / "examples" / "checkout.act1.json"
    data = json.loads(example_path.read_text(encoding="utf-8"))
    data.pop("expires_at", None)
    no_exp = AimoCheckout.model_validate(data)
    with pytest.raises(TrustError, match="no expiry"):
        verify_checkout(sign_checkout(no_exp, MERCHANT), public_jwks(), NOW)

    data_no_total = json.loads(example_path.read_text(encoding="utf-8"))
    data_no_total["totals"] = [{"type": "subtotal", "amount": 100}]
    no_total = AimoCheckout.model_validate(data_no_total)
    with pytest.raises(ValueError, match="total"):
        no_total.total_minor()
