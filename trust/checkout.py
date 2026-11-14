"""The quote: Valio signs an AimoCheckout as an ES256 JWT, the buyer side verifies it before anything else."""

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from ap2.sdk.utils import b64url_decode, compute_sha256_b64url
from jwcrypto.jwk import JWK
from pydantic import ValidationError

from contract.models import AimoCheckout
from trust import TrustError
from trust.keys import sign, verify

HELSINKI = ZoneInfo("Europe/Helsinki")


def sign_checkout(checkout: AimoCheckout, merchant_key: JWK) -> str:
    """Signs exactly what the AP2 SDK expects: the checkout as JSON, empty fields left out, no extra claims."""
    return sign(checkout.model_dump(mode="json", exclude_none=True), merchant_key)


def verify_checkout(checkout_jwt: str, merchant_jwks: dict, now: datetime) -> AimoCheckout:
    """Raises TrustError with rule 'quote-signature' (bad signature or shape) or 'quote-not-expired'."""
    checkout = _parse(verify(checkout_jwt, merchant_jwks))
    if checkout.expires_at is None:
        raise TrustError("The quote has no expiry date, so it cannot be trusted.", rule="quote-not-expired")
    if checkout.expires_at <= now:
        expired = checkout.expires_at.astimezone(HELSINKI)
        raise TrustError(f"The quote expired on {expired:%d/%m/%Y at %H:%M}.", rule="quote-not-expired")
    return checkout


def checkout_hash(checkout_jwt: str) -> str:
    """SHA-256 of the exact token, base64url. Mandates, approvals, orders and receipts all point at this."""
    return compute_sha256_b64url(checkout_jwt)


def read_checkout(checkout_jwt: str) -> AimoCheckout:
    """The payload WITHOUT checking the signature. Only for a token already verified, or about to be."""
    try:
        return _parse(json.loads(b64url_decode(checkout_jwt.split(".")[1])))
    except (IndexError, ValueError) as e:
        raise TrustError("not a JWT") from e


def _parse(payload: dict) -> AimoCheckout:
    try:
        return AimoCheckout.model_validate(payload)
    except ValidationError as e:
        raise TrustError(f"signed payload is not an AimoCheckout: {e.error_count()} errors") from e
