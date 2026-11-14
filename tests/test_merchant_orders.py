"""The gateway, part 2, in replay mode: an Authorization becomes an order with a signed receipt, or a refusal."""

import json
import threading
from pathlib import Path

import pytest
from ap2.sdk.utils import b64url_decode, b64url_encode
from fastapi.testclient import TestClient

from common.audit import AuditLog, default_log_path
from contract.models import AuditEvent, BuyerPolicy, CheckoutResponse, Order
from merchant import audit, payments, store
from merchant.app import app
from trust.checkout import checkout_hash
from trust.keys import private_key, public_jwk, public_jwks
from trust.mandates import OpenMandates, close_as_agent, close_as_human, issue_open_mandates
from trust.receipts import verify_receipt

ROOT = Path(__file__).resolve().parent.parent
FROZEN = "2026-11-14T13:29:07+02:00"  # contract/fixtures/valio/frozen_now.txt
AFTER_EXPIRY = "2026-11-15T13:29:08+02:00"  # one second after the 24 hours a quote lasts
MONDAY = "2026-11-16"
MANAGER, AGENT = private_key("manager"), private_key("agent")

client = TestClient(app)


@pytest.fixture(autouse=True)
def replay(monkeypatch, tmp_path):
    monkeypatch.setenv("VALIO_MODE", "replay")
    monkeypatch.setenv("AIMO_FROZEN_NOW", FROZEN)
    monkeypatch.setenv("AIMO_STATE_DIR", str(tmp_path))


@pytest.fixture(scope="module")
def open_mandates() -> OpenMandates:
    policy = json.loads((ROOT / "contract" / "examples" / "policy.demo.json").read_text(encoding="utf-8"))
    return issue_open_mandates(BuyerPolicy.model_validate(policy), MANAGER, public_jwk("agent"))


def quote(litres: int) -> CheckoutResponse:
    """A quote for lactose-free milk 464306 at EUR 1.01 a litre: 1,000 is under the EUR 1,500 cap, 2,000 above."""
    body = {
        "customer": "demo-hotel-chain",
        "delivery_date": MONDAY,
        "needs": [{"product_id": "464306", "amount": litres, "unit": "L"}],
    }
    return CheckoutResponse.model_validate(client.post("/checkouts", json=body).json())


def complete(checkout_id: str, authorization):
    return client.post(f"/checkouts/{checkout_id}/complete", json=authorization.model_dump())


def gateway_log() -> AuditLog:
    """The gateway's log, read with the shared class: its `verify` is the check the harness runs on its own log."""
    return AuditLog(default_log_path("merchant"))


def refused(response, words: str):
    assert response.status_code == 403, response.text
    problems = response.json()["problems"]
    assert words in " ".join(problems), problems


def tamper(checkout_jwt: str) -> str:
    """The same token with a lower price, signature untouched."""
    header, body, signature = checkout_jwt.split(".")
    payload = json.loads(b64url_decode(body))
    payload["line_items"][0]["item"]["price"] = 71
    return ".".join([header, b64url_encode(json.dumps(payload).encode("utf-8")), signature])


# ---------- Accepted ----------


def test_agent_mandate_gives_an_order_whose_receipt_verifies(open_mandates):
    issued = quote(1000)
    response = complete(issued.checkout_id, close_as_agent(open_mandates, AGENT, issued.checkout_jwt))
    assert response.status_code == 200, response.text
    order = Order.model_validate(response.json())
    assert (order.status, order.signed_by, order.total_minor, order.currency) == ("accepted", "agent", 101000, "EUR")
    assert order.checkout_id == issued.checkout_id and order.checkout_hash == checkout_hash(issued.checkout_jwt)
    assert order.delivery_date.isoformat() == MONDAY

    receipt = verify_receipt(order.receipt_jwt, client.get("/.well-known/jwks.json").json())
    assert receipt == order.receipt.model_dump()
    assert (receipt["status"], receipt["order_id"], receipt["reference"]) == (
        "Success",
        order.order_id,
        order.mandate_reference,
    )
    assert Order.model_validate(client.get(f"/orders/{order.order_id}").json()) == order


def test_human_signed_mandate_is_accepted_above_the_cap():
    issued = quote(2000)
    response = complete(issued.checkout_id, close_as_human(MANAGER, issued.checkout_jwt))
    assert response.status_code == 200, response.text
    order = Order.model_validate(response.json())
    assert (order.signed_by, order.total_minor) == ("human", 202000)
    verify_receipt(order.receipt_jwt, public_jwks())


# ---------- Refused ----------


def test_agent_mandate_above_the_cap_is_refused(open_mandates):
    issued = quote(2000)
    response = complete(issued.checkout_id, close_as_agent(open_mandates, AGENT, issued.checkout_jwt))
    refused(response, "202000 exceeds maximum 150000")
    assert store.order_for_checkout(issued.checkout_id) is None


def test_mandate_over_a_tampered_quote_is_refused(open_mandates):
    issued = quote(1000)
    response = complete(issued.checkout_id, close_as_agent(open_mandates, AGENT, tamper(issued.checkout_jwt)))
    refused(response, "another quote")
    assert store.order_for_checkout(issued.checkout_id) is None


def test_mandate_for_another_quote_is_refused(open_mandates):
    first, second = quote(1000), quote(1000)
    response = complete(second.checkout_id, close_as_agent(open_mandates, AGENT, first.checkout_jwt))
    assert response.status_code == 403 and response.json()["problems"]
    assert store.order_for_checkout(second.checkout_id) is None


def test_human_mandate_signed_with_the_agent_key_is_refused():
    issued = quote(2000)
    refused(complete(issued.checkout_id, close_as_human(AGENT, issued.checkout_jwt)), "mandate rejected")


def test_expired_quote_is_refused(open_mandates, monkeypatch):
    issued = quote(1000)
    authorization = close_as_agent(open_mandates, AGENT, issued.checkout_jwt)
    monkeypatch.setenv("AIMO_FROZEN_NOW", AFTER_EXPIRY)
    refused(complete(issued.checkout_id, authorization), "quote expired")


def test_quote_edited_in_the_gateway_state_is_refused(open_mandates):
    issued = quote(1000)
    edited = issued.model_copy(update={"checkout_jwt": tamper(issued.checkout_jwt)})
    store.save_checkout(edited)
    refused(complete(issued.checkout_id, close_as_agent(open_mandates, AGENT, edited.checkout_jwt)), "bad signature")


def test_unknown_quote_and_unknown_order_are_not_found(open_mandates):
    authorization = close_as_agent(open_mandates, AGENT, quote(1000).checkout_jwt)
    assert complete("chk_nope", authorization).status_code == 404
    assert client.get("/orders/ord_nope").status_code == 404
    assert client.post("/checkouts/chk_nope/complete", json={"signed_by": "agent"}).status_code == 422


# ---------- Single use ----------


def test_the_same_mandate_twice_returns_the_same_order(open_mandates, tmp_path):
    issued = quote(1000)
    authorization = close_as_agent(open_mandates, AGENT, issued.checkout_jwt)
    first, again = complete(issued.checkout_id, authorization), complete(issued.checkout_id, authorization)
    assert first.status_code == again.status_code == 200
    assert first.json() == again.json()
    assert len(list((tmp_path / "merchant" / "orders").glob("*.json"))) == 1


def test_another_mandate_for_an_ordered_quote_is_refused(open_mandates):
    issued = quote(1000)
    ordered = complete(issued.checkout_id, close_as_agent(open_mandates, AGENT, issued.checkout_jwt)).json()
    response = complete(issued.checkout_id, close_as_human(MANAGER, issued.checkout_jwt))
    refused(response, f"already ordered as {ordered['order_id']}")


# ---------- Sandbox payment ----------


def test_an_accepted_order_is_booked_on_the_customers_invoice_account(open_mandates):
    issued = quote(1000)
    response = complete(issued.checkout_id, close_as_agent(open_mandates, AGENT, issued.checkout_jwt))
    order = Order.model_validate(response.json())
    payment = order.payment
    assert (payment.status, payment.amount_minor, payment.currency, payment.sandbox) == (
        "captured",
        101000,
        "EUR",
        True,
    )
    assert payment.instrument == "invoice-account:demo-hotel-chain" and payment.payment_id.startswith("pay_")
    assert payment.captured_at == order.accepted_at
    # What the payment mandate allowed, as Valio read it: the cap comes from the open mandate the manager signed.
    assert order.mandate.model_dump() == {
        "cap_minor": 150000,
        "amount_minor": 101000,
        "currency": "EUR",
        "instrument": "invoice-account:demo-hotel-chain",
    }
    booked = payments.account("demo-hotel-chain")
    assert (booked.used_minor, booked.credit_limit_minor) == (101000, payments.CREDIT_LIMIT_MINOR)
    assert [(b.payment_id, b.order_id, b.amount_minor) for b in booked.bookings] == [
        (payment.payment_id, order.order_id, 101000)
    ]
    assert Order.model_validate(client.get(f"/orders/{order.order_id}").json()).payment == payment


def test_an_order_the_manager_signed_has_no_cap_and_is_booked_too():
    issued = quote(2000)
    order = Order.model_validate(complete(issued.checkout_id, close_as_human(MANAGER, issued.checkout_jwt)).json())
    assert (order.mandate.cap_minor, order.mandate.amount_minor) == (None, 202000)
    assert order.payment.amount_minor == 202000
    assert payments.account("demo-hotel-chain").used_minor == 202000


def test_a_mandate_sent_twice_and_a_refused_order_book_nothing_more(open_mandates):
    issued = quote(1000)
    authorization = close_as_agent(open_mandates, AGENT, issued.checkout_jwt)
    complete(issued.checkout_id, authorization)
    complete(issued.checkout_id, authorization)
    above = quote(2000)
    refused(complete(above.checkout_id, close_as_agent(open_mandates, AGENT, above.checkout_jwt)), "exceeds maximum")
    booked = payments.account("demo-hotel-chain")
    assert booked.used_minor == 101000 and len(booked.bookings) == 1


def test_an_order_above_what_is_left_on_the_account_is_refused(open_mandates, monkeypatch):
    monkeypatch.setattr(payments, "CREDIT_LIMIT_MINOR", 150000)
    first, second = quote(1000), quote(1000)
    assert complete(first.checkout_id, close_as_agent(open_mandates, AGENT, first.checkout_jwt)).status_code == 200
    response = complete(second.checkout_id, close_as_agent(open_mandates, AGENT, second.checkout_jwt))
    refused(response, "exceeds what is left on the invoice account (49000 of 150000)")
    assert store.order_for_checkout(second.checkout_id) is None
    assert payments.account("demo-hotel-chain").used_minor == 101000


# ---------- Audit ----------


def test_audit_tells_the_story_and_every_line_points_at_the_previous_one(open_mandates):
    issued = quote(1000)
    authorization = close_as_agent(open_mandates, AGENT, issued.checkout_jwt)
    order = complete(issued.checkout_id, authorization).json()
    complete(issued.checkout_id, authorization)
    complete(issued.checkout_id, close_as_human(MANAGER, issued.checkout_jwt))

    log = [AuditEvent.model_validate(event) for event in client.get("/audit").json()]
    assert [event.action for event in log] == [
        "quote_issued",
        "mandate_verified",
        "payment_captured",
        "order_accepted",
        "order_replayed",
        "order_refused",
    ]
    assert log[0].what == "Quote for 1000 ST of 464306, 1010.00 EUR excl. tax."
    assert log[2].what == (
        f"Sandbox payment {order['payment']['payment_id']}: 1010.00 EUR booked on invoice-account:demo-hotel-chain."
    )
    assert "1010.00 of 20000.00 EUR used" in log[2].why and "No real money moves" in log[2].why
    assert order["order_id"] in log[3].what and "already ordered" in log[5].why
    assert {(event.side, event.checkout_id, event.checkout_hash) for event in log} == {
        ("merchant", issued.checkout_id, checkout_hash(issued.checkout_jwt))
    }
    assert [event.seq for event in log] == [1, 2, 3, 4, 5, 6]
    assert [event.prev_hash for event in log] == [None] + [event.hash for event in log[:-1]]
    assert gateway_log().verify() is None


def test_the_log_sits_with_the_rest_of_the_gateway_state():
    assert gateway_log().path == store.state_dir() / "audit.jsonl"


def test_requests_at_the_same_time_never_break_the_chain():
    def write(thread: int):
        for line in range(20):
            audit.record("test", f"Line {line} of thread {thread}.", "Eight threads write at once.")

    threads = [threading.Thread(target=write, args=(thread,)) for thread in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert [event.seq for event in audit.events()] == list(range(1, 161))
    assert gateway_log().verify() is None


def test_a_refusal_answers_cross_origin_calls_from_localhost(open_mandates):
    issued = quote(2000)
    response = client.post(
        f"/checkouts/{issued.checkout_id}/complete",
        json=close_as_agent(open_mandates, AGENT, issued.checkout_jwt).model_dump(),
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.status_code == 403
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
