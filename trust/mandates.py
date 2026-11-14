"""Who may order a quote: AP2 mandates.

The manager signs two open mandates in advance, bound to the agent's public key: which merchants (checkout) and
the spend cap (payment). Below the cap the agent closes both for one quote. Above it, or when a rule asks for a
human, the manager signs both closed mandates directly for this exact quote. The gateway checks either form.

Binding: `aud` is the merchant id, `nonce` is the checkout id, the payment's `transaction_id` is the checkout hash.
Mandate times (`iat`, `exp`) use the real clock, because the SDK stamps the real time when it signs.

A refusal is a list of problems, and each one is a sentence a buyer can read on the approval page: the SDK's own
words ("KB-SD-JWT nonce mismatch") are put in plain words here, with the amounts and the quote ids they name.
"""

import re
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from ap2.sdk.checkout_mandate_chain import CheckoutMandateChain
from ap2.sdk.mandate import MandateClient
from ap2.sdk.payment_mandate_chain import PaymentMandateChain
from ap2.sdk.utils import compute_sha256_b64url
from jwcrypto.jwk import JWK
from jwcrypto.jws import InvalidJWSSignature
from pydantic import BaseModel, ConfigDict

from common.money import money
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
from contract.models import AimoCheckout, Authorization, BuyerPolicy, MandateFacts
from trust import TrustError
from trust.checkout import checkout_hash, read_checkout

_client = MandateClient()
CHAIN = "~~"  # an agent-closed mandate is "<open mandate>~~<closed hop>"; a human-signed one is a single token
HELSINKI = ZoneInfo("Europe/Helsinki")


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
    facts: MandateFacts | None = None  # what the payment mandate allows: only when `ok`


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
    if checkout.merchant is None:
        return MandateCheck(ok=False, signed_by=None, problems=["The quote names no merchant."], reference=reference)

    chained = {CHAIN in authorization.checkout_mandate, CHAIN in authorization.payment_mandate}
    if len(chained) != 1:
        mixed = "The two mandates do not go together: one is signed by the agent, the other by a human."
        return MandateCheck(ok=False, signed_by=None, problems=[mixed], reference=reference)
    actual = "agent" if chained == {True} else "human"
    problems = []
    if actual != authorization.signed_by:
        said, signer = _signer_words(authorization.signed_by), _signer_words(actual)
        problems.append(f"The request says {said} signed it, but the mandates are signed by {signer}.")

    manager = JWK(**manager_public_jwk)
    facts = None
    try:
        verify = _verify_agent if actual == "agent" else _verify_human
        found, payment, cap = verify(authorization, checkout, checkout_jwt, manager)
        problems += [_plain(problem, checkout) for problem in found]
        facts = MandateFacts(
            cap_minor=cap,
            amount_minor=payment.payment_amount.amount,
            currency=payment.payment_amount.currency,
            instrument=payment.payment_instrument.id,
        )
    except Exception as e:  # noqa: BLE001  the SDK raises ValueError, TypeError or jwcrypto errors for a bad chain
        problems.append(_why_rejected(e))
    if problems:
        return MandateCheck(ok=False, signed_by=None, problems=problems, reference=reference)
    return MandateCheck(ok=True, signed_by=actual, problems=[], reference=reference, facts=facts)


def _closed_mandates(checkout_jwt: str) -> tuple[AimoCheckout, CheckoutMandate, PaymentMandate]:
    checkout, digest = read_checkout(checkout_jwt), checkout_hash(checkout_jwt)
    if checkout.merchant is None:
        raise TrustError("The quote names no merchant.")
    closed_checkout = CheckoutMandate(checkout_jwt=checkout_jwt, checkout_hash=digest)
    closed_payment = PaymentMandate(
        transaction_id=digest,
        payee=checkout.merchant,
        payment_amount=Amount(amount=checkout.total_minor(), currency=checkout.currency),
        payment_instrument=PaymentInstrument(id=f"invoice-account:{checkout.aimo.customer}", type="invoice"),
    )
    return checkout, closed_checkout, closed_payment


Verified = tuple[list[str], PaymentMandate, int | None]  # problems, the closed payment mandate, the agent's cap


def _verify_agent(authorization: Authorization, checkout: AimoCheckout, checkout_jwt: str, manager: JWK) -> Verified:
    """Both chains must start with the manager's key, end with the key the manager bound, and target this quote."""
    if checkout.merchant is None:  # verify_mandates refuses this case first
        raise TrustError("The quote names no merchant.")
    bind = {
        "key_or_provider": lambda _token: manager,
        "expected_aud": checkout.merchant.id,
        "expected_nonce": checkout.id,
    }
    checkout_chain = CheckoutMandateChain.parse(_client.verify(token=authorization.checkout_mandate, **bind))
    payment_chain = PaymentMandateChain.parse(_client.verify(token=authorization.payment_mandate, **bind))
    problems = checkout_chain.verify(expected_checkout_hash=checkout_hash(checkout_jwt), checkout_jwt=checkout_jwt)
    problems += payment_chain.verify()
    problems += _payment_matches(payment_chain.closed_mandate, checkout, checkout_jwt)
    caps = [c.max for c in payment_chain.open_mandate.constraints if getattr(c, "max", None) is not None]
    return problems, payment_chain.closed_mandate, min(caps, default=None)


def _verify_human(authorization: Authorization, checkout: AimoCheckout, checkout_jwt: str, manager: JWK) -> Verified:
    """Both closed mandates must be signed by the manager's own key, for this exact quote. No cap: the manager signs."""
    closed_checkout = _client.verify(authorization.checkout_mandate, manager, payload_type=CheckoutMandate)
    closed_payment = _client.verify(authorization.payment_mandate, manager, payload_type=PaymentMandate)
    problems = []
    if closed_checkout.mandate_payload.checkout_hash != checkout_hash(checkout_jwt):
        problems.append("The mandate is for another quote.")
    payment = closed_payment.mandate_payload
    return problems + _payment_matches(payment, checkout, checkout_jwt), payment, None


def _payment_matches(payment: PaymentMandate, checkout: AimoCheckout, checkout_jwt: str) -> list[str]:
    """The cap check alone would accept a payment smaller than the quote: the amount must be the quote's total."""
    problems = []
    if payment.transaction_id != checkout_hash(checkout_jwt):
        problems.append("The payment mandate is for another quote.")
    paid = (payment.payment_amount.amount, payment.payment_amount.currency)
    if paid != (checkout.total_minor(), checkout.currency):
        total = money(checkout.total_minor(), checkout.currency)
        problems.append(f"The payment mandate is for {money(*paid)}, the quote's total is {total}.")
    if checkout.merchant is None:
        problems.append("The quote names no merchant.")
    elif payment.payee.id != checkout.merchant.id:
        problems.append(f"The payment mandate pays {payment.payee.id}, not the merchant of this quote.")
    return problems


# ---------- refusals in plain words ----------


def _plain(problem: str, checkout: AimoCheckout) -> str:
    """One problem the SDK found, as a sentence a buyer can read. A sentence we do not know is left as it is."""
    if found := re.fullmatch(r"Amount (\d+) exceeds maximum (\d+)", problem):
        amount, cap = (money(int(minor), checkout.currency) for minor in found.groups())
        return f"The amount, {amount}, is above the {cap} the agent may sign alone."
    if problem.startswith("Checkout checkout_hash mismatch"):
        signer = checkout.merchant.name or checkout.merchant.id
        return f"The mandate does not match the quote {signer} signed: the quote was changed, or it is another one."
    if found := re.fullmatch(r"Merchant (.+) not in allowed list", problem):
        return f"{found[1]} is not a merchant the agent is allowed to order from."
    return problem


def _why_rejected(error: Exception) -> str:
    """Why the SDK refused to read a mandate at all: a bad signature, another quote, a mandate past its date."""
    text = str(error)
    if isinstance(error, InvalidJWSSignature):
        return "A signature on the mandate does not verify: it was not signed with the expected key."
    if found := re.search(r"nonce mismatch: expected '([^']+)', got '([^']+)'", text):
        return f"The mandate was signed for another quote ({found[2]}), not for this one ({found[1]})."
    if found := re.search(r"expired at (\d+)", text):
        when = datetime.fromtimestamp(int(found[1]), HELSINKI)
        return f"A mandate in the chain expired on {when:%d/%m/%Y at %H:%M}: the manager must sign a new one."
    return f"The mandate could not be verified ({type(error).__name__}: {text})"[:300]


def _signer_words(signed_by: str) -> str:
    return "a human" if signed_by == "human" else "the agent"
