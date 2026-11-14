"""The sandbox payment: once the mandates verify, the order's amount is booked on a simulated invoice account.

No real money moves. A wholesale customer pays on invoice, so the payment mandate names the customer's invoice account
as its instrument, and this file plays that account: one JSON file per customer under state/merchant/accounts/ with
the credit limit, what is booked so far, and one line per payment. `scripts/dev.py --fresh` empties it with the rest.

The credit limit and the payment terms are made up for the sandbox: Valio's real ones are not in the challenge data.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel

from contract.models import AimoCheckout, MandateFacts, Payment
from merchant import store

ACCOUNTS = "accounts"
CREDIT_LIMIT_MINOR = 2_000_000  # EUR 20,000 a customer: about a hundred demo orders before a --fresh is needed
TERMS = "Invoice at 14 days (simulated)"


class PaymentRefused(Exception):
    """The amount cannot be booked. The message is one of the problems the refused order lists."""


class Booking(BaseModel):
    payment_id: str
    order_id: str
    amount_minor: int
    captured_at: datetime


class Account(BaseModel):
    """A customer's simulated invoice account."""

    customer: str
    instrument: str
    currency: str
    credit_limit_minor: int
    used_minor: int = 0
    bookings: list[Booking] = []


def instrument_of(customer: str) -> str:
    """The name of a customer's invoice account, as the payment mandate writes it (trust/mandates.py)."""
    return f"invoice-account:{customer}"


def account(customer: str, currency: str = "EUR") -> Account:
    """The customer's account as it stands, or a new empty one. Nothing is written."""
    found = store._load(ACCOUNTS, customer, Account)
    return found or Account(
        customer=customer,
        instrument=instrument_of(customer),
        currency=currency,
        credit_limit_minor=CREDIT_LIMIT_MINOR,
    )


def capture(checkout: AimoCheckout, facts: MandateFacts, order_id: str, now: datetime) -> Payment:
    """Book the quote's total on the customer's account. Call it once the mandates verify, under the order lock."""
    customer = checkout.aimo.customer
    if not store.SAFE_ID.match(customer):
        raise PaymentRefused(f"customer {customer!r} cannot have an invoice account")
    if facts.instrument != instrument_of(customer):
        raise PaymentRefused(f"payment instrument {facts.instrument} is not {customer}'s invoice account")
    booked = account(customer, checkout.currency)
    amount = checkout.total_minor()
    if booked.used_minor + amount > booked.credit_limit_minor:
        left = booked.credit_limit_minor - booked.used_minor
        raise PaymentRefused(
            f"amount {amount} exceeds what is left on the invoice account ({left} of {booked.credit_limit_minor})"
        )
    payment = Payment(
        payment_id=f"pay_{uuid.uuid4().hex[:8]}",
        status="captured",
        amount_minor=amount,
        currency=checkout.currency,
        instrument=booked.instrument,
        terms=TERMS,
        captured_at=now,
    )
    booked.used_minor += amount
    booked.bookings.append(
        Booking(payment_id=payment.payment_id, order_id=order_id, amount_minor=amount, captured_at=now)
    )
    store._save(ACCOUNTS, customer, booked)
    return payment
