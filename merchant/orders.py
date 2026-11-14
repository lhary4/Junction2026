"""An Authorization becomes an order, or a refusal that lists every problem. No valid signature, no order.

Checks, in this order:
  1. the quote exists, is still the one Valio signed, and has not expired
  2. the mandates verify against it (trust.verify_mandates: signatures, merchant, quote hash, amount, spend cap)
  3. the quote has not been ordered yet
  4. the amount fits on the customer's invoice account (merchant/payments.py: a sandbox, no real money moves)

A mandate is bound to one quote by its hash, so "this mandate was already used" can only mean "this quote was already
ordered". The same mandate sent again gets the same order back: a retry after a lost answer never orders twice.
Another mandate for an ordered quote is refused.
"""

import threading
import uuid
from datetime import datetime

from pydantic import BaseModel

from common import clock
from contract.models import AimoCheckout, Authorization, Order, Payment, Receipt
from merchant import audit, payments, store
from merchant.catalog import HELSINKI
from trust import TrustError
from trust.checkout import checkout_hash, verify_checkout
from trust.keys import private_key, public_jwk, public_jwks
from trust.mandates import MandateCheck, verify_mandates
from trust.receipts import sign_receipt, verify_receipt

_lock = threading.Lock()  # two requests for the same quote must not both find it unordered


class Refusal(BaseModel):
    """Body of the HTTP 403 answer."""

    problems: list[str]


class OrderRefused(Exception):
    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


class UnknownQuote(LookupError):
    pass


def complete(checkout_id: str, authorization: Authorization) -> Order:
    quote = store.load_checkout(checkout_id)
    if quote is None:
        raise UnknownQuote(checkout_id)
    digest = checkout_hash(quote.checkout_jwt)
    try:
        with _lock:
            return _complete(quote.checkout_jwt, digest, authorization)
    except OrderRefused as refusal:
        audit.record("order_refused", f"Order refused for quote {checkout_id}.", str(refusal), checkout_id, digest)
        raise


def _complete(checkout_jwt: str, digest: str, authorization: Authorization) -> Order:
    try:
        checkout = verify_checkout(checkout_jwt, public_jwks(), clock.now())
    except TrustError as e:
        raise OrderRefused([str(e)]) from e

    # The manager's public key: in production Valio would hold it from the day the customer account was opened.
    check = verify_mandates(authorization, checkout_jwt, public_jwk("manager"))
    if not check.ok:
        raise OrderRefused(check.problems)

    existing = store.order_for_checkout(checkout.id)
    if existing and existing.mandate_reference == check.reference:
        why = "The same mandate was sent again: one mandate gives one order."
        audit.record("order_replayed", f"Order {existing.order_id} returned again.", why, checkout.id, digest)
        return existing
    if existing:
        raise OrderRefused([f"quote {checkout.id} was already ordered as {existing.order_id} with another mandate"])

    audit.record("mandate_verified", *_mandate_story(check), checkout.id, digest)
    order_id = f"ord_{uuid.uuid4().hex[:8]}"
    now = clock.now().astimezone(HELSINKI)
    try:
        payment = payments.capture(checkout, check.facts, order_id, now)
    except payments.PaymentRefused as e:
        raise OrderRefused([str(e)]) from e
    order = _accept(checkout, digest, check, order_id, now, payment)
    store.save_order(order)
    audit.record("payment_captured", *_payment_story(payment, checkout.aimo.customer), checkout.id, digest)
    why = "Valid mandate for a quote Valio signed and that has not expired."
    audit.record("order_accepted", f"Order {order.order_id} accepted, receipt signed.", why, checkout.id, digest)
    return order


def _accept(
    checkout: AimoCheckout, digest: str, check: MandateCheck, order_id: str, now: datetime, payment: Payment
) -> Order:
    receipt_jwt = sign_receipt(order_id, check.reference, private_key("merchant"))
    return Order(
        order_id=order_id,
        status="accepted",
        checkout_id=checkout.id,
        checkout_hash=digest,
        mandate_reference=check.reference,
        signed_by=check.signed_by,
        total_minor=checkout.total_minor(),
        currency=checkout.currency,
        delivery_date=checkout.aimo.delivery_date,
        created_at=now,
        accepted_at=now,
        receipt_jwt=receipt_jwt,
        receipt=Receipt.model_validate(verify_receipt(receipt_jwt, public_jwks())),
        mandate=check.facts,
        payment=payment,
    )


def _payment_story(payment: Payment, customer: str) -> tuple[str, str]:
    """What and why for the audit line of the sandbox payment."""
    booked = payments.account(customer, payment.currency)
    amount = f"{payment.amount_minor / 100:.2f} {payment.currency}"
    used = f"{booked.used_minor / 100:.2f} of {booked.credit_limit_minor / 100:.2f} {booked.currency}"
    return (
        f"Sandbox payment {payment.payment_id}: {amount} booked on {payment.instrument}.",
        f"The mandates verify. Simulated account: {used} used. No real money moves.",
    )


def _mandate_story(check: MandateCheck) -> tuple[str, str]:
    """What and why for the audit line of a mandate that passed."""
    if check.signed_by == "agent":
        return (
            "Mandate chain valid, signed by the agent inside the manager's open mandate.",
            "Signatures, merchant, spend cap, quote hash, amount and single use all pass.",
        )
    return (
        "Mandates valid, signed by the manager for this exact quote.",
        "Signatures, merchant, quote hash, amount and single use all pass.",
    )
