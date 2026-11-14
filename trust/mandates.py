"""Who may order a quote: AP2 mandates.

The manager signs two open mandates in advance, bound to the agent's public key: which merchants (checkout) and
the spend cap (payment). Below the cap the agent closes both for one quote. Above it, or when a rule asks for a
human, the manager signs both closed mandates directly for this exact quote. The gateway checks either form.

Binding: `aud` is the merchant id, `nonce` is the checkout id, the payment's `transaction_id` is the checkout hash.
Mandate times (`iat`, `exp`) use the real clock, because the SDK stamps the real time when it signs.
"""

from typing import Literal

from ap2.sdk.checkout_mandate_chain import CheckoutMandateChain
from ap2.sdk.mandate import MandateClient
from ap2.sdk.payment_mandate_chain import PaymentMandateChain
from ap2.sdk.utils import compute_sha256_b64url
from jwcrypto.jwk import JWK
from pydantic import BaseModel, ConfigDict

from contract.ap2 import (
    AllowedMerchants,
    Amount,
    AmountRange,
    CheckoutMandate,
    OpenCheckoutMandate,
    OpenPaymentMandate,
    PaymentInstrument,
    PaymentMandate,
)
from contract.models import AimoCheckout, Authorization, BuyerPolicy
from trust import TrustError
from trust.checkout import checkout_hash, read_checkout

_client = MandateClient()
CHAIN = "~~"  # an agent-closed mandate is "<open mandate>~~<closed hop>"; a human-signed one is a single token


class OpenMandates(BaseModel):
    """The two SD-JWTs the manager signed in advance. Held by the harness, never by the agent."""

    model_config = ConfigDict(extra="forbid")

    checkout: str
    payment: str


class MandateCheck(BaseModel):
    """What the gateway learns from an Authorization. `reference` is what the receipt points at."""

    model_config = ConfigDict(extra="forbid")

    ok: bool
    signed_by: Literal["agent", "human"] | None
    problems: list[str]
    reference: str | None


def issue_open_mandates(policy: BuyerPolicy, manager_key: JWK, agent_public_jwk: dict) -> OpenMandates:
    bound_to_agent = {"cnf": {"jwk": agent_public_jwk}, "exp": int(policy.valid_until.timestamp())}
    checkout = OpenCheckoutMandate(constraints=[AllowedMerchants(allowed=policy.allowed_merchants)], **bound_to_agent)
    cap = AmountRange(currency=policy.currency, max=policy.autonomous_limit_minor)
    payment = OpenPaymentMandate(constraints=[cap], **bound_to_agent)
    return OpenMandates(
        checkout=_client.create(payloads=[checkout], issuer_key=manager_key),
        payment=_client.create(payloads=[payment], issuer_key=manager_key),
    )


def close_as_agent(open_mandates: OpenMandates, agent_key: JWK, checkout_jwt: str) -> Authorization:
    checkout, closed_checkout, closed_payment = _closed_mandates(checkout_jwt)
    assert checkout.merchant is not None
    bind = {"holder_key": agent_key, "aud": checkout.merchant.id, "nonce": checkout.id}
    return Authorization(
        signed_by="agent",
        checkout_mandate=_client.present(mandate_token=open_mandates.checkout, payloads=[closed_checkout], **bind),
        payment_mandate=_client.present(mandate_token=open_mandates.payment, payloads=[closed_payment], **bind),
    )


def close_as_human(manager_key: JWK, checkout_jwt: str) -> Authorization:
    _, closed_checkout, closed_payment = _closed_mandates(checkout_jwt)
    return Authorization(
        signed_by="human",
        checkout_mandate=_client.create(payloads=[closed_checkout], issuer_key=manager_key),
        payment_mandate=_client.create(payloads=[closed_payment], issuer_key=manager_key),
    )


def mandate_reference(authorization: Authorization) -> str:
    """SHA-256 base64url of the closed checkout mandate JWT, used to bind orders and receipts."""
    return compute_sha256_b64url(_client.get_closed_mandate_jwt(authorization.checkout_mandate))


def verify_mandates(authorization: Authorization, checkout_jwt: str, manager_public_jwk: dict) -> MandateCheck:
    """Gateway side. Pass the quote exactly as the gateway issued it. `ok` is True only when `problems` is empty."""
    reference = mandate_reference(authorization)
    try:
        checkout = read_checkout(checkout_jwt)
    except TrustError as e:
        return MandateCheck(ok=False, signed_by=None, problems=[str(e)], reference=reference)

    chained = {CHAIN in authorization.checkout_mandate, CHAIN in authorization.payment_mandate}
    if len(chained) != 1:
        return MandateCheck(
            ok=False, signed_by=None, problems=["mandates mix agent and human forms"], reference=reference
        )
    actual = "agent" if chained == {True} else "human"
    problems = [] if actual == authorization.signed_by else [f"says signed by {authorization.signed_by}, is {actual}"]

    manager = JWK(**manager_public_jwk)
    try:
        if actual == "agent":
            problems += _verify_agent(authorization, checkout, checkout_jwt, manager)
        else:
            problems += _verify_human(authorization, checkout, checkout_jwt, manager)
    except Exception as e:  # noqa: BLE001  the SDK raises ValueError, TypeError or jwcrypto errors for a bad chain
        problems.append(f"mandate rejected: {type(e).__name__}: {e}"[:300])
    return MandateCheck(
        ok=not problems, signed_by=actual if not problems else None, problems=problems, reference=reference
    )


def _closed_mandates(checkout_jwt: str) -> tuple[AimoCheckout, CheckoutMandate, PaymentMandate]:
    checkout, digest = read_checkout(checkout_jwt), checkout_hash(checkout_jwt)
    if checkout.merchant is None:
        raise TrustError("checkout is missing merchant")
    closed_checkout = CheckoutMandate(checkout_jwt=checkout_jwt, checkout_hash=digest)
    closed_payment = PaymentMandate(
        transaction_id=digest,
        payee=checkout.merchant,
        payment_amount=Amount(amount=checkout.total_minor(), currency=checkout.currency),
        payment_instrument=PaymentInstrument(id=f"invoice-account:{checkout.aimo.customer}", type="invoice"),
    )
    return checkout, closed_checkout, closed_payment


def _verify_agent(authorization: Authorization, checkout: AimoCheckout, checkout_jwt: str, manager: JWK) -> list[str]:
    """Both chains must start with the manager's key, end with the key the manager bound, and target this quote."""
    if checkout.merchant is None:
        return ["checkout is missing merchant"]
    bind = {
        "key_or_provider": lambda _token: manager,
        "expected_aud": checkout.merchant.id,
        "expected_nonce": checkout.id,
    }
    checkout_chain = CheckoutMandateChain.parse(_client.verify(token=authorization.checkout_mandate, **bind))
    payment_chain = PaymentMandateChain.parse(_client.verify(token=authorization.payment_mandate, **bind))
    problems = checkout_chain.verify(expected_checkout_hash=checkout_hash(checkout_jwt), checkout_jwt=checkout_jwt)
    problems += payment_chain.verify()
    return problems + _payment_matches(payment_chain.closed_mandate, checkout, checkout_jwt)


def _verify_human(authorization: Authorization, checkout: AimoCheckout, checkout_jwt: str, manager: JWK) -> list[str]:
    """Both closed mandates must be signed by the manager's own key, for this exact quote."""
    closed_checkout = _client.verify(authorization.checkout_mandate, manager, payload_type=CheckoutMandate)
    closed_payment = _client.verify(authorization.payment_mandate, manager, payload_type=PaymentMandate)
    problems = []
    if closed_checkout.mandate_payload.checkout_hash != checkout_hash(checkout_jwt):
        problems.append("checkout mandate is for another quote")
    return problems + _payment_matches(closed_payment.mandate_payload, checkout, checkout_jwt)


def _payment_matches(payment: PaymentMandate, checkout: AimoCheckout, checkout_jwt: str) -> list[str]:
    """The cap check alone would accept a payment smaller than the quote: the amount must be the quote's total."""
    problems = []
    if payment.transaction_id != checkout_hash(checkout_jwt):
        problems.append("payment mandate is for another quote")
    if (payment.payment_amount.amount, payment.payment_amount.currency) != (checkout.total_minor(), checkout.currency):
        problems.append(
            f"payment amount {payment.payment_amount.amount} is not the quote total {checkout.total_minor()}"
        )
    if checkout.merchant is None:
        problems.append("checkout is missing merchant")
    elif payment.payee.id != checkout.merchant.id:
        problems.append(f"payee {payment.payee.id} is not the quote's merchant")
    return problems
